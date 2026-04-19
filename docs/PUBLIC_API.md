# Public API surface

Pre-1.0: only the items listed here are treated as a stability contract. Internal modules may change if this document is updated.

## Supported imports

**Claim graph (contracts)**

- `research_agent.contracts.core.claim_graph` — graph models, `merge_claim_graph`, `ClaimGraphValidationResult`, `ValidationIssue`, `ClaimGraphDraft`, `ClaimGraphBundle`, etc.
- **Validation:** Prefer **`validate_claim_graph_detailed`** for new code — returns a structured `ClaimGraphValidationResult` with `ok: bool` and `errors: list[ValidationIssue]` (coded). **`validate_claim_graph`** is a thin convenience wrapper returning only error message strings. Warnings are not emitted today; severity will be widened if/when warning rules are introduced.
- `research_agent.contracts.renderers.markdown` — `render_crop_dossier_markdown`, `render_questionnaire_response_markdown`, `render_questionnaire_execution_markdown` (coverage + skipped questions + stop reason), `render_prioritization_markdown`, `render_synthesis_markdown`, `render_final_projection_markdown` (`style="customer"` | `"debug"`).
- `research_agent.contracts.examples` — `build_agrinova_demo_bundle()` (canonical Agrinova demo graph).

**Agronomy / narrative contracts**

- `research_agent.contracts.agronomy.dossier` — `CropDossier`, `LifecycleStage`, `ProductionSystemContext`, `RotationRole`, and the agronomic-model layer: `YieldDriver`, `LimitingFactor`, `HeuristicRule`, `Intervention`, `InterventionEffect`, `Pathogen`, `BeneficialOrganism`, `SoilDependency`, `MicrobiomeFunction`, `CoverCropEffect`. All new fields on `CropDossier` are optional and default empty; pre-existing dossiers remain valid.
- `research_agent.contracts.agronomy.input` — `DossierInputVars` for dossier artifact seed context (separate from retrieval `InputVars`).
- `research_agent.contracts.agronomy.validation` — `validate_crop_dossier_detailed` (structured), `validate_crop_dossier` (messages-only convenience), `DossierThresholds`, `CropDossierValidationResult`. Errors-only today; same `ValidationIssue` shape as the claim-graph validator.
- `research_agent.contracts.agronomy.prioritization` — `CropUseCaseCandidate`, `ScoreComponents`, `RankedCandidate`, `TierList`, `PrioritizationResult` (crop × use-case ranking with deterministic score components and evidence-linked rationale claims).
- `research_agent.contracts.agronomy.synthesis` — `NormalizedConcept`, `CrossCropPattern`, `OntologyNode`, `PlatformPrimitive`, `SynthesisOutput` (v1 cross-crop synthesis over dossier + optional questionnaire JSON; claim graphs not used as inputs in v1).
- `research_agent.contracts.core.claims`, `research_agent.contracts.core.questionnaire`, `research_agent.contracts.core.evidence`, `research_agent.contracts.core.artifact_meta` — shared claim/questionnaire/evidence/meta shapes. Questionnaire specs use **typed** `ApplicabilityRule` lists (`present`, `non_empty`, `contains_keyword`, `has_tag` on dossier fields / meta tags / primary use cases); legacy **string** entries in `applicability_rules` are coerced to `present`. `required_context` is enforced during filtering (non-empty top-level dossier fields). Execution output is `QuestionnaireExecutionResult` with `QuestionnaireCoverage`, `SkippedQuestion`, `evidence_validation_errors` (claim evidence IDs not in the LLM evidence slice), and `stop_reason`.

**Import ergonomics**

- `import research_agent.agent.questionnaire` loads **only** questionnaire helpers (filtering, applicability) without importing `research_agent.agent.llm` — the `agent` package uses lazy exports, and `questionnaire.py` does not import `LLMClient` at import time. Use `from research_agent.agent.research import ResearchAgent` when you need the full loop.
- `import research_agent.retrieval` loads **`retrieval.scoring`** only (Pydantic + `types`). Symbols that need HTTP / `feedparser` / Tavily (`tavily_search`, `retrieve_scholarly_*`) are resolved **lazily** from `research_agent.retrieval.sources` when accessed. Importing **`retrieval.sources`** directly still requires **`[retrieval]`** extras.
- Running **`pytest tests/`** with full coverage expects **`research-agent[dev]`** (includes retrieval extras). Tests that hit `retrieval.sources` may be marked **`retrieval`**; run `pytest -m "not retrieval"` to skip those when working offline without optional deps.

**Agent loop**

