from __future__ import annotations

from research_agent.agent.research import ResearchAgent


class _DummyLLM:
    def json_response(self, **_: object) -> dict:
        raise AssertionError("LLM should not be called in this unit test")


def _agent() -> ResearchAgent:
    return ResearchAgent(llm=_DummyLLM())  # type: ignore[arg-type]


def test_maps_structural_code() -> None:
    assert _agent()._partials_to_refresh(["lifecycle_missing_stages: x"]) == {"structure"}


def test_maps_agronomic_code() -> None:
    assert _agent()._partials_to_refresh(["too_few_yield_drivers: x"]) == {"agronomic"}


def test_maps_interventions_code() -> None:
    assert _agent()._partials_to_refresh(["intervention_effect_dangling_fk: x"]) == {"interventions"}


def test_unknown_or_retrieval_only_codes_do_not_force_redraft() -> None:
    assert _agent()._partials_to_refresh(["evidence_id_unknown:E001: x"]) == set()

