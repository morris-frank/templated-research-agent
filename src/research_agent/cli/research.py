from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research_agent.contracts.agronomy.input import DossierInputVars
from research_agent.contracts.renderers.markdown import (
    render_crop_dossier_markdown,
    render_questionnaire_execution_markdown,
)
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


def _result_json_for_stdout(result: dict[str, Any]) -> dict[str, Any]:
    """Omit bulky evidence lists from CLI output; keep counts for visibility."""
    out = dict(result)
    if "evidence" in out:
        ev = out.pop("evidence")
        out["evidence_count"] = len(ev) if isinstance(ev, list) else 0
    if "evidence_full" in out:
        ef = out.pop("evidence_full")
        out["evidence_full_count"] = len(ef) if isinstance(ef, list) else 0
    return out


def load_questionnaire_spec(path: str):
    from research_agent.contracts.core.questionnaire import QuestionnaireSpec

    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as e:
            raise RuntimeError("YAML questionnaire specs require pyyaml; pip install 'research-agent[retrieval]'") from e
        return QuestionnaireSpec.model_validate(yaml.safe_load(text))
    return QuestionnaireSpec.model_validate(json.loads(text))


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
    parser.add_argument(
        "--output-json",
        type=str,
        metavar="PATH",
        help="Write full run result JSON (including evidence) to this path; stdout omits evidence lists",
    )
    parser.add_argument(
        "--questionnaire-spec",
        type=str,
        help="Path to QuestionnaireSpec YAML or JSON (requires --questionnaire-vars and --dossier or --dossier-file)",
    )
    parser.add_argument(
        "--questionnaire-vars",
        type=str,
        help="JSON file mapping template variables (e.g. crop, use_case)",
    )
    parser.add_argument(
        "--dossier-file",
        type=str,
        help="CropDossier JSON; use with --questionnaire-spec when not using --dossier",
    )
    parser.add_argument(
        "--questionnaire-render-md",
        type=str,
        help="Write questionnaire execution markdown (coverage + responses)",
    )
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

    if args.questionnaire_spec:
        if not args.questionnaire_vars:
            parser.error("--questionnaire-spec requires --questionnaire-vars")
        if not args.dossier and not args.dossier_file:
            parser.error("Questionnaire execution requires --dossier or --dossier-file")
    if args.questionnaire_render_md and not args.questionnaire_spec:
        parser.error("--questionnaire-render-md requires --questionnaire-spec")

    from research_agent.agent.llm import LLMClient
    from research_agent.agent.research import ResearchAgent

    agent = ResearchAgent(
        llm=LLMClient(),
        cache_settings=CacheSettings(mode=args.cache_mode, cache_dir=args.cache_dir),
    )

    if args.questionnaire_spec:
        from research_agent.contracts.agronomy.dossier import CropDossier

        spec = load_questionnaire_spec(args.questionnaire_spec)
        vars_map = json.loads(Path(args.questionnaire_vars).read_text(encoding="utf-8"))
        if args.dossier:
            from research_agent.agent.schemas import EvidenceItem, PlanOut

            dossier_out = agent.run_dossier(task_prompt, input_vars, dossier_input)
            dossier = CropDossier.model_validate(dossier_out["dossier"])
            evidence_full_raw = dossier_out.get("evidence_full") or dossier_out["evidence"]
            evidence_full = [EvidenceItem.model_validate(e) for e in evidence_full_raw]
            q_out = agent.run_questionnaire(
                task_prompt,
                input_vars,
                dossier,
                spec,
                vars_map,
                plan=PlanOut.model_validate(dossier_out["plan"]),
                evidence=evidence_full,
            )
            result = {
                **dossier_out,
                "questionnaire": q_out["questionnaire"],
                "questionnaire_iterations": q_out["iterations"],
                "questionnaire_evidence_validation_errors": q_out.get("questionnaire_evidence_validation_errors", []),
                "questionnaire_reused_dossier_retrieval": q_out.get("reused_retrieval_substrate", False),
            }
            # Questionnaire may extend evidence (gap-fill); keep top-level evidence aligned with the questionnaire run.
            result["evidence"] = q_out["evidence"]
            result["evidence_full"] = q_out["evidence_full"]
        else:
            dossier = CropDossier.model_validate(
                json.loads(Path(args.dossier_file).read_text(encoding="utf-8"))
            )
            result = agent.run_questionnaire(task_prompt, input_vars, dossier, spec, vars_map)
    else:
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
    if args.questionnaire_render_md:
        from research_agent.contracts.core.questionnaire import QuestionnaireExecutionResult

        qexec = QuestionnaireExecutionResult.model_validate(result["questionnaire"])
        Path(args.questionnaire_render_md).write_text(
            render_questionnaire_execution_markdown(qexec), encoding="utf-8"
        )
    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    print(json.dumps(_result_json_for_stdout(result), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
