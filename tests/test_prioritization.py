from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from research_agent.agent.prioritization import (
    aggregate_score,
    assign_tier_lists,
    compute_score_components,
    run_prioritization,
    validate_claim_evidence_ids,
)
from research_agent.contracts.agronomy.prioritization import (
    CropUseCaseCandidate,
    PrioritizationResult,
    RankedCandidate,
    ScoreComponents,
    TierList,
)
from research_agent.contracts.core.claims import Claim
from research_agent.contracts.renderers.markdown import render_prioritization_markdown
from research_agent.types import EvidenceItem, InputVars, PlanOut


def _ev(**kwargs: object) -> EvidenceItem:
    base = {
        "id": "e1",
        "source_type": "web",
        "retrieval_method": "t",
        "title": "t",
        "url": "http://example.com",
        "abstract_or_snippet": "",
        "score": 2.0,
    }
    base.update(kwargs)
    return EvidenceItem.model_validate(base)


def test_prioritization_result_json_roundtrip() -> None:
    c = CropUseCaseCandidate(candidate_id="x", crop="Wheat", use_case="u")
    comp = ScoreComponents(icp_fit=0.5, platform_leverage=0.5, data_availability=0.5, evidence_strength=0.5)
    rc = RankedCandidate(candidate=c, components=comp, aggregate_score=0.5, rationale_claims=[])
    pr = PrioritizationResult(
        prioritization_id="prio-test",
        ranked=[rc],
        tier_lists=[TierList(tier="T2", candidates=[rc])],
        validation_errors=[],
    )
    raw = json.loads(json.dumps(pr.model_dump(mode="json")))
    restored = PrioritizationResult.model_validate(raw)
    assert restored.prioritization_id == "prio-test"
    assert restored.ranked[0].candidate.crop == "Wheat"


def test_compute_and_aggregate_deterministic() -> None:
    ev = [
        _ev(
            id="e1",
            title="field trial biological pathogen assay",
            abstract_or_snippet="platform sensor monitoring dataset randomized design baseline metadata",
            score=2.0,
        )
    ]
    cand = CropUseCaseCandidate(candidate_id="a", crop="Wheat", use_case="diagnostics")
    comp = compute_score_components(ev, cand)
    assert comp.icp_fit == pytest.approx(compute_score_components(ev, cand).icp_fit)
    w = (0.25, 0.25, 0.25, 0.25)
    agg = aggregate_score(comp, w)
    assert agg == pytest.approx(aggregate_score(comp, w))


def test_assign_tier_lists_buckets() -> None:
    c = CropUseCaseCandidate(candidate_id="i", crop="x", use_case="y")
    comp = ScoreComponents(icp_fit=0.1, platform_leverage=0.1, data_availability=0.1, evidence_strength=0.1)
    high = RankedCandidate(candidate=c, components=comp, aggregate_score=0.9, rationale_claims=[])
    low = RankedCandidate(
        candidate=CropUseCaseCandidate(candidate_id="j", crop="a", use_case="b"),
        components=comp,
        aggregate_score=0.1,
        rationale_claims=[],
    )
    tiers = assign_tier_lists([low, high])
    assert {t.tier for t in tiers} == {"T1", "T2", "T3"}
    assert tiers[0].candidates[0].aggregate_score >= 0.67


def test_validate_claim_evidence_ids() -> None:
    errs = validate_claim_evidence_ids(
        [Claim(text="x", evidence_ids=["bad"])],
        {"ok"},
    )
    assert any("invalid_evidence_id" in e for e in errs)

    empty_errs = validate_claim_evidence_ids([Claim(text="x", evidence_ids=[])], {"e1"})
    assert "empty_evidence_ids" in empty_errs


def test_aggregate_score_rejects_bad_weights_length() -> None:
    comp = ScoreComponents(icp_fit=0.5, platform_leverage=0.5, data_availability=0.5, evidence_strength=0.5)
    with pytest.raises(ValueError, match="weights must be a 4-tuple"):
        aggregate_score(comp, (0.5, 0.5))


