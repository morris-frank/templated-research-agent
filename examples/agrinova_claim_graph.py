from __future__ import annotations

import json
import sys
from pathlib import Path

from research_agent.contracts.core.claim_graph import validate_claim_graph
from research_agent.contracts.examples import build_agrinova_demo_bundle
from research_agent.contracts.renderers.markdown import render_final_projection_markdown


def main() -> None:
    bundle = build_agrinova_demo_bundle()
    errors = validate_claim_graph(bundle)
    if errors:
        print("Validation errors:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        raise SystemExit(1)
    out_dir = Path(__file__).resolve().parent / "generated"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "agrinova.claim_graph.json").write_text(
        json.dumps(bundle.model_dump(mode="json"), indent=2, default=str),
        encoding="utf-8",
    )
    (out_dir / "agrinova.projection.md").write_text(
        render_final_projection_markdown(bundle.output, bundle),
        encoding="utf-8",
    )
    print(f"Agrinova claim graph valid; wrote {out_dir / 'agrinova.claim_graph.json'}")


if __name__ == "__main__":
    main()
