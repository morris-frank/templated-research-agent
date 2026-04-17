from __future__ import annotations

from research_agent.agent.dossier_bridge import DroppedRef
from research_agent.agent.research import ResearchAgent
from research_agent.contracts.agronomy.validation import DossierThresholds
from research_agent.types import EvidenceItem


class _DummyLLM:
    def json_response(self, **_: object) -> dict:
        raise AssertionError("LLM should not be called in this unit test")


def _agent() -> ResearchAgent:
    return ResearchAgent(llm=_DummyLLM())  # type: ignore[arg-type]


def _evidence() -> list[EvidenceItem]:
    items = []
    for ref in _dossier().evidence_index:
        items.append(
            EvidenceItem(
                id=ref.id,
                source_type="paper" if ref.source_type == "paper" else "web",
                retrieval_method="test",
                title=ref.title,
                url=str(ref.url),
            )
        )
    return items


def _dossier():
    from examples.build_demo_artifacts import demo_dossier

    return demo_dossier()


def test_evaluate_crop_dossier_structural_passes_for_demo() -> None:
    ok, errors = _agent().evaluate_crop_dossier(_dossier(), _evidence(), [])
    assert ok
    assert errors == []


def test_evaluate_crop_dossier_reports_unknown_evidence_and_dropped_refs() -> None:
    dossier = _dossier()
    dossier.yield_drivers[0].evidence_ids = ["E_BOGUS"]
    dropped = [DroppedRef(kind="intervention_effect", location="intervention_effects[0]", value="x", reason="unknown")]
    ok, errors = _agent().evaluate_crop_dossier(dossier, _evidence(), dropped)
    assert not ok
    assert any("evidence_id_unknown:E_BOGUS" in e for e in errors)
    assert any(e.startswith("merge_ref_dropped:") for e in errors)


def test_evaluate_crop_dossier_reports_section_floor() -> None:
    dossier = _dossier()
    for yd in dossier.yield_drivers:
        yd.evidence_ids = []
    ok, errors = _agent().evaluate_crop_dossier(
        dossier,
        _evidence(),
        [],
        DossierThresholds(min_evidence_linked_per_section={"yield_drivers": 1, "interventions": 1, "pathogens": 1}),
    )
    assert not ok
    assert any(e.startswith("per_section_evidence_floor:yield_drivers") for e in errors)

