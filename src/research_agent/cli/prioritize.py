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


def load_task_file(path: str) -> tuple[str, InputVars, dict[str, Any]]:
    """Load task JSON; optional keys ``prioritization_weights``, ``rubric_version`` for prioritize defaults."""
    with open(path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    extras: dict[str, Any] = {}
    if "prioritization_weights" in data:
        extras["prioritization_weights"] = data["prioritization_weights"]
    if "rubric_version" in data:
        extras["rubric_version"] = data["rubric_version"]
    return data["task_prompt"], InputVars.model_validate(data["input_vars"]), extras


def parse_weights_csv(s: str | None) -> tuple[float, float, float, float] | None:
    """Parse ``icp,platform,data,evidence`` comma-separated weights; must be exactly four numbers."""
    if s is None or not str(s).strip():
        return None
    parts = [p.strip() for p in str(s).split(",")]
    if len(parts) != 4:
        raise ValueError("Expected four comma-separated weights: icp_fit,platform_leverage,data_availability,evidence_strength")
    return tuple(float(p) for p in parts)  # type: ignore[return-value]


def weights_from_task_extras(extras: dict[str, Any]) -> tuple[float, float, float, float] | None:
    raw = extras.get("prioritization_weights")
    if raw is None:
        return None
    if not isinstance(raw, list) or len(raw) != 4:
        raise ValueError("prioritization_weights in task file must be a JSON array of four numbers")
    return tuple(float(x) for x in raw)  # type: ignore[return-value]


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
    parser.add_argument(
        "--weights",
        type=str,
        default=None,
        metavar="W1,W2,W3,W4",
        help="Comma-separated weights for icp_fit, platform_leverage, data_availability, evidence_strength (overrides task file)",
    )
    parser.add_argument(
        "--rubric-version",
        type=str,
        default=None,
        help="Stored on PrioritizationResult.rubric_version (default 1.0; task file may set rubric_version)",
    )
    args = parser.parse_args()

    extras: dict[str, Any] = {}
    if args.demo:
        task_prompt, input_vars, candidates = demo_payload()
    else:
        if not args.task_file or not args.candidates:
            parser.error("Pass --demo or both --task-file and --candidates")
        task_prompt, input_vars, extras = load_task_file(args.task_file)
        candidates = load_candidates(args.candidates)

    from research_agent.agent.llm import LLMClient
    from research_agent.agent.prioritization import _validate_weights_four
    from research_agent.agent.research import ResearchAgent

    try:
        w_cli = parse_weights_csv(args.weights)
        w_file = weights_from_task_extras(extras)
    except ValueError as e:
        parser.error(str(e))
    weights_final = w_cli if w_cli is not None else w_file
    if weights_final is None:
        weights_final = (0.25, 0.25, 0.25, 0.25)
    _validate_weights_four(weights_final)

    rubric = args.rubric_version
    if rubric is None and extras.get("rubric_version") is not None:
        rubric = str(extras["rubric_version"])
    if rubric is None:
        rubric = "1.0"

    agent = ResearchAgent(
        llm=LLMClient(),
        cache_settings=CacheSettings(mode=args.cache_mode, cache_dir=args.cache_dir),
    )
    result = agent.run_prioritization(task_prompt, input_vars, candidates, weights=weights_final, rubric_version=rubric)

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
