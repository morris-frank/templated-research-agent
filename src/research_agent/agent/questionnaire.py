"""Questionnaire execution: instantiate, filter, answer — no retrieval (orchestrated in ResearchAgent)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
from research_agent.agent.llm import LLMClient
from research_agent.types import EvidenceItem


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
    *,
    question_spec: QuestionSpec | None = None,
) -> tuple[bool, str | None]:
    """Evaluate one rule. Returns (ok, reason_if_failed)."""
    op = rule.op
    if op == "has_tag":
        if rule.value is None or not rule.value.strip():
            raise ValueError("has_tag requires rule.value")
        if question_spec is None:
            raise ValueError("has_tag requires question_spec")
        ok = rule.value in question_spec.tags
        return ok, None if ok else f"tag_missing:{rule.value}"

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


def filter_questions(
    dossier: CropDossier,
    instantiated: list[InstantiatedQuestion],
) -> tuple[list[InstantiatedQuestion], list[SkippedQuestion]]:
    """Keep questions whose applicability_rules all pass."""
    applicable: list[InstantiatedQuestion] = []
    skipped: list[SkippedQuestion] = []
    for iq in instantiated:
        spec = iq.spec
        if not spec.applicability_rules:
            applicable.append(iq)
            continue
        failed_reason: str | None = None
        for rule in spec.applicability_rules:
            ok, reason = satisfies(dossier, rule, question_spec=spec)
            if not ok:
                failed_reason = reason or "rule_failed"
                break
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
    llm: LLMClient,
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
                "Each key_claim must include evidence_ids referencing only IDs from the evidence list.",
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


def build_execution_result(
    spec: QuestionnaireSpec,
    subject_id: str,
    responses: list[QuestionAnswer],
    skipped: list[SkippedQuestion],
    *,
    stop_reason: str | None = None,
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
    )


def run_questionnaire_pass(
    llm: LLMClient,
    spec: QuestionnaireSpec,
    dossier: CropDossier,
    evidence: list[EvidenceItem],
    variables: dict[str, Any],
    *,
    subject_id: str,
    top_k_evidence: int = 25,
    stop_reason: str | None = None,
) -> QuestionnaireExecutionResult:
    """Single pass: instantiate → filter → answer → coverage."""
    instantiated = instantiate_questions(spec, variables)
    applicable, skipped = filter_questions(dossier, instantiated)
    responses = answer_questions(
        llm, spec, dossier, evidence, applicable, top_k_evidence=top_k_evidence
    )
    return build_execution_result(spec, subject_id, responses, skipped, stop_reason=stop_reason)
