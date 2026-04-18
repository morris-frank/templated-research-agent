"""Questionnaire execution: instantiate, filter, answer — no retrieval (orchestrated in ResearchAgent).

LLM calls use a client passed from the caller; this module does not import ``agent.llm`` at import time
(so pure helpers like ``satisfies`` / ``filter_questions`` stay usable without the OpenAI stack).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from research_agent.contracts.agronomy.dossier import CropDossier
from research_agent.contracts.core.questionnaire import (
    ApplicabilityRule,
    QuestionAnswer,
    QuestionAnswerDraft,
    QuestionInstance,
    QuestionnaireCoverage,
    QuestionnaireExecutionResult,
    QuestionnaireResponseSet,
    QuestionnaireSpec,
    QuestionSpec,
    SkippedQuestion,
)
from research_agent.types import EvidenceItem

if TYPE_CHECKING:
    from research_agent.agent.llm import LLMClient


@dataclass(frozen=True)
class InstantiatedQuestion:
    spec: QuestionSpec
    instance: QuestionInstance


def _normalize_vars(variables: dict[str, Any]) -> dict[str, str]:
    return {k: str(v) for k, v in variables.items()}


def instantiate_questions(spec: QuestionnaireSpec, variables: dict[str, Any]) -> list[InstantiatedQuestion]:
    """Render each question prompt from ``variables`` (stringified)."""
    str_vars = _normalize_vars(variables)
    out: list[InstantiatedQuestion] = []
    for q in spec.questions:
        missing = [v for v in q.variables if v not in str_vars]
        if missing:
            raise ValueError(f"Question {q.id!r} missing variables: {missing}")
        rendered = q.render_prompt({k: str_vars[k] for k in q.variables})
        inst = QuestionInstance(
            spec_id=q.id,
            variables={k: str_vars[k] for k in q.variables},
            rendered_prompt=rendered,
            category=q.category,
            answer_kind=q.answer_kind,
            evidence_policy=q.evidence_policy,
            required_context=q.required_context,
        )
        out.append(InstantiatedQuestion(spec=q, instance=inst))
    return out


def resolve_dossier_field(dossier: CropDossier, field: str) -> Any:
    """Return a top-level attribute of ``CropDossier`` by name."""
    if not field or not field.replace("_", "").isalnum():
        raise ValueError(f"Invalid dossier field: {field!r}")
    if not hasattr(dossier, field):
        raise ValueError(f"Unknown dossier field: {field!r}")
    return getattr(dossier, field)


def _is_nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _field_as_search_blob(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.lower()
    parts: list[str] = []
    if isinstance(value, list):
        for item in value:
            if hasattr(item, "model_dump"):
                parts.append(str(item.model_dump()).lower())
            else:
                parts.append(str(item).lower())
    else:
        parts.append(str(value).lower())
    return " ".join(parts)


def satisfies(
    dossier: CropDossier,
    rule: ApplicabilityRule,
) -> tuple[bool, str | None]:
    """Evaluate one rule. Returns (ok, reason_if_failed).

    ``has_tag`` is dossier-scoped: use ``field`` ``meta_tags`` (default) for ``ArtifactMeta.tags``,
    or ``primary_use_cases`` for membership in ``dossier.primary_use_cases``.
    """
    op = rule.op
    if op == "has_tag":
        if rule.value is None or not str(rule.value).strip():
            raise ValueError("has_tag requires rule.value")
        tag_val = str(rule.value).strip()
        field = (rule.field or "meta_tags").strip()
        if field in ("", "meta_tags"):
            tags = dossier.meta.tags or []
            ok = tag_val in tags
            return ok, None if ok else f"tag_missing_meta:{tag_val}"
        if field == "primary_use_cases":
            ok = tag_val in dossier.primary_use_cases
            return ok, None if ok else f"tag_missing_use_case:{tag_val}"
        raise ValueError(f"has_tag field must be 'meta_tags' or 'primary_use_cases', not {field!r}")

    if not rule.field:
        raise ValueError(f"Rule op {op!r} requires field")

    try:
        value = resolve_dossier_field(dossier, rule.field)
    except ValueError as e:
        return False, str(e)

    if op == "present":
        ok = value is not None
        return ok, None if ok else "not_present"

    if op == "non_empty":
        ok = _is_nonempty(value)
        return ok, None if ok else "empty"

    if op == "contains_keyword":
        if rule.value is None:
            raise ValueError("contains_keyword requires rule.value")
        blob = _field_as_search_blob(value)
        ok = rule.value.lower() in blob
        return ok, None if ok else f"keyword_missing:{rule.value}"

    raise ValueError(f"Unsupported applicability op: {op!r}")


def required_context_satisfied(dossier: CropDossier, field_names: list[str]) -> tuple[bool, str | None]:
    """Each name must be a top-level ``CropDossier`` attribute with non-empty value."""
    for name in field_names:
        try:
            value = resolve_dossier_field(dossier, name)
        except ValueError as e:
            return False, f"required_context_unknown:{name}:{e}"
        if not _is_nonempty(value):
            return False, f"required_context_empty:{name}"
    return True, None


def filter_questions(
    dossier: CropDossier,
    instantiated: list[InstantiatedQuestion],
) -> tuple[list[InstantiatedQuestion], list[SkippedQuestion]]:
    """Keep questions whose applicability rules and required_context all pass."""
    applicable: list[InstantiatedQuestion] = []
    skipped: list[SkippedQuestion] = []
    for iq in instantiated:
        spec = iq.spec
        failed_reason: str | None = None
        if spec.applicability_rules:
            for rule in spec.applicability_rules:
                ok, reason = satisfies(dossier, rule)
                if not ok:
                    failed_reason = reason or "rule_failed"
                    break
        if failed_reason is None and spec.required_context:
            ok_rc, reason_rc = required_context_satisfied(dossier, spec.required_context)
            if not ok_rc:
                failed_reason = reason_rc or "required_context_failed"
        if failed_reason is None:
            applicable.append(iq)
        else:
            skipped.append(
                SkippedQuestion(
                    question_id=spec.id,
                    applicable=False,
                    skip_reason=f"not_applicable:{failed_reason}",
                )
            )
    return applicable, skipped


def compute_coverage(
    total_questions: int,
    skipped: list[SkippedQuestion],
    responses: list[QuestionAnswer],
) -> QuestionnaireCoverage:
    not_applicable = sum(1 for s in skipped if not s.applicable)
    applicable = total_questions - not_applicable
    answered = sum(1 for r in responses if r.status in {"answered", "partial"})
    insufficient = sum(1 for r in responses if r.status == "insufficient_evidence")
    ratio = (answered / applicable) if applicable > 0 else 0.0
    return QuestionnaireCoverage(
        total=total_questions,
        applicable=applicable,
        answered=answered,
        insufficient_evidence=insufficient,
        not_applicable=not_applicable,
        coverage_ratio=ratio,
    )


def answer_questions(
    llm: "LLMClient",
    spec: QuestionnaireSpec,
    dossier: CropDossier,
    evidence: list[EvidenceItem],
    applicable: list[InstantiatedQuestion],
    *,
    top_k_evidence: int = 25,
) -> list[QuestionAnswer]:
    """Produce one LLM answer per applicable question; no retrieval."""
    responses: list[QuestionAnswer] = []
    dossier_dump = dossier.model_dump(mode="json")
    ev_slice = evidence[:top_k_evidence]
    for iq in applicable:
        payload = {
            "question_id": iq.spec.id,
            "rendered_prompt": iq.instance.rendered_prompt,
            "answer_kind": iq.spec.answer_kind,
            "evidence_policy": iq.spec.evidence_policy,
            "dossier_context": dossier_dump,
            "evidence": [e.model_dump() for e in ev_slice],
            "instructions": [
                "Return JSON only matching QuestionAnswerDraft.",
                "Each key_claim evidence_ids must reference only IDs appearing in the evidence array below (same slice as retrieval).",
                "Use status=insufficient_evidence if evidence cannot support a defensible answer.",
                "Use status=not_applicable only if the prompt cannot apply given dossier context.",
            ],
        }
        draft = llm.json_response(
            system="Answer agronomy questionnaire items using dossier context and cited evidence IDs only.",
            user_payload=payload,
            schema_model=QuestionAnswerDraft,
        )
        validated = QuestionAnswerDraft.model_validate(draft)
        responses.append(
            QuestionAnswer(
                question_id=iq.spec.id,
                status=validated.status,
                answer_markdown=validated.answer_markdown,
                key_claims=validated.key_claims,
                rationale=validated.rationale,
            )
        )
    return responses


def validate_answer_claim_evidence_ids(
    responses: list[QuestionAnswer],
    allowed_ids: set[str],
) -> tuple[list[QuestionAnswer], list[str]]:
    """Downgrade answers whose ``key_claims`` cite evidence IDs outside ``allowed_ids`` (e.g. LLM slice)."""
    errors: list[str] = []
    fixed: list[QuestionAnswer] = []
    for r in responses:
        bad: set[str] = set()
        for c in r.key_claims:
            for eid in c.evidence_ids:
                if eid not in allowed_ids:
                    bad.add(eid)
        if bad:
            errors.append(f"{r.question_id}:invalid_evidence_ids:{sorted(bad)}")
            note = " [Deterministic: key_claim evidence_ids must reference retrieved evidence only.]"
            fixed.append(
                r.model_copy(
                    update={
                        "status": "insufficient_evidence",
                        "rationale": ((r.rationale or "") + note).strip(),
                    }
                )
            )
        else:
            fixed.append(r)
    return fixed, errors


def build_execution_result(
    spec: QuestionnaireSpec,
    subject_id: str,
    responses: list[QuestionAnswer],
    skipped: list[SkippedQuestion],
    *,
    stop_reason: str | None = None,
    evidence_validation_errors: list[str] | None = None,
) -> QuestionnaireExecutionResult:
    """Package responses, coverage, and diagnostics."""
    total = len(spec.questions)
    coverage = compute_coverage(total, skipped, responses)
    response_set = QuestionnaireResponseSet(
        questionnaire_id=spec.questionnaire_id,
        subject_id=subject_id,
        responses=responses,
    )
    return QuestionnaireExecutionResult(
        responses=response_set,
        coverage=coverage,
        skipped_questions=skipped,
        stop_reason=stop_reason,
        evidence_validation_errors=list(evidence_validation_errors or []),
    )


def run_questionnaire_pass(
    llm: "LLMClient",
    spec: QuestionnaireSpec,
    dossier: CropDossier,
    evidence: list[EvidenceItem],
    variables: dict[str, Any],
    *,
    subject_id: str,
    top_k_evidence: int = 25,
    stop_reason: str | None = None,
) -> QuestionnaireExecutionResult:
    """Single pass: instantiate → filter → answer → deterministic evidence-ID check → coverage."""
    instantiated = instantiate_questions(spec, variables)
    applicable, skipped = filter_questions(dossier, instantiated)
    responses = answer_questions(
        llm, spec, dossier, evidence, applicable, top_k_evidence=top_k_evidence
    )
    # Match LLM payload: only IDs in the evidence slice shown to the model may be cited.
    allowed_ids = {e.id for e in evidence[:top_k_evidence]}
    responses, ev_errs = validate_answer_claim_evidence_ids(responses, allowed_ids)
    return build_execution_result(
        spec,
        subject_id,
        responses,
        skipped,
        stop_reason=stop_reason,
        evidence_validation_errors=ev_errs,
    )
