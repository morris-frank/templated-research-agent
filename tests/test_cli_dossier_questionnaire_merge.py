"""CLI-level smoke: dossier + questionnaire merge matches questionnaire evidence and reuse flag."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from research_agent.cli import research as cli_research
from research_agent.contracts.agronomy.dossier import CropDossier, LifecycleStage
from research_agent.contracts.core.artifact_meta import ArtifactMeta


def _ev(id_: str) -> dict:
    return {
        "id": id_,
        "source_type": "web",
        "retrieval_method": "t",
        "title": "t",
        "url": "http://example.com",
    }


def test_cli_dossier_questionnaire_merges_evidence_and_sets_reuse_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task = tmp_path / "task.json"
    task.write_text(
        json.dumps(
            {
                "task_prompt": "x",
                "input_vars": {"topic": "t", "source_urls": []},
                "dossier_input": {
                    "crop_name": "Wheat",
                    "crop_category": "cereal",
                    "primary_use_cases": ["u"],
                    "priority_tier": "T1",
                },
            }
        ),
        encoding="utf-8",
    )
    spec = tmp_path / "q.json"
    spec.write_text(
        json.dumps(
            {
                "questionnaire_id": "qid",
                "domain": "d",
                "version": "1",
                "questions": [],
            }
        ),
        encoding="utf-8",
    )
    vars_path = tmp_path / "vars.json"
    vars_path.write_text(json.dumps({}), encoding="utf-8")

    now = datetime.now(timezone.utc)
    dossier_obj = CropDossier(
        meta=ArtifactMeta(artifact_id="d1", artifact_type="crop_dossier", created_at=now, updated_at=now),
        crop_name="Wheat",
        crop_category="cereal",
        primary_use_cases=["u"],
        priority_tier="T1",
        last_updated=date.today(),
        lifecycle_ontology=[LifecycleStage(stage="Pre-plant", description="")],
    )
    dossier_dict = dossier_obj.model_dump(mode="json")
    plan = {"subquestions": [], "web_queries": [], "paper_queries": [], "evidence_requirements": []}
    dossier_ev = [_ev("d1"), _ev("d2")]
    q_ev = [_ev("q1")]
    q_full = [_ev("q1"), _ev("q2")]

    q_questionnaire = {
        "responses": {
            "questionnaire_id": "qid",
            "subject_id": "Wheat__qid",
            "responses": [],
        },
        "coverage": {
            "total": 0,
            "applicable": 0,
            "answered": 0,
            "insufficient_evidence": 0,
            "not_applicable": 0,
            "coverage_ratio": 1.0,
        },
        "skipped_questions": [],
        "stop_reason": "first_pass",
        "evidence_validation_errors": [],
    }

    class _DummyAgent:
        def __init__(self, **_: object) -> None:
            pass

        def run_dossier(self, *_a: object, **_k: object) -> dict:
            return {
                "plan": plan,
                "evidence": dossier_ev,
                "evidence_full": dossier_ev,
                "dossier": dossier_dict,
                "validation_errors": [],
                "iterations": 1,
            }

        def run_questionnaire(self, *_a: object, **_k: object) -> dict:
            return {
                "plan": plan,
                "evidence": q_ev,
                "evidence_full": q_full,
                "dossier": dossier_dict,
                "questionnaire": q_questionnaire,
                "validation_errors": [],
                "questionnaire_evidence_validation_errors": [],
                "iterations": 1,
                "reused_retrieval_substrate": True,
            }

    class _DummyLLM:
        pass

    monkeypatch.setattr("research_agent.agent.llm.LLMClient", _DummyLLM)
    monkeypatch.setattr("research_agent.agent.research.ResearchAgent", _DummyAgent)
    monkeypatch.setattr(
        "sys.argv",
        [
            "research-agent",
            "--dossier",
            "--task-file",
            str(task),
            "--questionnaire-spec",
            str(spec),
            "--questionnaire-vars",
            str(vars_path),
            "--output-json",
            str(tmp_path / "full.json"),
        ],
    )

    assert cli_research.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["questionnaire_reused_dossier_retrieval"] is True
    assert out["evidence_count"] == 1
    assert out["evidence_full_count"] == 2
    full = json.loads((tmp_path / "full.json").read_text(encoding="utf-8"))
    assert [e["id"] for e in full["evidence"]] == ["q1"]
    assert [e["id"] for e in full["evidence_full"]] == ["q1", "q2"]
