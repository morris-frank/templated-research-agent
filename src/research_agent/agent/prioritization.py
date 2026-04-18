"""Research-lite prioritization: deterministic score components + evidence-backed rationale claims."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from research_agent.contracts.agronomy.prioritization import (
    CropUseCaseCandidate,
    PrioritizationResult,
    RankedCandidate,
    ScoreComponents,
    TierList,
)
from research_agent.contracts.core.claims import Claim
from research_agent.types import EvidenceItem, InputVars, PlanOut

# Keyword buckets for deterministic heuristics (0–1 densities).
_ICP_KEYWORDS = ("biological", "inoculant", "pathogen", "diagnostic", "trial", "field", "assay")
_PLATFORM_KEYWORDS = ("platform", "sensor", "monitoring", "companion", "benchmark", "variance")
_DATA_KEYWORDS = ("dataset", "metadata", "randomized", "replicat", "design", "baseline")


def _keyword_density(keywords: tuple[str, ...], text: str) -> float:
    if not text.strip():
        return 0.0
    hits = sum(1 for k in keywords if k in text)
    return min(1.0, hits / max(len(keywords), 1) * 2.5)


def _combined_text(evidence: list[EvidenceItem], candidate: CropUseCaseCandidate) -> str:
    parts: list[str] = []
    for e in evidence:
        parts.append(f"{e.title} {e.abstract_or_snippet}".lower())
    parts.append(f"{candidate.crop} {candidate.use_case} {candidate.notes or ''}".lower())
    return " ".join(parts)


def compute_score_components(evidence: list[EvidenceItem], candidate: CropUseCaseCandidate) -> ScoreComponents:
    """Rule-based scores from retrieval text + candidate labels (reproducible given same evidence)."""
    blob = _combined_text(evidence, candidate)
    icp_fit = _keyword_density(_ICP_KEYWORDS, blob)
    platform_leverage = _keyword_density(_PLATFORM_KEYWORDS, blob)
    data_availability = _keyword_density(_DATA_KEYWORDS, blob)
    scores = [e.score for e in evidence]
    if scores:
        evidence_strength = min(1.0, max(0.0, (sum(scores) / len(scores)) / 2.0))
    else:
        evidence_strength = 0.0
    return ScoreComponents(
        icp_fit=round(icp_fit, 4),
        platform_leverage=round(platform_leverage, 4),
        data_availability=round(data_availability, 4),
        evidence_strength=round(evidence_strength, 4),
    )


def _validate_weights_four(weights: tuple[float, ...]) -> tuple[float, float, float, float]:
    if len(weights) != 4:
        raise ValueError(
            "weights must be a 4-tuple matching "
            "(icp_fit, platform_leverage, data_availability, evidence_strength)"
        )
    return (float(weights[0]), float(weights[1]), float(weights[2]), float(weights[3]))


def aggregate_score(components: ScoreComponents, weights: tuple[float, ...]) -> float:
    w = _validate_weights_four(weights)
    vals = (
        components.icp_fit,
        components.platform_leverage,
        components.data_availability,
        components.evidence_strength,
    )
    return min(1.0, max(0.0, sum(wi * vi for wi, vi in zip(w, vals))))


def assign_tier_lists(ranked: list[RankedCandidate]) -> list[TierList]:
    """Fixed thresholds on aggregate_score."""
    t1 = [r for r in ranked if r.aggregate_score >= 0.67]
    t2 = [r for r in ranked if 0.34 <= r.aggregate_score < 0.67]
    t3 = [r for r in ranked if r.aggregate_score < 0.34]
    return [
        TierList(tier="T1", candidates=t1),
        TierList(tier="T2", candidates=t2),
        TierList(tier="T3", candidates=t3),
    ]


class CandidateRationaleDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    claims: list[Claim] = Field(default_factory=list)


class PrioritizationRationaleDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rationales: list[CandidateRationaleDraft] = Field(default_factory=list)


def validate_claim_evidence_ids(claims: list[Claim], allowed_ids: set[str]) -> list[str]:
    """Require each claim to cite at least one allowed evidence id (same slice as the LLM)."""
    errors: list[str] = []
    for c in claims:
        if not c.evidence_ids:
            errors.append("empty_evidence_ids")
            continue
        for eid in c.evidence_ids:
            if eid not in allowed_ids:
                errors.append(f"invalid_evidence_id:{eid}")
    return errors


def run_prioritization(
    agent: Any,
    task_prompt: str,
    input_vars: InputVars,
    candidates: list[CropUseCaseCandidate],
    *,
    weights: tuple[float, float, float, float] = (0.25, 0.25, 0.25, 0.25),
    top_k_evidence: int | None = None,
) -> tuple[PrioritizationResult, PlanOut, list[EvidenceItem]]:
    """Plan + retrieve once, score deterministically, optional LLM rationales with evidence IDs."""
    if not candidates:
        raise ValueError("candidates must be non-empty")
    ids = [c.candidate_id for c in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("candidate_id values must be unique")
    _validate_weights_four(weights)
    tk = top_k_evidence if top_k_evidence is not None else agent.top_k_evidence

    block = "\n".join(f"- {c.candidate_id}: {c.crop} / {c.use_case}" for c in candidates)
    augmented = f"{task_prompt}\n\nPrioritize and gather evidence for these crop × use_case candidates:\n{block}\n"
    plan = agent.plan(augmented, input_vars.model_dump(), PlanOut.model_json_schema())
    evidence = agent.collect_evidence(plan, input_vars)
    if not evidence:
        raise RuntimeError("No evidence retrieved; aborting prioritization")

    allowed_ids = {e.id for e in evidence[:tk]}
    ranked: list[RankedCandidate] = []
    for c in candidates:
        comp = compute_score_components(evidence, c)
        agg = aggregate_score(comp, weights)
        ranked.append(
            RankedCandidate(
                candidate=c,
                components=comp,
                aggregate_score=round(agg, 4),
                rationale_claims=[],
            )
        )
    ranked.sort(key=lambda r: r.aggregate_score, reverse=True)

    validation_errors: list[str] = []
    try:
        draft = agent.llm.json_response(
            system=(
                "You justify prioritization ranks using short claims. "
                "Each claim must use evidence_ids only from the provided evidence list. "
                "Output JSON matching PrioritizationRationaleDraft."
            ),
            user_payload={
                "candidates": [c.model_dump() for c in candidates],
                "evidence": [e.model_dump() for e in evidence[:tk]],
                "scores": [r.model_dump() for r in ranked],
                "instructions": [
                    "Emit one rationales entry per candidate_id.",
                    "2–4 claims per candidate; each claim needs evidence_ids from the evidence list only.",
                ],
            },
            schema_model=PrioritizationRationaleDraft,
        )
        rationale = PrioritizationRationaleDraft.model_validate(draft)
    except Exception as exc:  # noqa: BLE001 — surface as validation, keep numeric artifact
        validation_errors.append(f"rationale_llm_failed:{exc}")
        rationale = PrioritizationRationaleDraft(rationales=[])
    by_id = {r.candidate.candidate_id: r for r in ranked}
    for block_r in rationale.rationales:
        if block_r.candidate_id not in by_id:
            validation_errors.append(f"unknown_candidate_id:{block_r.candidate_id}")
            continue
        errs = validate_claim_evidence_ids(block_r.claims, allowed_ids)
        if errs:
            validation_errors.extend([f"{block_r.candidate_id}:{e}" for e in errs])
            continue
        rc = by_id[block_r.candidate_id]
        by_id[block_r.candidate_id] = rc.model_copy(update={"rationale_claims": block_r.claims})

    ranked = sorted(by_id.values(), key=lambda r: r.aggregate_score, reverse=True)
    result = PrioritizationResult(
        prioritization_id=f"prio-{uuid.uuid4().hex[:12]}",
        ranked=ranked,
        tier_lists=assign_tier_lists(ranked),
        validation_errors=validation_errors,
    )
    return result, plan, evidence
