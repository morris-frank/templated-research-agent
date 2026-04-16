# Refactoring notes

## Decisions

1. **Single package** `research_agent` under `src/`, installable via root `pyproject.toml` (`research-agent` distribution name).
2. **No `sys.path` hacks** — contracts live in `research_agent.contracts`; the research agent imports them normally.
3. **One claim-graph validator** — all rules in `contracts/core/claim_graph.py`. `validate_claim_graph` returns `list[str]` messages; `validate_claim_graph_detailed` returns `ClaimGraphValidationResult` with coded `ValidationIssue` rows (includes link strength in `[0,1]`).
4. **One projection renderer** — `render_final_projection_markdown(..., style="customer"|"debug")` subsumes the old standalone debug layout.
5. **Demo ownership** — `build_agrinova_demo_bundle()` only in `research_agent.contracts.examples.agrinova`, re-exported from `research_agent.contracts.examples`. The `claim-graph` CLI imports it; it does not embed demo data.
6. **`claim_graph_bridge.py`** — explicit name for `EvidenceItem` → `EvidenceRecord` mapping (avoids a vague `bridge.py`).
7. **`contracts_lib_example/`** — reduced to a README pointer; code moved to `src/research_agent/contracts` and `examples/`.

## Breaking changes

- Imports **`from contracts....`** → **`from research_agent.contracts....`**
- **`contracts_lib_example/contracts`**, **examples**, and **workflows** trees removed from that folder; use **`src/research_agent/contracts`**, repo **`examples/`**, **`examples/workflows/`**.
- **`claim_graph_prototype.py`** body removed; same filename is a shim only.
- **`research_agent_prototype.py`** docstring and inline implementation removed; shim only.

## Final repo tree (high level)

```text
pyproject.toml
README.md
research_agent_prototype.py    # shim
claim_graph_prototype.py       # shim
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
contracts_lib_example/
  README.md                    # migration pointer
docs/
  ARCHITECTURE.md
  PUBLIC_API.md
  REFACTORING.md
```

## Migration checklist

1. `pip install -e ".[dev]"`
2. Replace `from contracts.` imports with `from research_agent.contracts.`
3. Run `python examples/agrinova_claim_graph.py` or `claim-graph --demo --validate-only` to verify.
