# Tier-1 pipeline (recipe)

This is an **orchestration recipe**, not a single bundled CLI: run prioritization first, then drive per-crop dossier and questionnaire runs from the ranked output.

## 1. Rank crop × use-case candidates

Use **`research-agent-prioritize`** (see [README.md](../README.md) and [PUBLIC_API.md](PUBLIC_API.md) for flags):

- **`--task-file`**: JSON with `task_prompt` and `input_vars` (same shape as `research-agent`).
- **`--candidates`**: JSON array of `{ "candidate_id", "crop", "use_case", ... }` or `{ "candidates": [ ... ] }`.
- **`--output-json`**: full payload including `prioritization`, `evidence`, `evidence_full`.

Optional: set **`prioritization_weights`** (array of four numbers) and **`rubric_version`** on the task JSON, and/or pass **`--weights`** / **`--rubric-version`** on the CLI (CLI overrides task-file defaults where both are set).

## 2. Take Tier 1 rows

From `prioritization.tier_lists`, use the list whose `tier` is **`T1`** (or filter `prioritization.ranked` by `aggregate_score` and your own cutoff). Each row has `candidate`, `components`, and validated **`rationale_claims`** with `evidence_ids`.

## 3. Per-candidate dossier + questionnaire

For each Tier-1 `(crop, use_case)` you want deep research on:

1. Build a **`research-agent` `--task-file`** with `dossier_input` aligned to that crop (and use cases as needed).
2. Run **`research-agent --dossier --task-file ...`** (optionally `--claim-graph`).
3. Optionally run **questionnaire** on the same invocation: `--questionnaire-spec` + `--questionnaire-vars`, which **reuses** the dossier plan/evidence when combined with `--dossier` (see ARCHITECTURE / PUBLIC_API).

Use a **shared `--cache-dir`** (or default cache) across runs so retrieval can reuse work when topics overlap.

## 4. Synthesis (later)

Cross-crop synthesis is intentionally **out of scope** for the prioritization artifact. Run it only once you have **multiple** comparable `PrioritizationResult`, dossier, and/or questionnaire JSON outputs in a stable shape.
