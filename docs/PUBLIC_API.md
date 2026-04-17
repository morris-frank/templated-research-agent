# Public API surface

Pre-1.0: only the items listed here are treated as a stability contract. Internal modules may change if this document is updated.

## Supported imports

**Claim graph (contracts)**

- `research_agent.contracts.core.claim_graph` — graph models, `merge_claim_graph`, `ClaimGraphValidationResult`, `ValidationIssue`, `ClaimGraphDraft`, `ClaimGraphBundle`, etc.
- **Validation:** Prefer **`validate_claim_graph_detailed`** for new code — returns a structured `ClaimGraphValidationResult` with `ok: bool` and `errors: list[ValidationIssue]` (coded). **`validate_claim_graph`** is a thin convenience wrapper returning only error message strings. Warnings are not emitted today; severity will be widened if/when warning rules are introduced.
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

- `research-agent` (setuptools entry point → `research_agent.cli.research:main`) — **requires `[retrieval]`**
  - `--demo` | `--task-file PATH`
  - `--claim-graph` — emit merged `ClaimGraphBundle` JSON in result
- `python -m research_agent` — same as `research-agent`; **requires `[retrieval]`**
- `claim-graph` → `research_agent.cli.claim_graph:main` — core install only
  - `--demo` | `--input-json PATH`
  - `--validate-only`, `--write-json`, `--render-markdown`, `--render-style customer|debug`, `--print-summary`

## Non-public modules

Not a semver promise without an explicit bump + PUBLIC_API update:

- `research_agent.retrieval.*` internals (function names may move between modules)
- `research_agent.cli` module layout beyond the entrypoint functions
- `research_agent.contracts.examples.agrinova` (import via `research_agent.contracts.examples` when possible)

Example scripts under **`examples/`** are illustrative, not a library API.
