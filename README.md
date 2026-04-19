# Templated research agent

Template-constrained research workflow: plan → retrieve (web + scholarly) → LLM JSON draft → evaluate → optional claim-graph merge and validation.

## Install

```bash
pip install -e ".[dev]"
```

- **Core** (`pip install -e .`): Pydantic contracts and claim-graph validation only. The `research_agent.retrieval` **package** loads only scoring helpers without optional HTTP/feed deps; importing `research_agent.retrieval.sources` still needs `[retrieval]`.
- **`[retrieval]`**: `requests`, `beautifulsoup4`, `feedparser`, `openai` for the research CLI and retrieval stack.
- **`[dev]`**: `pyyaml` + `[retrieval]` (recommended for local work).

## CLIs

**Requirements.** `research-agent`, `python -m research_agent`, and **`research-agent-prioritize`** require the `[retrieval]` extra (OpenAI client + HTTP stack). Install with `pip install -e ".[retrieval]"` or `pip install -e ".[dev]"`. **`research-agent-synthesize`** runs on the **core** install (no retrieval). The `claim-graph` CLI and contracts work on the core install (Pydantic only).

| Command | Purpose | Extras |
|--------|---------|--------|
| `research-agent` | Full agent (`--final-report` default or `--dossier`) with optional `--claim-graph` sidecar. Requires API keys (see below). | `[retrieval]` |
| `python -m research_agent` | Same as `research-agent`. | `[retrieval]` |
| `research-agent-prioritize` | **Tier-1 crop × use-case ranking**: batch candidates JSON → `PrioritizationResult` plus evidence; optional markdown. Flags and JSON shapes are documented in [docs/PUBLIC_API.md](docs/PUBLIC_API.md). | `[retrieval]` |
| `research-agent-synthesize` | **Cross-crop synthesis**: manifest of dossier (+ optional questionnaire) JSON → `SynthesisOutput`; optional markdown. See [docs/PUBLIC_API.md](docs/PUBLIC_API.md). | core |
| `claim-graph` | Validate / render / export a `ClaimGraphBundle` (`--demo` uses package demo data). | core |

Environment (research agent): `OPENAI_API_KEY`, `TAVILY_API_KEY`; optional `OPENAI_MODEL`, `OPENAI_BASE_URL`, `OPENAI_ORG`.

### `research-agent` mode matrix

- default / `--final-report`: emit `final` primary artifact
- `--claim-graph`: add `claim_graph_sidecar` (does not replace primary artifact)
- `--dossier`: emit `dossier` primary artifact (requires `dossier_input` in task file unless `--demo`)
- `--dossier --claim-graph`: dossier primary + claim-graph sidecar
- invalid: `--final-report --dossier`

`evidence_ids` in dossier outputs are run-local IDs (`E001`, `E002`, ...), valid within that run's `evidence_index`.

### Retrieval caching

`research-agent` now uses persistent retrieval caching by default to speed up repeat runs with similar inputs.

- `--cache-mode default` (default): read and write cache
- `--cache-mode refresh`: bypass cache reads and write fresh results
- `--cache-mode off`: disable cache reads and writes for the run
- `--cache-dir PATH`: override cache location (default `~/.cache/research-agent`)

Cache behavior notes:
- scope: retrieval + evidence collection only (no LLM response caching)
- negative caching: exceptions/timeouts are not cached
- top-level stale fallback: in `default` mode, if fresh aggregate collection fails and a stale aggregate exists, stale may be returned with a warning

### Live dossier example

```json
{
  "task_prompt": "Build a crop dossier for wheat disease-pressure management.",
  "input_vars": {"topic": "wheat agronomy", "region": "EU", "source_urls": []},
  "dossier_input": {
    "crop_name": "Wheat",
    "crop_category": "cereal",
    "primary_use_cases": ["pathogen panel"],
    "priority_tier": "T1"
  }
}
```

```bash
research-agent --task-file task.json --dossier --claim-graph --render-markdown wheat.dossier.md
```

## Examples

```bash
python examples/build_demo_artifacts.py
python examples/agrinova_claim_graph.py
claim-graph --demo --print-summary
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — layers and data flow.
- [docs/PUBLIC_API.md](docs/PUBLIC_API.md) — supported imports and CLI surface (`research-agent`, `research-agent-prioritize`, `claim-graph`).
- [docs/TIER1_PIPELINE.md](docs/TIER1_PIPELINE.md) — optional recipe: prioritization → per-crop dossier / questionnaire runs.
- [docs/REFACTORING.md](docs/REFACTORING.md) — migration from monoliths and repo layout.