def test_run_prioritization_rejects_empty_claim_evidence_ids() -> None:
    plan = PlanOut(subquestions=[], web_queries=[], paper_queries=[], evidence_requirements=[])
    evidence = [_ev(id="e1")]

    class _LLM:
        def json_response(self, **_: object) -> dict:
            return {
                "rationales": [
                    {
                        "candidate_id": "c1",
                        "claims": [{"text": "no cites", "evidence_ids": [], "evidence_urls": [], "support": "direct"}],
                    }
                ]
            }

    class _Agent:
        top_k_evidence = 25
        llm = _LLM()

        def plan(self, *_a: object, **_k: object) -> PlanOut:
            return plan

        def collect_evidence(self, *_a: object, **_k: object) -> list[EvidenceItem]:
            return evidence

    res, _, _ = run_prioritization(
        _Agent(),
        "t",
        InputVars(topic="t", source_urls=[]),
        [CropUseCaseCandidate(candidate_id="c1", crop="W", use_case="u")],
    )
    assert any("empty_evidence_ids" in e for e in res.validation_errors)
    assert not res.ranked[0].rationale_claims


def test_render_prioritization_markdown_escapes_table_pipes() -> None:
    c = CropUseCaseCandidate(candidate_id="c|x", crop="A|B", use_case="Y|Z")
    comp = ScoreComponents(icp_fit=0.5, platform_leverage=0.5, data_availability=0.5, evidence_strength=0.5)
    rc = RankedCandidate(candidate=c, components=comp, aggregate_score=0.5, rationale_claims=[])
    pr = PrioritizationResult(
        prioritization_id="p",
        ranked=[rc],
        tier_lists=[TierList(tier="T2", candidates=[rc])],
        validation_errors=[],
    )
    md = render_prioritization_markdown(pr)
    assert "| A\\|B | Y\\|Z |" in md
    assert "### A\\|B — Y\\|Z (`c\\|x`)" in md


def test_run_prioritization_mocks_llm_and_retrieval() -> None:
    plan = PlanOut(
        subquestions=["q"],
        web_queries=["w"],
        paper_queries=["p"],
        evidence_requirements=["e"],
    )
    evidence = [
        _ev(
            id="e1",
            title="trial field biological",
            abstract_or_snippet="dataset platform",
            score=2.0,
        )
    ]
    candidates = [
        CropUseCaseCandidate(candidate_id="c1", crop="Wheat", use_case="x"),
    ]

    class _LLM:
        def json_response(self, **_: object) -> dict:
            return {
                "rationales": [
                    {
                        "candidate_id": "c1",
                        "claims": [
                            {
                                "text": "Strong retrieval match for wheat use case.",
                                "evidence_ids": ["e1"],
                                "evidence_urls": [],
                                "support": "direct",
                            }
                        ],
                    }
                ]
            }

    class _Agent:
        top_k_evidence = 25
        llm = _LLM()

        def plan(self, *_a: object, **_k: object) -> PlanOut:
            return plan

        def collect_evidence(self, *_a: object, **_k: object) -> list[EvidenceItem]:
            return evidence

    res, p, ev = run_prioritization(_Agent(), "task", InputVars(topic="t", source_urls=[]), candidates)
    assert p == plan
    assert ev == evidence
    assert res.ranked[0].rationale_claims[0].evidence_ids == ["e1"]
    assert not res.validation_errors
    md = render_prioritization_markdown(res)
    assert "Wheat" in md and "e1" in md


