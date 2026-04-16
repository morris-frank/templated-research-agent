# Templated research agent

Template-constrained research workflow: plan → retrieve (web + scholarly) → LLM JSON draft → evaluate → optional claim-graph merge and validation.

## Install

```bash
pip install -e ".[dev]"
```

- **Core** (`pip install -e .`): Pydantic contracts and claim-graph validation only.
- **`[retrieval]`**: `requests`, `beautifulsoup4`, `feedparser`, `openai` for the research CLI and retrieval stack.
- **`[dev]`**: `pyyaml` + `[retrieval]` (recommended for local work).

## CLIs

| Command | Purpose |
|--------|---------|
| `research-agent` | Full agent (`--demo`, `--task-file`, optional `--claim-graph`). Requires API keys (see below). |
| `claim-graph` | Validate / render / export a `ClaimGraphBundle` (`--demo` uses package demo data). |
| `python -m research_agent` | Same as `research-agent`. |

Environment (research agent): `OPENAI_API_KEY`, `TAVILY_API_KEY`; optional `OPENAI_MODEL`, `OPENAI_BASE_URL`, `OPENAI_ORG`.

## Examples

```bash
python examples/build_demo_artifacts.py
python examples/agrinova_claim_graph.py
claim-graph --demo --print-summary
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — layers and data flow.
- [docs/PUBLIC_API.md](docs/PUBLIC_API.md) — supported imports and CLI surface.
- [docs/REFACTORING.md](docs/REFACTORING.md) — migration from monoliths and repo layout.

## Deprecated entry points

Root **`research_agent_prototype.py`** and **`claim_graph_prototype.py`** are thin shims; prefer the console scripts above.
