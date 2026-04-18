from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from research_agent.agent.research import ResearchAgent
from research_agent.agent.schemas import GapQueries
from research_agent.contracts.agronomy.dossier import CropDossier, LifecycleStage
from research_agent.contracts.core.artifact_meta import ArtifactMeta
from research_agent.contracts.core.questionnaire import (
    QuestionAnswer,
    QuestionnaireCoverage,
    QuestionnaireExecutionResult,
    QuestionnaireResponseSet,
    QuestionnaireSpec,
    QuestionSpec,
)
from research_agent.types import EvidenceItem, InputVars, PlanOut


def _dossier() -> CropDossier:
    now = datetime.now(timezone.utc)
    return CropDossier(
        meta=ArtifactMeta(artifact_id="d", artifact_type="crop_dossier", created_at=now, updated_at=now),
        crop_name="Wheat",
        crop_category="cereal",
        primary_use_cases=["x"],
        priority_tier="T1",
        last_updated=date.today(),
        lifecycle_ontology=[LifecycleStage(stage="Pre-plant", description="")],
    )


def _spec() -> QuestionnaireSpec:
    return QuestionnaireSpec(
        questionnaire_id="qi",
        domain="d",
        version="1",
        questions=[
            QuestionSpec(id="q1", category="c", prompt_template="{a}", variables=["a"]),
        ],
    )


def test_run_questionnaire_no_insufficient_stops_after_one_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    from research_agent.agent import research as research_mod

    plan = PlanOut(subquestions=[], web_queries=[], paper_queries=[], evidence_requirements=[])
    ev = EvidenceItem(
        id="e1",
        source_type="web",
        retrieval_method="t",
        title="t",
        url="http://example.com",
    )
    spec = _spec()
    dossier = _dossier()

    def fake_pass(*_: object, **__: object) -> QuestionnaireExecutionResult:
        return QuestionnaireExecutionResult(
            responses=QuestionnaireResponseSet(
                questionnaire_id=spec.questionnaire_id,
                subject_id="s",
                responses=[
                    QuestionAnswer(question_id="q1", status="answered", answer_markdown="ok"),
                ],
            ),
            coverage=QuestionnaireCoverage(
                total=1,
                applicable=1,
                answered=1,
                insufficient_evidence=0,
                not_applicable=0,
                coverage_ratio=1.0,
            ),
            stop_reason="first_pass",
        )

    monkeypatch.setattr(research_mod, "run_questionnaire_pass", fake_pass)

    class _LLM:
        pass

    agent = ResearchAgent(llm=_LLM())  # type: ignore[arg-type]
    monkeypatch.setattr(agent, "plan", lambda *_a, **_k: plan)
    monkeypatch.setattr(agent, "collect_evidence", lambda *_a, **_k: [ev])

    out = agent.run_questionnaire(
        "task",
        InputVars(topic="t"),
        dossier,
        spec,
        {"a": "v"},
    )
    assert out["iterations"] == 1
    assert out["questionnaire"]["stop_reason"] == "all_answered_or_no_insufficient"


def test_run_questionnaire_gap_fill_second_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    from research_agent.agent import research as research_mod

    plan = PlanOut(subquestions=[], web_queries=[], paper_queries=[], evidence_requirements=[])
    ev = EvidenceItem(
        id="e1",
        source_type="web",
        retrieval_method="t",
        title="t",
        url="http://example.com",
    )
    spec = _spec()
    dossier = _dossier()
    n = {"v": 0}

    def fake_pass(*_: object, **__: object) -> QuestionnaireExecutionResult:
        n["v"] += 1
        if n["v"] == 1:
            return QuestionnaireExecutionResult(
                responses=QuestionnaireResponseSet(
                    questionnaire_id=spec.questionnaire_id,
                    subject_id="s",
                    responses=[
                        QuestionAnswer(question_id="q1", status="insufficient_evidence", answer_markdown=""),
                    ],
                ),
                coverage=QuestionnaireCoverage(
                    total=1,
                    applicable=1,
                    answered=0,
                    insufficient_evidence=1,
                    not_applicable=0,
                    coverage_ratio=0.0,
                ),
                stop_reason="first_pass",
            )
        return QuestionnaireExecutionResult(
            responses=QuestionnaireResponseSet(
                questionnaire_id=spec.questionnaire_id,
                subject_id="s",
                responses=[
                    QuestionAnswer(question_id="q1", status="answered", answer_markdown="ok"),
                ],
            ),
            coverage=QuestionnaireCoverage(
                total=1,
                applicable=1,
                answered=1,
                insufficient_evidence=0,
                not_applicable=0,
                coverage_ratio=1.0,
            ),
            stop_reason="after_gap_fill",
        )

    monkeypatch.setattr(research_mod, "run_questionnaire_pass", fake_pass)

    class _LLM:
        pass

    agent = ResearchAgent(llm=_LLM())  # type: ignore[arg-type]
    monkeypatch.setattr(agent, "plan", lambda *_a, **_k: plan)
    monkeypatch.setattr(agent, "collect_evidence", lambda *_a, **_k: [ev])
    monkeypatch.setattr(agent, "collect_incremental_evidence", lambda *_a, **_k: [ev])
    monkeypatch.setattr(
        agent,
        "gap_queries",
        lambda *_a, **_k: GapQueries(web_queries=["gap"], paper_queries=[]),
    )

    out = agent.run_questionnaire("task", InputVars(topic="t"), dossier, spec, {"a": "v"})
    assert out["iterations"] == 2
    assert n["v"] == 2
    assert out["questionnaire"]["responses"]["responses"][0]["status"] == "answered"


def test_run_questionnaire_no_gap_queries_no_second_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    from research_agent.agent import research as research_mod

    plan = PlanOut(subquestions=[], web_queries=[], paper_queries=[], evidence_requirements=[])
    ev = EvidenceItem(
        id="e1",
        source_type="web",
        retrieval_method="t",
        title="t",
        url="http://example.com",
    )
    spec = _spec()
    dossier = _dossier()
    n = {"v": 0}

    def fake_pass(*_: object, **__: object) -> QuestionnaireExecutionResult:
        n["v"] += 1
        return QuestionnaireExecutionResult(
            responses=QuestionnaireResponseSet(
                questionnaire_id=spec.questionnaire_id,
                subject_id="s",
                responses=[
                    QuestionAnswer(question_id="q1", status="insufficient_evidence", answer_markdown=""),
                ],
            ),
            coverage=QuestionnaireCoverage(
                total=1,
                applicable=1,
                answered=0,
                insufficient_evidence=1,
                not_applicable=0,
                coverage_ratio=0.0,
            ),
            stop_reason="first_pass",
        )

    monkeypatch.setattr(research_mod, "run_questionnaire_pass", fake_pass)

    class _LLM:
        pass

    agent = ResearchAgent(llm=_LLM())  # type: ignore[arg-type]
    monkeypatch.setattr(agent, "plan", lambda *_a, **_k: plan)
    monkeypatch.setattr(agent, "collect_evidence", lambda *_a, **_k: [ev])
    monkeypatch.setattr(agent, "gap_queries", lambda *_a, **_k: GapQueries(web_queries=[], paper_queries=[]))

    out = agent.run_questionnaire("task", InputVars(topic="t"), dossier, spec, {"a": "v"})
    assert out["iterations"] == 1
    assert n["v"] == 1
    assert out["questionnaire"]["stop_reason"] == "no_gap_queries"
