from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import ValidationError

from research_agent.agent.claim_graph_bridge import evidence_items_to_records
from research_agent.agent.dossier_bridge import DroppedRef, evidence_items_to_refs, merge_crop_dossier
from research_agent.agent.llm import LLMClient
from research_agent.agent.schemas import (
    Claim,
    CropDossierDraft,
    DossierAgronomicPartial,
    DossierInterventionPartial,
    DossierStructurePartial,
    EvidenceItem,
    FinalReport,
    GapQueries,
    InputVars,
    PlanOut,
)
from research_agent.contracts.agronomy.input import DossierInputVars
from research_agent.contracts.agronomy.validation import DossierThresholds, validate_crop_dossier_detailed
from research_agent.contracts.core.claim_graph import (
    ClaimGraphDraft,
    ExecutionContext,
    merge_claim_graph,
    validate_claim_graph,
)
from research_agent.retrieval.scoring import dedupe_evidence
from research_agent.retrieval.sources import (
    collect_evidence_for_plan,
    collect_evidence_for_queries,
)

Partial = Literal["structure", "agronomic", "interventions"]

_CODE_TO_PARTIAL: dict[str, Partial] = {
    "lifecycle_missing_stages": "structure",
    "too_few_yield_drivers": "agronomic",
    "too_few_limiting_factors": "agronomic",
    "too_few_interventions": "interventions",
    "too_few_pathogens": "interventions",
    "intervention_effect_dangling_fk": "interventions",
    "merge_ref_dropped": "interventions",
    "per_section_evidence_floor:yield_drivers": "agronomic",
    "per_section_evidence_floor:interventions": "interventions",
    "per_section_evidence_floor:pathogens": "interventions",
}


def _collect_evidence_ids(value: Any) -> set[str]:
    ids: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "evidence_ids" and isinstance(nested, list):
                ids.update(str(item) for item in nested)
            else:
                ids.update(_collect_evidence_ids(nested))
    elif isinstance(value, list):
        for item in value:
            ids.update(_collect_evidence_ids(item))
    return ids


def claim_lists(report: FinalReport) -> list[tuple[str, Claim]]:
    out: list[tuple[str, Claim]] = []
    for section_name in ("key_findings", "scientific_evidence", "market_context"):
        for claim in getattr(report, section_name):
            out.append((section_name, claim))
    return out


