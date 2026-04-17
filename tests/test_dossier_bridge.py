from __future__ import annotations

from datetime import datetime, timezone

from research_agent.agent.dossier_bridge import evidence_items_to_refs, merge_crop_dossier
from research_agent.agent.schemas import CropDossierDraft
from research_agent.types import EvidenceItem


def _evidence_item() -> EvidenceItem:
    return EvidenceItem(
        id="E001",
        source_type="paper",
        retrieval_method="test",
        title="Sample",
        url="https://example.org/paper",
        abstract_or_snippet="snippet",
        venue="Journal",
        year=2024,
        authors=["A. Author"],
        score=0.9,
    )


def _draft_with_bad_refs() -> CropDossierDraft:
    return CropDossierDraft.model_validate(
        {
            "crop_name": "Wheat",
            "crop_category": "cereal",
            "primary_use_cases": ["test"],
            "priority_tier": "T1",
            "production_system_context": {},
            "rotation_role": {},
            "lifecycle_ontology": [{"stage": "Vegetative", "description": ""}],
            "yield_drivers": [{"id": "yd1", "name": "N", "mechanism": {"text": "x", "evidence_ids": ["E001"]}}],
            "limiting_factors": [],
            "agronomist_heuristics": [],
            "interventions": [{"id": "iv1", "kind": "input", "name": "fert"}],
            "intervention_effects": [
                {"intervention_id": "iv-missing", "target_ref": "yd1", "effect": "increase"},
                {"intervention_id": "iv1", "target_ref": "missing-target", "effect": "decrease"},
            ],
            "pathogens": [{"id": "p1", "name": "rust", "affected_stages": ["Vegetative"]}],
            "beneficials": [],
            "soil_dependencies": [],
            "microbiome_roles": [],
            "cover_crop_effects": [
                {"cover_crop": "clover", "target_ref": "unknown", "effect": {"text": "x", "evidence_ids": []}}
            ],
            "confidence": 0.5,
            "open_questions": [],
        }
    )


def test_evidence_items_to_refs_round_trip_fields() -> None:
    refs = evidence_items_to_refs([_evidence_item()])
    assert len(refs) == 1
    assert refs[0].id == "E001"
    assert str(refs[0].url) == "https://example.org/paper"
    assert refs[0].source_type == "paper"


def test_merge_crop_dossier_normalizes_and_reports_dropped_refs() -> None:
    dossier, dropped = merge_crop_dossier(
        _draft_with_bad_refs(),
        evidence_items_to_refs([_evidence_item()]),
        artifact_id="dossier-test",
        now=datetime.now(timezone.utc),
    )
    assert dossier.meta.artifact_type == "crop_dossier"
    assert dossier.evidence_index and dossier.evidence_index[0].id == "E001"
    assert len(dropped) >= 2
    assert any(d.reason == "unknown_intervention_id" for d in dropped)
    assert any(d.reason == "unknown_target_ref" for d in dropped)