- `research_agent.agent.research.ResearchAgent`
- `research_agent.agent.schemas` — `InputVars`, `EvidenceItem`, `FinalReport`, `PlanOut`, `GapQueries`, narrative `Claim`, `DossierStructurePartial`, `DossierAgronomicPartial`, `DossierInterventionPartial`, `CropDossierDraft`
- `research_agent.agent.dossier_bridge` — `DroppedRef`, `evidence_items_to_refs`, `merge_crop_dossier`
- `research_agent.agent.llm.LLMClient`
- `research_agent.agent.claim_graph_bridge` — `evidence_items_to_records`, `evidence_source_kind`
- `ResearchAgent.run_dossier(...)`, `ResearchAgent.compose_claim_graph_from(...)`
- `ResearchAgent.run_questionnaire(task_prompt, input_vars, dossier, questionnaire_spec, variables, ...)` — plan + retrieval + questionnaire pass(es); requires a materialized `CropDossier`. Pass optional **`plan`** and **`evidence`** together to reuse a prior retrieval run (e.g. dossier). Optional single gap-fill retry when answers are `insufficient_evidence`. Returns include `questionnaire_evidence_validation_errors` and `reused_retrieval_substrate` when applicable.
- `ResearchAgent.run_prioritization(task_prompt, input_vars, candidates)` — one plan + retrieval pass over a batch of crop × use-case candidates; returns `prioritization` (`PrioritizationResult` JSON), `evidence` / `evidence_full`, and merged `validation_errors` (including rationale evidence-ID validation).
- `ResearchAgent.run_claim_graph(...)` remains available but is **legacy convenience** for Python callers; new orchestration should use primary mode + optional sidecar composition.

## Supported CLIs

- `research-agent` (setuptools entry point → `research_agent.cli.research:main`) — **requires `[retrieval]`**
  - `--demo` | `--task-file PATH`
  - primary mode: default / `--final-report`, or `--dossier` (`run_dossier` JSON includes `evidence_full` for downstream steps)
  - `--claim-graph` — optional sidecar from the same plan/evidence
  - `--render-markdown PATH` — dossier markdown rendering (`--dossier` only)
  - `--questionnaire-spec PATH` — YAML/JSON `QuestionnaireSpec` (requires `--questionnaire-vars` and `--dossier` or `--dossier-file`)
  - `--questionnaire-vars PATH` — JSON object for template variables (e.g. `crop`, `use_case`)
  - `--dossier-file PATH` — load `CropDossier` JSON when not generating via `--dossier`
  - `--questionnaire-render-md PATH` — write execution markdown (coverage + responses)
  - `--cache-mode default|refresh|off`, `--cache-dir PATH` — retrieval cache controls
  - `--output-json PATH` — write the **full** run JSON (including `evidence` / `evidence_full`) to a file; stdout prints the same structure with evidence lists replaced by `evidence_count` / `evidence_full_count`
  - Combined **`--dossier`** + **`--questionnaire-spec`**: after the questionnaire step, top-level **`evidence`** and **`evidence_full`** in the merged JSON match the questionnaire run (including any gap-fill retrieval); **`questionnaire_reused_dossier_retrieval`** is set when plan/evidence were reused from the dossier pass
- `python -m research_agent` — same as `research-agent`; **requires `[retrieval]`**
- `research-agent-synthesize` → `research_agent.cli.synthesize:main` — **core install** (Pydantic + contracts only; no retrieval imports)
  - **`--inputs-manifest PATH`** or **`--input-dir DIR`** (loads `DIR/manifest.json`) — JSON with `runs[]` entries: `run_id`, **`dossier`** (path relative to manifest), optional **`questionnaire`**, optional **`prioritization_context`** (metadata only; not used to extract concepts in v1)
  - optional thresholds: `min_crops_for_pattern`, `min_mentions` (or nested `thresholds`)
  - `--output-json`, `--render-markdown` — stdout prints full JSON
- `research-agent-prioritize` → `research_agent.cli.prioritize:main` — **requires `[retrieval]`**
  - `--demo` | `--task-file PATH` (JSON with `task_prompt` and `input_vars`, same shape as `research-agent`; optional **`prioritization_weights`** — JSON array of four numbers — and **`rubric_version`** string for defaults)
  - `--candidates PATH` — JSON array of `{ "candidate_id", "crop", "use_case", ... }` rows (or `{ "candidates": [...] }`)
  - `--weights W1,W2,W3,W4` — comma-separated aggregate weights (icp_fit, platform_leverage, data_availability, evidence_strength); overrides task-file `prioritization_weights` when set
  - `--rubric-version STR` — recorded on `PrioritizationResult.rubric_version`; overrides task-file `rubric_version` when set
  - `--output-json PATH` — full run JSON (`prioritization`, `evidence`, `evidence_full`); stdout omits bulky evidence lists (counts only)
  - `--render-markdown PATH` — human-readable tier table + rationale lines
  - `--cache-mode`, `--cache-dir` — same semantics as `research-agent`
  - Tier-1 orchestration recipe: [docs/TIER1_PIPELINE.md](TIER1_PIPELINE.md)
- `claim-graph` → `research_agent.cli.claim_graph:main` — core install only
  - `--demo` | `--input-json PATH`
  - `--validate-only`, `--write-json`, `--render-markdown`, `--render-style customer|debug`, `--print-summary`

## Non-public modules

Not a semver promise without an explicit bump + PUBLIC_API update:

- `research_agent.retrieval.*` internals (function names may move between modules)
- `research_agent.cli` module layout beyond the entrypoint functions
- `research_agent.contracts.examples.agrinova` (import via `research_agent.contracts.examples` when possible)

Example scripts under **`examples/`** are illustrative, not a library API.