@dataclass
class ResearchAgent:
    llm: LLMClient
    max_iterations: int = 3
    top_k_evidence: int = 25

    def plan(self, task_prompt: str, input_vars: dict[str, Any], target_schema: dict[str, Any]) -> PlanOut:
        payload = {
            "task_prompt": task_prompt,
            "input_vars": input_vars,
            "target_schema": target_schema,
            "instructions": [
                "Decompose the task into concrete subquestions.",
                "Produce web queries for current/general web search.",
                "Produce paper queries for scholarly databases.",
                "Prefer queries that can be resolved via DOI/title search when likely scholarly.",
            ],
        }
        out = self.llm.json_response(
            system=(
                "You are planning a bounded research workflow. Output only the JSON object matching the schema. "
                "Do not answer the task; only produce the research plan."
            ),
            user_payload=payload,
            schema_model=PlanOut,
        )
        return PlanOut.model_validate(out)

    def draft(self, task_prompt: str, input_vars: dict[str, Any], evidence: list[EvidenceItem]) -> dict[str, Any]:
        payload = {
            "task_prompt": task_prompt,
            "input_vars": input_vars,
            "evidence": [e.model_dump() for e in evidence[: self.top_k_evidence]],
            "instructions": [
                "Return JSON only.",
                "Use only supported claims from evidence.",
                "For every claim in key_findings, scientific_evidence, and market_context, include evidence_ids referencing the provided evidence items.",
                "Populate evidence_urls for each claim using the URLs corresponding to the cited evidence_ids.",
                "Use support='direct' when the cited evidence directly supports the claim; otherwise use 'partial' or 'contextual'.",
                "If evidence is weak or conflicting, reflect that in open_questions and confidence.",
                "Do not invent citations or facts not grounded in evidence.",
            ],
        }
        return self.llm.json_response(
            system="You synthesize retrieved evidence into the target report schema with explicit claim-level evidence linking.",
            user_payload=payload,
            schema_model=FinalReport,
        )

    def draft_claim_graph(
        self, task_prompt: str, input_vars: dict[str, Any], evidence: list[EvidenceItem]
    ) -> dict[str, Any]:
        payload = {
            "task_prompt": task_prompt,
            "input_vars": input_vars,
            "evidence": [e.model_dump() for e in evidence[: self.top_k_evidence]],
            "instructions": [
                "Return JSON only matching ClaimGraphDraft.",
                "Emit claims, claim_evidence_links, claim_dependency_links, and output (FinalProjection). Do not write long prose sections.",
                "Every claim needs claim_id (stable string), text, claim_kind, scope (list of {key, value} entries; use [] if none), confidence, status.",
                "Use claim_evidence_links only with evidence_id values from the provided evidence list.",
                "Use relation direct_support when the evidence itself states or measures the claim; indirect_support when it requires interpretation.",
                "Recommendations (claim_kind recommendation) should usually depend_on or be motivated by observation/inference claims via claim_dependency_links.",
                "output.summary_claim_refs and insight items must reference existing claim_id values.",
                "For RecommendationItem, rationale_claim_refs point to recommendation claims; dependency_claim_refs point to supporting observation/inference claims.",
                "If the task has no quantitative soil/lab metrics in evidence, avoid numeric literals in claim text (status contested or qualitative wording).",
            ],
        }
        return self.llm.json_response(
            system=(
                "You build a structured claim graph: claims, evidence links, claim dependencies, and a final projection. "
                "Ground every link in the supplied evidence IDs."
            ),
            user_payload=payload,
            schema_model=ClaimGraphDraft,
        )

    def draft_crop_dossier_structure(
        self, task_prompt: str, input_vars: dict[str, Any], dossier_input: DossierInputVars, evidence: list[EvidenceItem]
    ) -> DossierStructurePartial:
        payload = {
            "task_prompt": task_prompt,
            "input_vars": input_vars,
            "dossier_input": dossier_input.model_dump(),
            "evidence": [e.model_dump() for e in evidence[: self.top_k_evidence]],
            "instructions": [
                "Return JSON only matching DossierStructurePartial.",
                "Populate production context and lifecycle ontology with practical specificity.",
            ],
        }
        out = self.llm.json_response(
            system="Draft the structural sections of a crop dossier from evidence.",
            user_payload=payload,
            schema_model=DossierStructurePartial,
        )
        return DossierStructurePartial.model_validate(out)

    def draft_crop_dossier_agronomic(
        self,
        task_prompt: str,
        input_vars: dict[str, Any],
        evidence: list[EvidenceItem],
        structure: DossierStructurePartial,
    ) -> DossierAgronomicPartial:
        payload = {
            "task_prompt": task_prompt,
            "input_vars": input_vars,
            "structure": structure.model_dump(),
            "evidence": [e.model_dump() for e in evidence[: self.top_k_evidence]],
            "instructions": [
                "Return JSON only matching DossierAgronomicPartial.",
                "Use lifecycle stage names from structure.lifecycle_ontology where stage is needed.",
            ],
        }
        out = self.llm.json_response(
            system="Draft the agronomic-model sections of a crop dossier from evidence.",
            user_payload=payload,
            schema_model=DossierAgronomicPartial,
        )
        return DossierAgronomicPartial.model_validate(out)

    def draft_crop_dossier_interventions(
        self,
        task_prompt: str,
        input_vars: dict[str, Any],
        evidence: list[EvidenceItem],
        structure: DossierStructurePartial,
        agronomic: DossierAgronomicPartial,
    ) -> DossierInterventionPartial:
        payload = {
            "task_prompt": task_prompt,
            "input_vars": input_vars,
            "structure": structure.model_dump(),
            "agronomic": agronomic.model_dump(),
            "evidence": [e.model_dump() for e in evidence[: self.top_k_evidence]],
            "instructions": [
                "Return JSON only matching DossierInterventionPartial.",
                "intervention_effects.intervention_id must reference interventions ids.",
                "intervention_effects.target_ref and cover_crop_effects.target_ref must reference IDs present in agronomic/pathogen/soil/microbiome sections.",
            ],
        }
        out = self.llm.json_response(
            system="Draft interventions, biotic risks, and systems interactions for crop dossier.",
            user_payload=payload,
            schema_model=DossierInterventionPartial,
        )
        return DossierInterventionPartial.model_validate(out)

    def draft_crop_dossier(
        self,
        task_prompt: str,
        input_vars: dict[str, Any],
        dossier_input: DossierInputVars,
        evidence: list[EvidenceItem],
        *,
        refresh_only: set[Partial] | None = None,
        prior: CropDossierDraft | None = None,
    ) -> CropDossierDraft:
        if prior is None and refresh_only:
            refresh_only = None
        refresh = refresh_only or {"structure", "agronomic", "interventions"}

        structure = (
            self.draft_crop_dossier_structure(task_prompt, input_vars, dossier_input, evidence)
            if "structure" in refresh
            else DossierStructurePartial.model_validate(prior.model_dump())
        )
        agronomic = (
            self.draft_crop_dossier_agronomic(task_prompt, input_vars, evidence, structure)
            if "agronomic" in refresh
            else DossierAgronomicPartial.model_validate(prior.model_dump())
        )
        interventions = (
            self.draft_crop_dossier_interventions(task_prompt, input_vars, evidence, structure, agronomic)
            if "interventions" in refresh
            else DossierInterventionPartial.model_validate(prior.model_dump())
        )

        return CropDossierDraft.model_validate(
            {
                **structure.model_dump(),
                **agronomic.model_dump(),
                **interventions.model_dump(),
            }
        )

    def evaluate(self, draft: dict[str, Any], evidence: list[EvidenceItem]) -> tuple[bool, list[str]]:
        missing: list[str] = []
        try:
            report = FinalReport.model_validate(draft)
        except ValidationError as e:
            return False, [f"schema_validation_failed: {e}"]

        if not report.summary.strip():
            missing.append("summary")
        if not report.key_findings:
            missing.append("key_findings")
        if not report.scientific_evidence:
            missing.append("scientific_evidence")
        if not report.market_context:
            missing.append("market_context")

        evidence_by_id = {e.id: e for e in evidence}
        for section_name, claim in claim_lists(report):
            if not claim.text.strip():
                missing.append(f"{section_name}:empty_claim_text")
                continue
            if not claim.evidence_ids:
                missing.append(f"{section_name}:claim_without_evidence_ids:{claim.text[:80]}")
                continue
            resolved_urls = []
            for eid in claim.evidence_ids:
                item = evidence_by_id.get(eid)
                if item is None:
                    missing.append(f"{section_name}:unknown_evidence_id:{eid}")
                    continue
                resolved_urls.append(item.url)
            if claim.evidence_urls and sorted(set(claim.evidence_urls)) != sorted(set(resolved_urls)):
                missing.append(f"{section_name}:evidence_url_mismatch:{claim.text[:80]}")
            if not resolved_urls:
                missing.append(f"{section_name}:claim_without_resolved_evidence:{claim.text[:80]}")
            paper_only = section_name == "scientific_evidence"
            if paper_only and not any(
                evidence_by_id[eid].source_type == "paper" for eid in claim.evidence_ids if eid in evidence_by_id
            ):
                missing.append(f"{section_name}:requires_paper_evidence:{claim.text[:80]}")

        return (len(missing) == 0), missing

    def evaluate_claim_graph(
        self, draft: dict[str, Any], evidence: list[EvidenceItem], execution_context: ExecutionContext
    ) -> tuple[bool, list[str]]:
        try:
            graph_draft = ClaimGraphDraft.model_validate(draft)
        except ValidationError as e:
            return False, [f"claim_graph_schema_validation_failed: {e}"]

        records = evidence_items_to_records(evidence, execution_id=execution_context.execution_id)
        bundle = merge_claim_graph(graph_draft, [execution_context], records)
        errors = validate_claim_graph(bundle)
        return (len(errors) == 0), errors

    def evaluate_crop_dossier(
        self,
        dossier,
        evidence: list[EvidenceItem],
        dropped_refs: list[DroppedRef],
        thresholds: DossierThresholds | None = None,
    ) -> tuple[bool, list[str]]:
        errors: list[str] = []
        result = validate_crop_dossier_detailed(dossier, thresholds)
        errors.extend(f"{issue.code}: {issue.message}" for issue in result.errors)

        known_ids = {e.id for e in evidence}
        for eid in sorted(_collect_evidence_ids(dossier.model_dump())):
            if eid not in known_ids:
                errors.append(f"evidence_id_unknown:{eid}: dossier references unknown evidence id")
        for drop in dropped_refs:
            errors.append(
                f"merge_ref_dropped:{drop.kind}:{drop.value}: {drop.location} dropped ({drop.reason})"
            )
        return len(errors) == 0, errors

    def gap_queries(
        self, task_prompt: str, input_vars: dict[str, Any], missing_requirements: list[str], evidence: list[EvidenceItem]
    ) -> GapQueries:
        payload = {
            "task_prompt": task_prompt,
            "input_vars": input_vars,
            "missing_requirements": missing_requirements,
            "evidence_titles": [e.title for e in evidence[:15]],
            "evidence_venues": [e.venue for e in evidence[:15] if e.venue],
        }
        out = self.llm.json_response(
            system=(
                "Generate only the minimum incremental research queries needed to fill the missing requirements. "
                "Output only the JSON object matching the schema."
            ),
            user_payload=payload,
            schema_model=GapQueries,
        )
        return GapQueries.model_validate(out)

    def collect_evidence(self, plan: PlanOut, input_vars: InputVars) -> list[EvidenceItem]:
        return collect_evidence_for_plan(plan, input_vars)

    def collect_incremental_evidence(self, plan: PlanOut) -> list[EvidenceItem]:
        """Gap-fill retrieval: plan queries only, no seed URL re-fetch."""
        return collect_evidence_for_queries(plan)

    def compose_claim_graph_from(
        self,
        task_prompt: str,
        input_vars: InputVars,
        plan: PlanOut,
        evidence: list[EvidenceItem],
    ) -> dict[str, Any]:
        run_tag = uuid.uuid4().hex[:12]
        execution_context = ExecutionContext(
            execution_id=f"exec-retrieval-{run_tag}",
            pipeline_kind="retrieval",
            pipeline_version="research-agent",
            run_at=datetime.now(timezone.utc),
            parameters=input_vars.model_dump(),
        )

        last_draft: dict[str, Any] | None = None
        for iteration in range(self.max_iterations):
            draft = self.draft_claim_graph(task_prompt, input_vars.model_dump(), evidence)
            ok, errors = self.evaluate_claim_graph(draft, evidence, execution_context)
            last_draft = draft
            if ok:
                graph_draft = ClaimGraphDraft.model_validate(draft)
                records = evidence_items_to_records(evidence, execution_id=execution_context.execution_id)
                bundle = merge_claim_graph(graph_draft, [execution_context], records)
                return {
                    "plan": plan.model_dump(),
                    "evidence": [e.model_dump() for e in evidence[: self.top_k_evidence]],
                    "claim_graph": bundle.model_dump(mode="json"),
                    "validation_errors": [],
                    "iterations": iteration + 1,
                }

            gap = self.gap_queries(task_prompt, input_vars.model_dump(), errors, evidence)
            if not gap.web_queries and not gap.paper_queries:
                break

            incr_plan = PlanOut(
                subquestions=plan.subquestions,
                web_queries=gap.web_queries,
                paper_queries=gap.paper_queries,
                evidence_requirements=plan.evidence_requirements,
            )
            new_evidence = self.collect_incremental_evidence(incr_plan)
            evidence = dedupe_evidence(evidence + new_evidence)
            time.sleep(0.5)

        graph_draft = ClaimGraphDraft.model_validate(last_draft) if last_draft else None
        records = evidence_items_to_records(evidence, execution_id=execution_context.execution_id)
        bundle_dump = None
        if graph_draft:
            bundle = merge_claim_graph(graph_draft, [execution_context], records)
            bundle_dump = bundle.model_dump(mode="json")
        return {
            "plan": plan.model_dump(),
            "evidence": [e.model_dump() for e in evidence[: self.top_k_evidence]],
            "claim_graph": bundle_dump,
            "validation_errors": validate_claim_graph(
                merge_claim_graph(ClaimGraphDraft.model_validate(last_draft), [execution_context], records)
            )
            if last_draft
            else ["no_draft"],
            "iterations": self.max_iterations,
            "warning": "Returned best-effort claim graph; deterministic validation still failing.",
        }

    def run_claim_graph(self, task_prompt: str, input_vars: InputVars) -> dict[str, Any]:
        """LEGACY helper retained for Python callers; CLI uses sidecar composition."""
        target_schema = ClaimGraphDraft.model_json_schema()
        plan = self.plan(task_prompt, input_vars.model_dump(), target_schema)
        evidence = self.collect_evidence(plan, input_vars)
        if not evidence:
            raise RuntimeError("No evidence retrieved; aborting")
        return self.compose_claim_graph_from(task_prompt, input_vars, plan, evidence)

    def _partials_to_refresh(self, validation_errors: list[str]) -> set[Partial]:
        refresh: set[Partial] = set()
        for err in validation_errors:
            code = err.split(": ", 1)[0]
            mapped = _CODE_TO_PARTIAL.get(code)
            if mapped:
                refresh.add(mapped)
        return refresh

    def run_dossier(
        self,
        task_prompt: str,
        input_vars: InputVars,
        dossier_input: DossierInputVars,
        *,
        thresholds: DossierThresholds | None = None,
    ) -> dict[str, Any]:
        target_schema = CropDossierDraft.model_json_schema()
        plan = self.plan(task_prompt, input_vars.model_dump(), target_schema)
        evidence = self.collect_evidence(plan, input_vars)
        if not evidence:
            raise RuntimeError("No evidence retrieved; aborting")

        draft = self.draft_crop_dossier(task_prompt, input_vars.model_dump(), dossier_input, evidence)
        last_errors: list[str] = []
        for iteration in range(self.max_iterations):
            dossier, dropped = merge_crop_dossier(
                draft,
                evidence_items_to_refs(evidence),
                artifact_id=f"dossier-{uuid.uuid4().hex[:12]}",
                now=datetime.now(timezone.utc),
            )
            ok, errors = self.evaluate_crop_dossier(dossier, evidence, dropped, thresholds)
            if ok:
                return {
                    "plan": plan.model_dump(),
                    "evidence": [e.model_dump() for e in evidence[: self.top_k_evidence]],
                    "dossier": dossier.model_dump(mode="json"),
                    "validation_errors": [],
                    "iterations": iteration + 1,
                }
            last_errors = errors
            gap = self.gap_queries(task_prompt, input_vars.model_dump(), errors, evidence)
            if gap.web_queries or gap.paper_queries:
                incr_plan = PlanOut(
                    subquestions=plan.subquestions,
                    web_queries=gap.web_queries,
                    paper_queries=gap.paper_queries,
                    evidence_requirements=plan.evidence_requirements,
                )
                evidence = dedupe_evidence(evidence + self.collect_incremental_evidence(incr_plan))
            refresh = self._partials_to_refresh(errors)
            if any(e.startswith("low_evidence_coverage:") or e.startswith("evidence_id_unknown:") for e in errors) and not refresh:
                refresh = {"structure", "agronomic", "interventions"}
            draft = self.draft_crop_dossier(
                task_prompt,
                input_vars.model_dump(),
                dossier_input,
                evidence,
                refresh_only=refresh or None,
                prior=draft,
            )
        dossier, _ = merge_crop_dossier(
            draft,
            evidence_items_to_refs(evidence),
            artifact_id=f"dossier-{uuid.uuid4().hex[:12]}",
            now=datetime.now(timezone.utc),
        )
        return {
            "plan": plan.model_dump(),
            "evidence": [e.model_dump() for e in evidence[: self.top_k_evidence]],
            "dossier": dossier.model_dump(mode="json"),
            "validation_errors": last_errors or ["no_draft"],
            "iterations": self.max_iterations,
        }

    def run(self, task_prompt: str, input_vars: InputVars) -> dict[str, Any]:
        target_schema = FinalReport.model_json_schema()
        plan = self.plan(task_prompt, input_vars.model_dump(), target_schema)
        evidence = self.collect_evidence(plan, input_vars)

        if not evidence:
            raise RuntimeError("No evidence retrieved; aborting")

        last_draft: dict[str, Any] | None = None
        for iteration in range(self.max_iterations):
            draft = self.draft(task_prompt, input_vars.model_dump(), evidence)
            ok, missing = self.evaluate(draft, evidence)
            last_draft = draft
            if ok:
                return {
                    "plan": plan.model_dump(),
                    "evidence": [e.model_dump() for e in evidence[: self.top_k_evidence]],
                    "final": draft,
                    "validation_errors": [],
                    "iterations": iteration + 1,
                }

            gap = self.gap_queries(task_prompt, input_vars.model_dump(), missing, evidence)
            if not gap.web_queries and not gap.paper_queries:
                break

            incr_plan = PlanOut(
                subquestions=plan.subquestions,
                web_queries=gap.web_queries,
                paper_queries=gap.paper_queries,
                evidence_requirements=plan.evidence_requirements,
            )
            new_evidence = self.collect_incremental_evidence(incr_plan)
            evidence = dedupe_evidence(evidence + new_evidence)
            time.sleep(0.5)

        return {
            "plan": plan.model_dump(),
            "evidence": [e.model_dump() for e in evidence[: self.top_k_evidence]],
            "final": last_draft,
            "validation_errors": missing if "missing" in locals() else ["no_draft"],
            "iterations": self.max_iterations,
            "warning": "Returned best-effort draft; claim-level evidence linking may still be incomplete or weak.",
        }
