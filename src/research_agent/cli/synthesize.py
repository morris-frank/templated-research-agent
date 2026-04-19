"""CLI: cross-crop synthesis from a manifest of dossier (+ optional questionnaire) JSON paths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_agent.contracts.renderers.markdown import render_synthesis_markdown
from research_agent.synthesis.pipeline import load_manifest, run_synthesis


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic synthesis over CropDossier + optional QuestionnaireExecutionResult JSON files.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--inputs-manifest",
        type=str,
        metavar="PATH",
        help="JSON manifest with runs[] (run_id, dossier path, optional questionnaire path, optional prioritization_context)",
    )
    group.add_argument(
        "--input-dir",
        type=str,
        metavar="DIR",
        help="Directory containing manifest.json (same schema as --inputs-manifest)",
    )
    parser.add_argument("--output-json", type=str, metavar="PATH", help="Write SynthesisOutput JSON")
    parser.add_argument("--render-markdown", type=str, metavar="PATH", help="Write synthesis markdown summary")
    args = parser.parse_args()

    manifest_path = Path(args.inputs_manifest) if args.inputs_manifest else Path(args.input_dir) / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    manifest, base = load_manifest(manifest_path)
    result = run_synthesis(manifest=manifest, base_path=base)

    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if args.render_markdown:
        Path(args.render_markdown).write_text(render_synthesis_markdown(result), encoding="utf-8")
    print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
