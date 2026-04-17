from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from research_agent.contracts.core.claim_graph import ClaimGraphBundle, validate_claim_graph_detailed
from research_agent.contracts.examples import build_agrinova_demo_bundle
from research_agent.contracts.renderers.markdown import render_final_projection_markdown


def read_bundle(path: Path) -> ClaimGraphBundle:
    return ClaimGraphBundle.model_validate_json(path.read_text(encoding="utf-8"))


def load_bundle_from_args(args: argparse.Namespace) -> ClaimGraphBundle:
    if args.demo:
        return build_agrinova_demo_bundle()
    if args.input_json:
        return read_bundle(args.input_json)
    raise SystemExit("Provide either --demo or --input-json PATH")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate, render, and export claim graph bundles (no demo construction here).",
    )
    parser.add_argument("--demo", action="store_true", help="Load the canonical Agrinova demo from the package.")
    parser.add_argument("--input-json", type=Path, help="Path to a ClaimGraphBundle JSON file.")
    parser.add_argument("--validate-only", action="store_true", help="Validate the bundle and exit.")
    parser.add_argument("--render-markdown", type=Path, help="Render report markdown to this path.")
    parser.add_argument(
        "--render-style",
        choices=("customer", "debug"),
        default="customer",
        help="Markdown layout for --render-markdown / default stdout.",
    )
    parser.add_argument("--write-json", type=Path, help="Write the bundle JSON to this path.")
    parser.add_argument("--print-summary", action="store_true", help="Print a concise summary to stdout.")
    args = parser.parse_args()

    if not args.demo and not args.input_json:
        parser.error("Pass --demo or --input-json PATH")

    try:
        bundle = load_bundle_from_args(args)
    except ValidationError as exc:
        print(exc, file=sys.stderr)
        return 2

    report = validate_claim_graph_detailed(bundle)

    if args.write_json:
        args.write_json.write_text(
            json.dumps(bundle.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    if args.render_markdown:
        args.render_markdown.write_text(
            render_final_projection_markdown(bundle.output, bundle, style=args.render_style),
            encoding="utf-8",
        )

    if args.print_summary:
        print(
            json.dumps(
                {
                    "claims": len(bundle.claims),
                    "evidence_records": len(bundle.evidence_records),
                    "claim_evidence_links": len(bundle.claim_evidence_links),
                    "claim_dependency_links": len(bundle.claim_dependency_links),
                    "ok": report.ok,
                    "error_count": len(report.errors),
                },
                indent=2,
            )
        )

    if report.errors:
        print(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))

    if args.validate_only:
        return 0 if report.ok else 1

    if not args.print_summary and not args.render_markdown and not args.write_json:
        print(render_final_projection_markdown(bundle.output, bundle, style=args.render_style), end="")

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
