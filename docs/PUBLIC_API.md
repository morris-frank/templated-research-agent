# Public API surface

Pre-1.0: only the items listed here are treated as a stability contract. Internal modules may change if this document is updated.

## Supported imports

**Claim graph (contracts)**

- `research_agent.contracts.core.claim_graph` — graph models, `merge_claim_graph`, `validate_claim_graph`, `validate_claim_graph_detailed`, `ClaimGraphValidationResult`, `ValidationIssue`, `ClaimGraphDraft`, `ClaimGraphBundle`, etc.
- `research_agent.contracts.renderers.markdown` — `render_crop_dossier_markdown`, `render_questionnaire_response_markdown`, `render_final_projection_markdown` (`style="customer"` | `"debug"`).
- `research_agent.contracts.examples` — `build_agrinova_demo_bundle()` (canonical Agrinova demo graph).

**Agronomy / narrative contracts**

- `research_agent.contracts.agronomy.*`, `research_agent.contracts.core.claims`, `research_agent.contracts.core.questionnaire`, `research_agent.contracts.core.evidence`, `research_agent.contracts.core.artifact_meta` — dossier and questionnaire shapes.

**Agent loop**

- `research_agent.agent.research.ResearchAgent`
- `research_agent.agent.schemas` — `InputVars`, `EvidenceItem`, `FinalReport`, `PlanOut`, `GapQueries`, narrative `Claim`
- `research_agent.agent.llm.LLMClient`
- `research_agent.agent.claim_graph_bridge` — `evidence_items_to_records`, `evidence_source_kind`

## Supported CLIs

- `research-agent` (setuptools entry point → `research_agent.cli.research:main`)
  - `--demo` | `--task-file PATH`
  - `--claim-graph` — emit merged `ClaimGraphBundle` JSON in result
- `claim-graph` → `research_agent.cli.claim_graph:main`
  - `--demo` | `--input-json PATH`
  - `--validate-only`, `--write-json`, `--render-markdown`, `--render-style customer|debug`, `--print-summary`
- `python -m research_agent` — same as `research-agent`

## Deprecated shims (compatibility only)

- Repo root `research_agent_prototype.py` — forwards to `research_agent.cli.research.main`
- Repo root `claim_graph_prototype.py` — forwards to `research_agent.cli.claim_graph.main`

Do not extend these files; new behavior belongs in `src/research_agent/`.

## Non-public modules

Not a semver promise without an explicit bump + PUBLIC_API update:

- `research_agent.retrieval.*` internals (function names may move between modules)
- `research_agent.cli` module layout beyond the entrypoint functions
- `research_agent.contracts.examples.agrinova` (import via `research_agent.contracts.examples` when possible)

Example scripts under **`examples/`** are illustrative, not a library API.
