from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from research_agent.agent.questionnaire import (
    filter_questions,
    instantiate_questions,
    satisfies,
    validate_answer_claim_evidence_ids,
)
from research_agent.contracts.agronomy.dossier import CropDossier, LifecycleStage, ProductionSystemContext
from research_agent.contracts.core.artifact_meta import ArtifactMeta
from research_agent.contracts.core.claims import Claim
from research_agent.contracts.core.questionnaire import (
    ApplicabilityRule,
    QuestionAnswer,
    QuestionnaireSpec,
    QuestionSpec,
)


def _meta() -> ArtifactMeta:
    now = datetime.now(timezone.utc)
    return ArtifactMeta(artifact_id="test-dossier", artifact_type="crop_dossier", created_at=now, updated_at=now)


def _minimal_dossier(
    *,
    crop_name: str = "Wheat",
    lifecycle_stages: list[LifecycleStage] | None = None,
    production: ProductionSystemContext | None = None,
    meta_tags: list[str] | None = None,
    primary_use_cases: list[str] | None = None,
) -> CropDossier:
    if lifecycle_stages is None:
        stages = [
            LifecycleStage(
                stage="Pre-plant",
                description="Prep",
            )
        ]
    else:
        stages = lifecycle_stages
    meta = _meta()
    if meta_tags is not None:
        meta = meta.model_copy(update={"tags": meta_tags})
    return CropDossier(
        meta=meta,
        crop_name=crop_name,
        crop_category="cereal",
        primary_use_cases=primary_use_cases if primary_use_cases is not None else ["panel"],
        priority_tier="T1",
        last_updated=date.today(),
        production_system_context=production or ProductionSystemContext(core_regions=["EU"]),
        lifecycle_ontology=stages,
    )


def test_satisfies_non_empty_and_present() -> None:
    d = _minimal_dossier()
    assert satisfies(d, ApplicabilityRule(op="non_empty", field="lifecycle_ontology"))[0] is True
    assert satisfies(d, ApplicabilityRule(op="present", field="production_system_context"))[0] is True


def test_satisfies_not_applicable_empty_list() -> None:
    d = _minimal_dossier(lifecycle_stages=[])
    ok, reason = satisfies(d, ApplicabilityRule(op="non_empty", field="lifecycle_ontology"))
    assert ok is False
    assert reason == "empty"


def test_satisfies_contains_keyword() -> None:
    d = _minimal_dossier(crop_name="Durum Wheat")
    assert satisfies(d, ApplicabilityRule(op="contains_keyword", field="crop_name", value="wheat"))[0] is True
    ok, reason = satisfies(d, ApplicabilityRule(op="contains_keyword", field="crop_name", value="barley"))
    assert ok is False
    assert "keyword_missing" in (reason or "")


def test_satisfies_has_tag_meta_and_primary_use_cases() -> None:
    d = _minimal_dossier(meta_tags=["demo", "pilot"])
    assert satisfies(d, ApplicabilityRule(op="has_tag", field="meta_tags", value="demo"))[0] is True
    ok, reason = satisfies(d, ApplicabilityRule(op="has_tag", field="meta_tags", value="missing"))
    assert ok is False
    assert "tag_missing_meta" in (reason or "")
    d2 = _minimal_dossier(primary_use_cases=["pathogen panel", "pilot"])
    assert satisfies(d2, ApplicabilityRule(op="has_tag", field="primary_use_cases", value="pilot"))[0] is True
    assert satisfies(d2, ApplicabilityRule(op="has_tag", field="primary_use_cases", value="nope"))[0] is False


def test_legacy_applicability_string_coerced_to_present() -> None:
    q = QuestionSpec.model_validate(
        {
            "id": "a",
            "category": "C",
            "prompt_template": "{x}",
            "variables": ["x"],
            "applicability_rules": ["lifecycle_ontology"],
        }
    )
    assert q.applicability_rules[0].op == "present"
    assert q.applicability_rules[0].field == "lifecycle_ontology"


def test_unsupported_op_raises() -> None:
    d = _minimal_dossier()
    bad = ApplicabilityRule.model_construct(op="not_a_real_op", field="crop_name")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Unsupported applicability op"):
        satisfies(d, bad)


def test_filter_skips_when_required_context_missing() -> None:
    spec = QuestionnaireSpec(
        questionnaire_id="q",
        domain="test",
        version="1",
        questions=[
            QuestionSpec(
                id="needs_lo",
                category="C",
                prompt_template="{v}",
                variables=["v"],
                applicability_rules=[],
                required_context=["lifecycle_ontology"],
            ),
        ],
    )
    instantiated = instantiate_questions(spec, {"v": "x"})
    d = _minimal_dossier(lifecycle_stages=[])
    applicable, skipped = filter_questions(d, instantiated)
    assert applicable == []
    assert len(skipped) == 1
    assert "required_context_empty" in (skipped[0].skip_reason or "")


def test_validate_answer_claim_evidence_ids_downgrades() -> None:
    r = QuestionAnswer(
        question_id="q1",
        status="answered",
        answer_markdown="x",
        key_claims=[Claim(text="t", evidence_ids=["E999"])],
    )
    fixed, errs = validate_answer_claim_evidence_ids([r], {"E001"})
    assert fixed[0].status == "insufficient_evidence"
    assert errs and "invalid_evidence_ids" in errs[0]


def test_filter_skips_failed_rules() -> None:
    spec = QuestionnaireSpec(
        questionnaire_id="q",
        domain="test",
        version="1",
        questions=[
            QuestionSpec(
                id="always",
                category="C",
                prompt_template="{v}",
                variables=["v"],
                applicability_rules=[],
            ),
            QuestionSpec(
                id="needs_wheat",
                category="C",
                prompt_template="{v}",
                variables=["v"],
                applicability_rules=[
                    ApplicabilityRule(op="contains_keyword", field="crop_name", value="barley"),
                ],
            ),
        ],
    )
    instantiated = instantiate_questions(spec, {"v": "x"})
    d = _minimal_dossier(crop_name="Wheat")
    applicable, skipped = filter_questions(d, instantiated)
    assert [x.spec.id for x in applicable] == ["always"]
    assert len(skipped) == 1
    assert skipped[0].question_id == "needs_wheat"
    assert skipped[0].applicable is False
    assert "not_applicable" in (skipped[0].skip_reason or "")


def test_instantiate_missing_variable_raises() -> None:
    spec = QuestionnaireSpec(
        questionnaire_id="q",
        domain="test",
        version="1",
        questions=[
            QuestionSpec(id="a", category="C", prompt_template="{a}", variables=["a"]),
        ],
    )
    with pytest.raises(ValueError, match="missing variables"):
        instantiate_questions(spec, {})
