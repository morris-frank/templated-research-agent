# Refactoring notes

## Decisions

1. **Single package** `research_agent` under `src/`, installable via root `pyproject.toml` (`research-agent` distribution name).
2. **No `sys.path` hacks** — contracts live in `research_agent.contracts`; the research agent imports them normally.
3. **One claim-graph validator** — all rules in `contracts/core/claim_graph.py`, implemented once in `validate_claim_graph_detailed`, which returns an errors-only `ClaimGraphValidationResult` (`ok` + `errors: list[ValidationIssue]`). `validate_claim_graph` is a thin wrapper returning `list[str]` messages for convenience. Warnings are intentionally not modeled until a rule actually needs them.
4. **One projection renderer** — `render_final_projection_markdown(..., style="customer"|"debug")` subsumes the old standalone debug layout.
5. **Demo ownership** — `build_agrinova_demo_bundle()` only in `research_agent.contracts.examples.agrinova`, re-exported from `research_agent.contracts.examples`. The `claim-graph` CLI imports it; it does not embed demo data.
6. `claim_graph_bridge.py` — explicit name for `EvidenceItem` → `EvidenceRecord` mapping (avoids a vague `bridge.py`).
7. **Legacy `contracts_lib_example/`** — removed from this repo; code lives under `src/research_agent/contracts` and `examples/`. Old `from contracts....` imports → `from research_agent.contracts....`.
8. **Dossier agronomic-model layer (additive, non-breaking).** `CropDossier` gained `yield_drivers`, `limiting_factors`, `agronomist_heuristics`, `interventions`, `intervention_effects`, `pathogens`, `beneficials`, `soil_dependencies`, `microbiome_roles`, `cover_crop_effects`, `evidence_index`, `confidence`, `open_questions`. All default to empty, so pre-existing `CropDossier` JSON still validates. A companion `contracts/agronomy/validation.py` mirrors the claim-graph validator shape (`validate_crop_dossier_detailed` + coded `ValidationIssue` errors) and carries configurable minimums via `DossierThresholds`. Intervention→target links use IDs (`intervention_id`, `target_ref` → `YieldDriver.id` / `Pathogen.id` / `SoilDependency.id` / `MicrobiomeFunction.id` / `LimitingFactor.id`), not free-form strings. Evidence references use the existing `EvidenceRef`; no new evidence type was introduced.

## Breaking changes (historical migration)

- Imports `from contracts....` → `from research_agent.contracts....`
- Former `contracts_lib_example/` layout is gone; use `src/research_agent/contracts`, repo `examples/`, `examples/workflows/`.
- Root `research_agent_prototype.py` / `claim_graph_prototype.py` shims are not shipped in this tree; use `research-agent` / `claim-graph` entry points or `python -m research_agent`.

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