def test_run_prioritization_invalid_evidence_id_in_claim() -> None:
    plan = PlanOut(subquestions=[], web_queries=[], paper_queries=[], evidence_requirements=[])
    evidence = [_ev(id="e1")]

    class _LLM:
        def json_response(self, **_: object) -> dict:
            return {
                "rationales": [
                    {
                        "candidate_id": "c1",
                        "claims": [{"text": "bad", "evidence_ids": ["nope"], "evidence_urls": [], "support": "direct"}],
                    }
                ]
            }

    class _Agent:
        top_k_evidence = 25
        llm = _LLM()

        def plan(self, *_a: object, **_k: object) -> PlanOut:
            return plan

        def collect_evidence(self, *_a: object, **_k: object) -> list[EvidenceItem]:
            return evidence

    res, _, _ = run_prioritization(
        _Agent(),
        "t",
        InputVars(topic="t", source_urls=[]),
        [CropUseCaseCandidate(candidate_id="c1", crop="W", use_case="u")],
    )
    assert res.validation_errors
    assert not res.ranked[0].rationale_claims


def test_prioritize_cli_stdout_redaction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from research_agent.cli import prioritize as cli_prioritize

    task = tmp_path / "task.json"
    task.write_text(
        json.dumps({"task_prompt": "x", "input_vars": {"topic": "t", "source_urls": []}}),
        encoding="utf-8",
    )
    cand_path = tmp_path / "c.json"
    cand_path.write_text(
        json.dumps([{"candidate_id": "c1", "crop": "Wheat", "use_case": "u"}]),
        encoding="utf-8",
    )
    prio = PrioritizationResult(
        prioritization_id="prio-x",
        ranked=[],
        tier_lists=[],
        validation_errors=[],
    )
    payload = {
        "plan": {"subquestions": [], "web_queries": [], "paper_queries": [], "evidence_requirements": []},
        "evidence": [{"id": "e1", "source_type": "web", "retrieval_method": "t", "title": "t", "url": "http://x"}],
        "evidence_full": [{"id": "e1", "source_type": "web", "retrieval_method": "t", "title": "t", "url": "http://x"}],
        "prioritization": prio.model_dump(mode="json"),
        "validation_errors": [],
        "iterations": 1,
    }

    class _DummyAgent:
        def __init__(self, **_: object) -> None:
            pass

        def run_prioritization(self, *_a: object, **_k: object) -> dict:
            return payload

    class _DummyLLM:
        pass

    monkeypatch.setattr("research_agent.agent.llm.LLMClient", _DummyLLM)
    monkeypatch.setattr("research_agent.agent.research.ResearchAgent", _DummyAgent)
    monkeypatch.setattr(
        "sys.argv",
        ["research-agent-prioritize", "--task-file", str(task), "--candidates", str(cand_path)],
    )

    assert cli_prioritize.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert "evidence" not in out
    assert out["evidence_count"] == 1


def test_research_agent_run_prioritization_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    from research_agent.agent.research import ResearchAgent

    called: dict[str, object] = {}

    def _fake(
        agent: object,
        task_prompt: str,
        input_vars: InputVars,
        candidates: list[CropUseCaseCandidate],
        *,
        weights: tuple[float, float, float, float] = (0.25, 0.25, 0.25, 0.25),
        top_k_evidence: int | None = None,
    ) -> tuple[PrioritizationResult, PlanOut, list[EvidenceItem]]:
        called["task"] = task_prompt
        called["n"] = len(candidates)
        pr = PrioritizationResult(prioritization_id="p", ranked=[], tier_lists=[], validation_errors=[])
        plan = PlanOut(subquestions=[], web_queries=[], paper_queries=[], evidence_requirements=[])
        return pr, plan, []

    monkeypatch.setattr("research_agent.agent.prioritization.run_prioritization", _fake)
    agent = ResearchAgent.__new__(ResearchAgent)
    agent.top_k_evidence = 25
    out = ResearchAgent.run_prioritization(
        agent,
        "hello",
        InputVars(topic="t", source_urls=[]),
        [CropUseCaseCandidate(candidate_id="a", crop="W", use_case="u")],
    )
    assert called["task"] == "hello"
    assert called["n"] == 1
    assert "prioritization" in out
