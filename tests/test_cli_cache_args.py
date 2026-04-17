from __future__ import annotations

import json
from pathlib import Path

from research_agent.cli import research as cli_research


def _task_file(tmp_path: Path) -> Path:
    path = tmp_path / "task.json"
    path.write_text(json.dumps({"task_prompt": "x", "input_vars": {"topic": "t", "source_urls": []}}), encoding="utf-8")
    return path


def test_cli_parses_cache_mode_and_dir(monkeypatch, tmp_path: Path) -> None:
    task = _task_file(tmp_path)
    captured = {}

    class _DummyAgent:
        def __init__(self, **kwargs):
            captured["cache_settings"] = kwargs.get("cache_settings")

        def run(self, *_: object, **__: object) -> dict:
            return {"plan": {}, "evidence": [], "final": {}, "validation_errors": [], "iterations": 1}

    class _DummyLLM:
        pass

    monkeypatch.setattr("research_agent.agent.llm.LLMClient", _DummyLLM)
    monkeypatch.setattr("research_agent.agent.research.ResearchAgent", _DummyAgent)
    monkeypatch.setattr(
        "sys.argv",
        [
            "research-agent",
            "--task-file",
            str(task),
            "--cache-mode",
            "off",
            "--cache-dir",
            str(tmp_path / "cache"),
        ],
    )
    assert cli_research.main() == 0
    settings = captured["cache_settings"]
    assert settings.mode == "off"
    assert settings.cache_dir == str(tmp_path / "cache")

