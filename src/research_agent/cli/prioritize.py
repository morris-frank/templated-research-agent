from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research_agent.contracts.agronomy.prioritization import CropUseCaseCandidate, PrioritizationResult
from research_agent.contracts.renderers.markdown import render_prioritization_markdown
from research_agent.retrieval.cache import CacheSettings
from research_agent.types import InputVars


def _result_json_for_stdout(result: dict[str, Any]) -> dict[str, Any]:
    out = dict(result)
    if "evidence" in out:
        ev = out.pop("evidence")
        out["evidence_count"] = len(ev) if isinstance(ev, list) else 0
    if "evidence_full" in out:
        ef = out.pop("evidence_full")
        out["evidence_full_count"] = len(ef) if isinstance(ef, list) else 0
    return out


def load_task_file(path: str) -> tuple[str, InputVars]:
    with open(path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data["task_prompt"], InputVars.model_validate(data["input_vars"])


def load_candidates(path: str) -> list[CropUseCaseCandidate]:
    raw: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "candidates" in raw:
        raw = raw["candidates"]
    if not isinstance(raw, list):
        raise ValueError('candidates file must be a JSON array or {"candidates": [...]}')
    return [CropUseCaseCandidate.model_validate(x) for x in raw]


def demo_payload() -> tuple[str, InputVars, list[CropUseCaseCandidate]]:
    task_prompt = "Rank crop × use-case opportunities for agri-input R&D prioritization."
    input_vars = InputVars(topic="biologicals and soil diagnostics", company="Demo", region=None, source_urls=[])
    candidates = [
        CropUseCaseCandidate(candidate_id="c1", crop="Wheat", use_case="soil microbiome diagnostics"),
        CropUseCaseCandidate(candidate_id="c2", crop="Maize", use_case="nitrogen use efficiency"),
    ]
    return task_prompt, input_vars, candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch crop × use-case prioritization (retrieval + scored artifact).")
    parser.add_argument("--demo", action="store_true", help="Run built-in demo payload")
    parser.add_argument("--task-file", type=str, help="JSON with task_prompt and input_vars")
    parser.add_argument("--candidates", type=str, help="JSON file: candidate rows (required unless --demo)")
    parser.add_argument(
        "--output-json",
        type=str,
        metavar="PATH",
        help="Write full run JSON (prioritization, evidence, evidence_full); stdout omits evidence lists",
    )
    parser.add_argument("--render-markdown", type=str, metavar="PATH", help="Write prioritization markdown summary")
    parser.add_argument("--cache-mode", choices=["default", "refresh", "off"], default="default", help="Retrieval cache")
    parser.add_argument("--cache-dir", type=str, default=None, help="Optional retrieval cache directory")
    args = parser.parse_args()

    if args.demo:
        task_prompt, input_vars, candidates = demo_payload()
    else:
        if not args.task_file or not args.candidates:
            parser.error("Pass --demo or both --task-file and --candidates")
        task_prompt, input_vars = load_task_file(args.task_file)
        candidates = load_candidates(args.candidates)

    from research_agent.agent.llm import LLMClient
    from research_agent.agent.research import ResearchAgent

    agent = ResearchAgent(
        llm=LLMClient(),
        cache_settings=CacheSettings(mode=args.cache_mode, cache_dir=args.cache_dir),
    )
    result = agent.run_prioritization(task_prompt, input_vars, candidates)

    if args.render_markdown:
        md = render_prioritization_markdown(PrioritizationResult.model_validate(result["prioritization"]))
        Path(args.render_markdown).write_text(md, encoding="utf-8")
    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    print(json.dumps(_result_json_for_stdout(result), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
