from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from research_agent.contracts.agronomy.dossier import (
    CropDossier,
    Intervention,
    InterventionEffect,
    LifecycleStage,
    Pathogen,
    YieldDriver,
)
from research_agent.contracts.core.claims import Claim
from research_agent.contracts.agronomy.synthesis import SynthesisOutput
from research_agent.contracts.core.artifact_meta import ArtifactMeta
from research_agent.synthesis.pipeline import load_manifest, resolve_safe_path, run_synthesis


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
    m_loaded, base = load_manifest(tmp_path / "manifest.json")
    out = run_synthesis(manifest=m_loaded, base_path=base)
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


def test_resolve_safe_path_rejects_traversal(tmp_path: Path) -> None:
    (tmp_path / "x.json").write_text("{}", encoding="utf-8")
    assert resolve_safe_path(tmp_path, "x.json").name == "x.json"
    with pytest.raises(ValueError, match="escape"):
        resolve_safe_path(tmp_path, "../outside")


def test_synthesis_id_same_for_identical_payloads_different_dirs(tmp_path: Path) -> None:
    d1 = _dossier_with_pathogen("Wheat", "Fusarium")
    d2 = _dossier_with_pathogen("Maize", "Fusarium")
    manifest_body = {
        "runs": [
            {"run_id": "wheat", "dossier": "w.json"},
            {"run_id": "maize", "dossier": "m.json"},
        ],
        "min_crops_for_pattern": 2,
    }
    ids: list[str] = []
    for name in ("dir_a", "dir_b"):
        d = tmp_path / name
        d.mkdir()
        (d / "w.json").write_text(json.dumps(d1.model_dump(mode="json")), encoding="utf-8")
        (d / "m.json").write_text(json.dumps(d2.model_dump(mode="json")), encoding="utf-8")
        (d / "manifest.json").write_text(json.dumps(manifest_body), encoding="utf-8")
        m_loaded, base = load_manifest(d / "manifest.json")
        ids.append(run_synthesis(manifest=m_loaded, base_path=base).synthesis_id)
    assert ids[0] == ids[1]


def test_manifest_accepts_inputs_alias(tmp_path: Path) -> None:
    d = _dossier_with_pathogen("Wheat", "Fusarium")
    (tmp_path / "w.json").write_text(json.dumps(d.model_dump(mode="json")), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "inputs": [{"run_id": "wheat", "dossier": "w.json"}],
                "min_crops_for_pattern": 1,
            }
        ),
        encoding="utf-8",
    )
    m_loaded, _ = load_manifest(tmp_path / "manifest.json")
    assert len(m_loaded.runs) == 1


def test_ontology_edges_from_dossier_links(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    mech = Claim(text="mechanism", evidence_ids=[])
    dossier = CropDossier(
        meta=ArtifactMeta(artifact_id="x", artifact_type="crop_dossier", created_at=now, updated_at=now),
        crop_name="Wheat",
        crop_category="cereal",
        primary_use_cases=["u"],
        priority_tier="T1",
        last_updated=date.today(),
        lifecycle_ontology=[LifecycleStage(stage="Pre-plant", description="")],
        yield_drivers=[YieldDriver(id="yd1", name="Grain fill", mechanism=mech, evidence_ids=[])],
        interventions=[Intervention(id="i1", kind="management", name="Fungicide", evidence_ids=[])],
        intervention_effects=[
            InterventionEffect(intervention_id="i1", target_ref="yd1", effect="increase", rationale=mech)
        ],
        pathogens=[Pathogen(id="p1", name="Rust", affected_stages=["Pre-plant"])],
    )
    (tmp_path / "one.json").write_text(json.dumps(dossier.model_dump(mode="json")), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"runs": [{"run_id": "wheat", "dossier": "one.json"}], "min_crops_for_pattern": 1}),
        encoding="utf-8",
    )
    m_loaded, base = load_manifest(tmp_path / "manifest.json")
    out = run_synthesis(manifest=m_loaded, base_path=base)
    rels = {e.relation for e in out.ontology_edges}
    assert "observed_in_stage" in rels
    assert "targets" in rels
