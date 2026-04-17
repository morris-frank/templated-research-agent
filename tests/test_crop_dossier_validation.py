"""Tests for :mod:`research_agent.contracts.agronomy.validation`."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from research_agent.contracts.agronomy.dossier import CropDossier
from research_agent.contracts.agronomy.validation import (
    DossierThresholds,
    validate_crop_dossier,
    validate_crop_dossier_detailed,
)
from research_agent.contracts.core.artifact_meta import ArtifactMeta

pytest.importorskip("examples.build_demo_artifacts", reason="demo builder not importable")
from examples.build_demo_artifacts import demo_dossier  # noqa: E402


def _empty_dossier() -> CropDossier:
    return CropDossier(
        meta=ArtifactMeta(
            artifact_id="dossier-empty",
            artifact_type="crop_dossier",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        crop_name="Test",
        crop_category="cereal",
        primary_use_cases=[],
        priority_tier="T3",
        last_updated=date.today(),
        lifecycle_ontology=[],
    )


def _codes(result) -> list[str]:
    return [e.code for e in result.errors]


def test_empty_dossier_fails_minimums_and_lifecycle():
    result = validate_crop_dossier_detailed(_empty_dossier())
    assert result.ok is False
    codes = _codes(result)
    assert "lifecycle_missing_stages" in codes
    assert "too_few_yield_drivers" in codes
    assert "too_few_interventions" in codes
    assert "too_few_pathogens" in codes


def test_demo_dossier_validates_cleanly():
    result = validate_crop_dossier_detailed(demo_dossier())
    assert result.ok is True, [e.code for e in result.errors]
    assert result.errors == []


def test_dangling_intervention_effect_fk():
    dossier = demo_dossier()
    dossier.intervention_effects[0].target_ref = "ZZZ"
    result = validate_crop_dossier_detailed(dossier)
    assert result.ok is False
    assert "intervention_effect_dangling_fk" in _codes(result)


def test_dangling_intervention_id_fk():
    dossier = demo_dossier()
    dossier.intervention_effects[0].intervention_id = "IV_BOGUS"
    result = validate_crop_dossier_detailed(dossier)
    assert "intervention_effect_dangling_fk" in _codes(result)


def test_evidence_coverage_threshold():
    dossier = demo_dossier()
    for d in dossier.yield_drivers:
        d.evidence_ids = []
        d.mechanism.evidence_ids = []
    for p in dossier.pathogens:
        p.evidence_ids = []
    for iv in dossier.interventions:
        iv.evidence_ids = []

    lenient = validate_crop_dossier_detailed(
        dossier, DossierThresholds(min_evidence_linked_fraction=0.1)
    )
    assert "low_evidence_coverage" not in _codes(lenient)

    strict = validate_crop_dossier_detailed(
        dossier, DossierThresholds(min_evidence_linked_fraction=0.9)
    )
    assert "low_evidence_coverage" in _codes(strict)


def test_evidence_id_dangling():
    dossier = demo_dossier()
    dossier.yield_drivers[0].evidence_ids.append("E_MISSING")
    result = validate_crop_dossier_detailed(dossier)
    assert "evidence_id_dangling" in _codes(result)


def test_validate_returns_messages_matching_detailed():
    dossier = _empty_dossier()
    detailed = validate_crop_dossier_detailed(dossier)
    simple = validate_crop_dossier(dossier)
    assert simple == [e.message for e in detailed.errors]
