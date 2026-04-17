from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research_agent.contracts.agronomy.input import DossierInputVars
from research_agent.contracts.renderers.markdown import render_crop_dossier_markdown
from research_agent.retrieval.cache import CacheSettings
from research_agent.types import InputVars


def demo_payload() -> tuple[str, InputVars, DossierInputVars]:
    task_prompt = (
        "Produce a concise structured research brief on cereal metagenomics and soil/arable crop residue context. "
        "Use current web context plus scientific literature. Mention limits explicitly."
    )
    input_vars = InputVars(
        topic="cereal metagenomics and soil microbiome context",
        company="Example AgTech",
        region="EU",
        source_urls=[
            "https://www.mdpi.com/2076-2607/12/3/510",
            "https://www.science.org/doi/10.1126/science.aap9516",
            "https://research.wur.nl/en/publications/reference-values-for-arable-crop-residues-organic-matter-and-cn-r/",
        ],
    )
    dossier_input = DossierInputVars(
        crop_name="Wheat",
        crop_category="cereal",
        primary_use_cases=["pathogen panel", "input optimization"],
        priority_tier="T1",
        use_case="integrated disease and soil management",
    )
    return task_prompt, input_vars, dossier_input


def load_task_file(path: str) -> tuple[str, InputVars, DossierInputVars | None]:
    with open(path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    dossier_input = DossierInputVars.model_validate(data["dossier_input"]) if "dossier_input" in data else None
    return data["task_prompt"], InputVars.model_validate(data["input_vars"]), dossier_input


def main() -> int:
    parser = argparse.ArgumentParser(description="Template-constrained research agent (retrieval + LLM draft).")
    parser.add_argument("--demo", action="store_true", help="Run the built-in demo payload")
    parser.add_argument("--task-file", type=str, help="Path to JSON file with task_prompt and input_vars")
    primary = parser.add_mutually_exclusive_group()
    primary.add_argument("--final-report", action="store_true", help="Primary output is FinalReport (default)")
    primary.add_argument("--dossier", action="store_true", help="Primary output is CropDossier")
    parser.add_argument(
        "--claim-graph",
        action="store_true",
        help="Also emit ClaimGraphBundle sidecar from same plan/evidence",
    )
    parser.add_argument("--render-markdown", type=str, help="Write rendered dossier markdown path (--dossier only)")
    parser.add_argument(
        "--cache-mode",
        choices=["default", "refresh", "off"],
        default="default",
        help="Retrieval cache behavior for this run",
    )
    parser.add_argument("--cache-dir", type=str, help="Optional retrieval cache directory override")
    args = parser.parse_args()

    if not args.demo and not args.task_file:
        parser.error("Pass --demo or --task-file")

    if args.demo:
        task_prompt, input_vars, dossier_input = demo_payload()
    else:
        task_prompt, input_vars, dossier_input = load_task_file(args.task_file)
        if args.dossier and dossier_input is None:
            parser.error("--dossier requires dossier_input in task file (unless --demo is used)")
    if args.render_markdown and not args.dossier:
        parser.error("--render-markdown is only valid with --dossier")

    from research_agent.agent.llm import LLMClient
    from research_agent.agent.research import ResearchAgent

    agent = ResearchAgent(
        llm=LLMClient(),
        cache_settings=CacheSettings(mode=args.cache_mode, cache_dir=args.cache_dir),
    )
    result = (
        agent.run_dossier(task_prompt, input_vars, dossier_input)
        if args.dossier
        else agent.run(task_prompt, input_vars)
    )
    if args.claim_graph:
        from research_agent.agent.schemas import EvidenceItem, PlanOut

        sidecar = agent.compose_claim_graph_from(
            task_prompt,
            input_vars,
            plan=PlanOut.model_validate(result["plan"]),
            evidence=[EvidenceItem.model_validate(e) for e in result["evidence"]],
        )
        result["claim_graph_sidecar"] = {
            "claim_graph": sidecar.get("claim_graph"),
            "validation_errors": sidecar.get("validation_errors", []),
        }
    if args.dossier and args.render_markdown:
        from research_agent.contracts.agronomy.dossier import CropDossier

        md = render_crop_dossier_markdown(CropDossier.model_validate(result["dossier"]))
        Path(args.render_markdown).write_text(md, encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
