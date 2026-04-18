from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_agent.cli import research as cli_research


def _task_file(tmp_path: Path, *, with_dossier: bool) -> Path:
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


def test_questionnaire_requires_vars(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    task = _task_file(tmp_path, with_dossier=True)
    spec = tmp_path / "q.json"
    spec.write_text(
        json.dumps(
            {
                "questionnaire_id": "x",
                "domain": "d",
                "version": "1",
                "questions": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["research-agent", "--dossier", "--task-file", str(task), "--questionnaire-spec", str(spec)],
    )
    with pytest.raises(SystemExit) as exc:
        cli_research.main()
    assert exc.value.code == 2


def test_questionnaire_requires_dossier_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    task = _task_file(tmp_path, with_dossier=True)
    spec = tmp_path / "q.json"
    spec.write_text(
        json.dumps(
            {
                "questionnaire_id": "x",
                "domain": "d",
                "version": "1",
                "questions": [],
            }
        ),
        encoding="utf-8",
    )
    vars_path = tmp_path / "vars.json"
    vars_path.write_text(json.dumps({"crop": "Wheat"}), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "research-agent",
            "--final-report",
            "--task-file",
            str(task),
            "--questionnaire-spec",
            str(spec),
            "--questionnaire-vars",
            str(vars_path),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli_research.main()
    assert exc.value.code == 2


def test_questionnaire_render_md_requires_spec(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    task = _task_file(tmp_path, with_dossier=True)
    monkeypatch.setattr(
        "sys.argv",
        ["research-agent", "--dossier", "--task-file", str(task), "--questionnaire-render-md", "out.md"],
    )
    with pytest.raises(SystemExit) as exc:
        cli_research.main()
    assert exc.value.code == 2
