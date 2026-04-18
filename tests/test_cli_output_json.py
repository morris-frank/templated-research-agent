from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_agent.cli import research as cli_research


def _task_file(tmp_path: Path) -> Path:
    path = tmp_path / "task.json"
    path.write_text(json.dumps({"task_prompt": "x", "input_vars": {"topic": "t", "source_urls": []}}), encoding="utf-8")
    return path


def _ev(id_: str) -> dict:
    return {
        "id": id_,
        "source_type": "web",
        "retrieval_method": "t",
        "title": "t",
        "url": "http://example.com",
    }


def test_stdout_omits_evidence_lists(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    task = _task_file(tmp_path)
    payload = {
        "plan": {"subquestions": [], "web_queries": [], "paper_queries": [], "evidence_requirements": []},
        "evidence": [_ev("e1")],
        "evidence_full": [_ev("e1"), _ev("e2")],
        "final": {},
        "validation_errors": [],
        "iterations": 1,
    }

    class _DummyAgent:
        def __init__(self, **_: object) -> None:
            pass

        def run(self, *_a: object, **_k: object) -> dict:
            return payload

    class _DummyLLM:
        pass

    monkeypatch.setattr("research_agent.agent.llm.LLMClient", _DummyLLM)
    monkeypatch.setattr("research_agent.agent.research.ResearchAgent", _DummyAgent)
    monkeypatch.setattr("sys.argv", ["research-agent", "--task-file", str(task)])

    assert cli_research.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert "evidence" not in out
    assert "evidence_full" not in out
    assert out["evidence_count"] == 1
    assert out["evidence_full_count"] == 2


def test_output_json_writes_full_result(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    task = _task_file(tmp_path)
    out_path = tmp_path / "full.json"
    payload = {
        "plan": {"subquestions": [], "web_queries": [], "paper_queries": [], "evidence_requirements": []},
        "evidence": [_ev("e1")],
        "evidence_full": [_ev("e1")],
        "final": {},
        "validation_errors": [],
        "iterations": 1,
    }

    class _DummyAgent:
        def __init__(self, **_: object) -> None:
            pass

        def run(self, *_a: object, **_k: object) -> dict:
            return payload

    class _DummyLLM:
        pass

    monkeypatch.setattr("research_agent.agent.llm.LLMClient", _DummyLLM)
    monkeypatch.setattr("research_agent.agent.research.ResearchAgent", _DummyAgent)
    monkeypatch.setattr(
        "sys.argv",
        ["research-agent", "--task-file", str(task), "--output-json", str(out_path)],
    )

    assert cli_research.main() == 0
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(written["evidence"]) == 1
    assert written["evidence"][0]["id"] == "e1"
    stdout = json.loads(capsys.readouterr().out)
    assert "evidence" not in stdout
