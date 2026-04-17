# Refactoring notes

## Decisions

1. **Single package** `research_agent` under `src/`, installable via root `pyproject.toml` (`research-agent` distribution name).
2. **No `sys.path` hacks** — contracts live in `research_agent.contracts`; the research agent imports them normally.
3. **One claim-graph validator** — all rules in `contracts/core/claim_graph.py`, implemented once in `validate_claim_graph_detailed`. `validate_claim_graph` is a thin wrapper returning `list[str]` messages for convenience; prefer `validate_claim_graph_detailed` for new code (see `PUBLIC_API.md`).
4. **One projection renderer** — `render_final_projection_markdown(..., style="customer"|"debug")` subsumes the old standalone debug layout.
5. **Demo ownership** — `build_agrinova_demo_bundle()` only in `research_agent.contracts.examples.agrinova`, re-exported from `research_agent.contracts.examples`. The `claim-graph` CLI imports it; it does not embed demo data.
6. `**claim_graph_bridge.py`** — explicit name for `EvidenceItem` → `EvidenceRecord` mapping (avoids a vague `bridge.py`).
7. **Legacy `contracts_lib_example/`** — removed from this repo; code lives under `src/research_agent/contracts` and `examples/`. Old `from contracts....` imports → `from research_agent.contracts....`.

## Breaking changes (historical migration)

- Imports `**from contracts....**` → `**from research_agent.contracts....**`
- Former **`contracts_lib_example/`** layout is gone; use **`src/research_agent/contracts`**, repo **`examples/`**, **`examples/workflows/**`.
- Root **`research_agent_prototype.py`** / **`claim_graph_prototype.py`** shims are not shipped in this tree; use **`research-agent`** / **`claim-graph`** entry points or **`python -m research_agent`**.

## Final repo tree (high level)

```text
pyproject.toml
README.md
src/research_agent/
  __init__.py
  __main__.py
  contracts/                   # core, agronomy, renderers, examples (agrinova demo)
  retrieval/                   # http, doi, scoring, sources
  agent/                       # schemas, llm, claim_graph_bridge, research
  cli/                         # research, claim_graph
examples/
  build_demo_artifacts.py
  agrinova_claim_graph.py
  questionnaire.agronomy.yaml
  generated/
  workflows/agronomy/
docs/
  ARCHITECTURE.md
  PUBLIC_API.md
  REFACTORING.md
```

## Migration checklist

1. `pip install -e ".[dev]"`
2. Replace `from contracts.` imports with `from research_agent.contracts.`
3. Run `python examples/agrinova_claim_graph.py` or `claim-graph --demo --validate-only` to verify.

