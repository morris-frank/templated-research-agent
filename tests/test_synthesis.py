from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from research_agent.contracts.agronomy.dossier import CropDossier, LifecycleStage, Pathogen
from research_agent.contracts.agronomy.synthesis import SynthesisOutput
from research_agent.contracts.core.artifact_meta import ArtifactMeta
from research_agent.synthesis.pipeline import load_manifest, run_synthesis


def _dossier_with_pathogen(crop: str, pathogen_name: str) -> CropDossier:
    now = datetime.now(timezone.utc)
    return CropDossier(
        meta=ArtifactMeta(artifact_id="x", artifact_type="crop_dossier", created_at=now, updated_at=now),
        crop_name=crop,
        crop_category="cereal",
        primary_use_cases=["u"],
        priority_tier="T1",
        last_updated=date.today(),
        lifecycle_ontology=[LifecycleStage(stage="Pre-plant", description="")],
        pathogens=[Pathogen(id="p1", name=pathogen_name)],
    )


def test_synthesis_output_json_roundtrip() -> None:
    out = SynthesisOutput(synthesis_id="s1", cross_crop_patterns=[], normalized_concepts=[])
    raw = json.loads(json.dumps(out.model_dump(mode="json")))
    assert SynthesisOutput.model_validate(raw).synthesis_id == "s1"


def test_run_synthesis_finds_cross_crop_pathogen(tmp_path: Path) -> None:
    d1 = _dossier_with_pathogen("Wheat", "Fusarium")
    d2 = _dossier_with_pathogen("Maize", "Fusarium")
    (tmp_path / "w.json").write_text(json.dumps(d1.model_dump(mode="json")), encoding="utf-8")
    (tmp_path / "m.json").write_text(json.dumps(d2.model_dump(mode="json")), encoding="utf-8")
    manifest = {
        "runs": [
            {"run_id": "wheat", "dossier": "w.json"},
            {"run_id": "maize", "dossier": "m.json"},
        ],
        "min_crops_for_pattern": 2,
        "min_mentions": 1,
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    runs, base, mc, mm = load_manifest(tmp_path / "manifest.json")
    out = run_synthesis(runs=runs, base_path=base, min_crops_for_pattern=mc, min_mentions=mm)
    kinds = {p.kind for p in out.cross_crop_patterns}
    assert "pathogen" in kinds
    assert any("fusarium" in p.normalized_label.lower() for p in out.cross_crop_patterns)


def test_synthesis_imports_do_not_load_retrieval_sources() -> None:
    code = """
import sys
import research_agent.contracts.agronomy.synthesis as s
import research_agent.synthesis as syn
assert hasattr(s, "SynthesisOutput")
assert "research_agent.retrieval.sources" not in sys.modules
"""
    repo = Path(__file__).resolve().parents[1]
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr + r.stdout


def test_synthesize_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from research_agent.cli import synthesize as cli_syn

    d1 = _dossier_with_pathogen("Wheat", "X")
    (tmp_path / "a.json").write_text(json.dumps(d1.model_dump(mode="json")), encoding="utf-8")
    (tmp_path / "b.json").write_text(
        json.dumps(_dossier_with_pathogen("Barley", "X").model_dump(mode="json")),
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "runs": [
                    {"run_id": "a", "dossier": "a.json"},
                    {"run_id": "b", "dossier": "b.json"},
                ],
                "min_crops_for_pattern": 2,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["research-agent-synthesize", "--inputs-manifest", str(tmp_path / "manifest.json")],
    )
    assert cli_syn.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["synthesis_id"].startswith("syn-")
