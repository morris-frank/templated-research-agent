from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_agent.cli import research as cli_research


def _task_file(tmp_path: Path, with_dossier: bool) -> Path:
    data = {
        "task_prompt": "x",
        "input_vars": {"topic": "t", "source_urls": []},
    }
    if with_dossier:
        data["dossier_input"] = {
            "crop_name": "Wheat",
            "crop_category": "cereal",
            "primary_use_cases": ["u"],
            "priority_tier": "T1",
        }
    path = tmp_path / "task.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_mutex_final_report_and_dossier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["research-agent", "--final-report", "--dossier", "--demo"])
    with pytest.raises(SystemExit) as exc:
        cli_research.main()
    assert exc.value.code == 2


def test_dossier_requires_dossier_input_when_task_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    task = _task_file(tmp_path, with_dossier=False)
    monkeypatch.setattr("sys.argv", ["research-agent", "--dossier", "--task-file", str(task)])
    with pytest.raises(SystemExit) as exc:
        cli_research.main()
    assert exc.value.code == 2


def test_dossier_and_claim_graph_parse(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    task = _task_file(tmp_path, with_dossier=True)

    class _DummyAgent:
        def __init__(self, **_: object) -> None:
            pass

        def run_dossier(self, *_: object, **__: object) -> dict:
            return {
                "plan": {"subquestions": [], "web_queries": [], "paper_queries": [], "evidence_requirements": []},
                "evidence": [],
                "dossier": {},
                "validation_errors": [],
                "iterations": 1,
            }

        def compose_claim_graph_from(self, *_: object, **__: object) -> dict:
            return {"claim_graph": {}, "validation_errors": []}

    class _DummyLLM:
        pass

    monkeypatch.setattr("research_agent.agent.llm.LLMClient", _DummyLLM)
    monkeypatch.setattr("research_agent.agent.research.ResearchAgent", _DummyAgent)
    monkeypatch.setattr("sys.argv", ["research-agent", "--dossier", "--claim-graph", "--task-file", str(task)])
    assert cli_research.main() == 0

