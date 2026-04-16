from __future__ import annotations

import argparse
import json
from typing import Any

from research_agent.agent.llm import LLMClient
from research_agent.agent.research import ResearchAgent
from research_agent.agent.schemas import InputVars


def demo_payload() -> tuple[str, InputVars]:
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
    return task_prompt, input_vars


def load_task_file(path: str) -> tuple[str, InputVars]:
    with open(path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data["task_prompt"], InputVars.model_validate(data["input_vars"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Template-constrained research agent (retrieval + LLM draft).")
    parser.add_argument("--demo", action="store_true", help="Run the built-in demo payload")
    parser.add_argument("--task-file", type=str, help="Path to JSON file with task_prompt and input_vars")
    parser.add_argument(
        "--claim-graph",
        action="store_true",
        help="Emit and validate ClaimGraphBundle (claims + links + projection) instead of FinalReport",
    )
    args = parser.parse_args()

    if not args.demo and not args.task_file:
        parser.error("Pass --demo or --task-file")

    if args.demo:
        task_prompt, input_vars = demo_payload()
    else:
        task_prompt, input_vars = load_task_file(args.task_file)

    agent = ResearchAgent(llm=LLMClient())
    result = agent.run_claim_graph(task_prompt, input_vars) if args.claim_graph else agent.run(task_prompt, input_vars)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
