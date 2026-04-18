from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from research_agent.agent.questionnaire import (
    filter_questions,
    instantiate_questions,
    satisfies,
)
from research_agent.contracts.agronomy.dossier import CropDossier, LifecycleStage, ProductionSystemContext
from research_agent.contracts.core.artifact_meta import ArtifactMeta
from research_agent.contracts.core.questionnaire import (
    ApplicabilityRule,
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
    return CropDossier(
        meta=_meta(),
        crop_name=crop_name,
        crop_category="cereal",
        primary_use_cases=["panel"],
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


def test_satisfies_has_tag_requires_question_spec() -> None:
    spec = QuestionSpec(
        id="q1",
        category="X",
        prompt_template="Hi {x}",
        variables=["x"],
        tags=["alpha", "beta"],
    )
    d = _minimal_dossier()
    assert satisfies(d, ApplicabilityRule(op="has_tag", value="alpha"), question_spec=spec)[0] is True
    assert satisfies(d, ApplicabilityRule(op="has_tag", value="gamma"), question_spec=spec)[0] is False


def test_unsupported_op_raises() -> None:
    d = _minimal_dossier()
    bad = ApplicabilityRule.model_construct(op="not_a_real_op", field="crop_name")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Unsupported applicability op"):
        satisfies(d, bad)


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
