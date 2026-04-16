from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ClaimKind = Literal[
    "observation",
    "comparison",
    "inference",
    "recommendation",
    "open_question",
]

ClaimStatus = Literal[
    "supported",
    "weakly_supported",
    "unsupported",
    "contested",
]

Confidence = Literal["low", "medium", "high"]

EvidenceSourceKind = Literal[
    "paper",
    "web",
    "measurement",
    "derived_metric",
    "benchmark",
    "customer_input",
    "report_artifact",
    "discovery_note",
]

LinkRelation = Literal[
    "direct_support",
    "indirect_support",
    "context_only",
    "contradicts",
    "motivates_recommendation",
]

ExecutionKind = Literal[
    "retrieval",
    "lab",
    "analysis",
    "model_inference",
    "report",
]

ClaimDependencyRelation = Literal[
    "depends_on",
    "derived_from",
    "generalizes",
    "narrows",
    "motivates",
    "contradicts",
]


class ExecutionContext(BaseModel):
    execution_id: str
    pipeline_kind: ExecutionKind
    pipeline_version: str
    run_at: datetime
    parameters: dict = Field(default_factory=dict)


class EvidenceRecord(BaseModel):
    evidence_id: str
    source_kind: EvidenceSourceKind

    title: str | None = None
    locator: str
    excerpt: str | None = None

    structured_value: dict | None = None
    units: str | None = None

    provenance: dict = Field(default_factory=dict)
    execution_context_id: str | None = None

    authority_score: float | None = None
    retrieved_at: datetime | None = None


class Claim(BaseModel):
    claim_id: str
    text: str
    claim_kind: ClaimKind

    scope: dict = Field(default_factory=dict)
    confidence: Confidence
    status: ClaimStatus


class ClaimEvidenceLink(BaseModel):
    link_id: str
    claim_id: str
    evidence_id: str

    relation: LinkRelation
    rationale: str
    strength: float  # 0.0 .. 1.0


class ClaimDependencyLink(BaseModel):
    link_id: str
    from_claim_id: str
    to_claim_id: str

    relation: ClaimDependencyRelation
    rationale: str


class InsightItem(BaseModel):
    insight_id: str
    text: str
    claim_refs: list[str]


class RecommendationItem(BaseModel):
    recommendation_id: str
    action: str
    rationale_claim_refs: list[str]
    dependency_claim_refs: list[str] = Field(default_factory=list)


class FinalProjection(BaseModel):
    summary_claim_refs: list[str]
    strengths: list[InsightItem] = Field(default_factory=list)
    weaknesses: list[InsightItem] = Field(default_factory=list)
    implications: list[InsightItem] = Field(default_factory=list)
    recommendations: list[RecommendationItem] = Field(default_factory=list)
    open_question_claim_refs: list[str] = Field(default_factory=list)


class ClaimGraphBundle(BaseModel):
    execution_contexts: list[ExecutionContext]
    evidence_records: list[EvidenceRecord]
    claims: list[Claim]
    claim_evidence_links: list[ClaimEvidenceLink]
    claim_dependency_links: list[ClaimDependencyLink]
    output: FinalProjection


class ClaimGraphDraft(BaseModel):
    """Draft slice produced by a model; merge with execution + evidence in application code."""

    claims: list[Claim]
    claim_evidence_links: list[ClaimEvidenceLink]
    claim_dependency_links: list[ClaimDependencyLink]
    output: FinalProjection


def index_by_id(items: list, attr: str) -> dict:
    return {getattr(x, attr): x for x in items}


_QUANT_RE = re.compile(
    r"(?:\b\d+(?:\.\d+)?\s*(?:%|percent|ppm|ppb|mg/kg|g/kg|t/ha|kg/ha|ha\b|°C|°F)\b)"
    r"|(?:\b\d+\.\d+\b)"
    r"|(?:\b\d{1,3}(?:,\d{3})+\b)"
    r"|(?:\b\d+\s*%\b)",
    re.IGNORECASE,
)


def _claim_has_quantitative_assertion(text: str) -> bool:
    return bool(_QUANT_RE.search(text))


def _is_evidence_backed(
    claim_id: str,
    evidence_links_by_claim: dict[str, list[ClaimEvidenceLink]],
    dep_from_claim: dict[str, list[ClaimDependencyLink]],
    memo: dict[str, bool],
    visiting: set[str],
) -> bool:
    """
    True when the claim has a grounded evidence path: strong direct support, two weaker
    evidence links, or a depends_on / derived_from chain to an evidence-backed claim.
    """
    if claim_id in memo:
        return memo[claim_id]
    if claim_id in visiting:
        return False
    visiting.add(claim_id)
    try:
        supports = evidence_links_by_claim.get(claim_id, [])
        strong_direct = [l for l in supports if l.relation == "direct_support" and l.strength >= 0.7]
        if strong_direct:
            memo[claim_id] = True
            return True

        weaker = [
            l
            for l in supports
            if l.relation in ("direct_support", "indirect_support") and 0.5 <= l.strength < 0.7
        ]
        if len(weaker) >= 2:
            memo[claim_id] = True
            return True

        for link in dep_from_claim.get(claim_id, []):
            if link.relation not in ("depends_on", "derived_from"):
                continue
            if _is_evidence_backed(
                link.to_claim_id, evidence_links_by_claim, dep_from_claim, memo, visiting
            ):
                memo[claim_id] = True
                return True

        memo[claim_id] = False
        return False
    finally:
        visiting.discard(claim_id)


def validate_claim_graph(bundle: ClaimGraphBundle) -> list[str]:
    errors: list[str] = []

    claims = index_by_id(bundle.claims, "claim_id")
    evidence = index_by_id(bundle.evidence_records, "evidence_id")
    execs = index_by_id(bundle.execution_contexts, "execution_id")

    for link in bundle.claim_evidence_links:
        if link.claim_id not in claims:
            errors.append(f"Missing claim for evidence link {link.link_id}: {link.claim_id}")
        if link.evidence_id not in evidence:
            errors.append(f"Missing evidence for evidence link {link.link_id}: {link.evidence_id}")

    for link in bundle.claim_dependency_links:
        if link.from_claim_id not in claims:
            errors.append(f"Missing from-claim for dependency {link.link_id}: {link.from_claim_id}")
        if link.to_claim_id not in claims:
            errors.append(f"Missing to-claim for dependency {link.link_id}: {link.to_claim_id}")

    all_output_claim_refs = list(bundle.output.summary_claim_refs)
    all_output_claim_refs += bundle.output.open_question_claim_refs
    for section in (bundle.output.strengths, bundle.output.weaknesses, bundle.output.implications):
        for item in section:
            all_output_claim_refs.extend(item.claim_refs)
    for rec in bundle.output.recommendations:
        all_output_claim_refs.extend(rec.rationale_claim_refs)
        all_output_claim_refs.extend(rec.dependency_claim_refs)

    for claim_id in all_output_claim_refs:
        if claim_id not in claims:
            errors.append(f"Output references missing claim: {claim_id}")

    evidence_links_by_claim: dict[str, list[ClaimEvidenceLink]] = {}
    for link in bundle.claim_evidence_links:
        evidence_links_by_claim.setdefault(link.claim_id, []).append(link)

    dep_from_claim: dict[str, list[ClaimDependencyLink]] = {}
    for link in bundle.claim_dependency_links:
        dep_from_claim.setdefault(link.from_claim_id, []).append(link)

    backing_memo: dict[str, bool] = {}
    for claim in bundle.claims:
        if claim.status != "supported":
            continue
        supports = evidence_links_by_claim.get(claim.claim_id, [])
        strong_direct = [l for l in supports if l.relation == "direct_support" and l.strength >= 0.7]
        outgoing = dep_from_claim.get(claim.claim_id, [])
        weaker = [
            l
            for l in supports
            if l.relation in ("direct_support", "indirect_support") and 0.5 <= l.strength < 0.7
        ]
        two_weaker = len(weaker) >= 2
        if not strong_direct and not outgoing and not two_weaker:
            errors.append(
                f"Supported claim has no support path (need strong direct, ≥2 weaker links, or claim deps): {claim.claim_id}"
            )

    for claim in bundle.claims:
        if claim.status != "supported" or claim.claim_kind != "recommendation":
            continue
        motivating = [
            l
            for l in dep_from_claim.get(claim.claim_id, [])
            if l.relation == "motivates"
            and claims[l.to_claim_id].claim_kind in ("observation", "inference")
        ]
        if not motivating:
            errors.append(
                f"Recommendation claim missing motivates dependency from observation/inference: {claim.claim_id}"
            )
            continue
        for link in motivating:
            if not _is_evidence_backed(
                link.to_claim_id,
                evidence_links_by_claim,
                dep_from_claim,
                backing_memo,
                set(),
            ):
                errors.append(
                    f"Recommendation {claim.claim_id} motivates claim {link.to_claim_id} without evidence-backed support path"
                )

    for claim in bundle.claims:
        if not _claim_has_quantitative_assertion(claim.text):
            continue
        linked_evidence_ids = {l.evidence_id for l in evidence_links_by_claim.get(claim.claim_id, [])}
        if not linked_evidence_ids:
            errors.append(f"Quantitative claim has no linked evidence: {claim.claim_id}")
            continue
        if not any(evidence[eid].structured_value for eid in linked_evidence_ids if eid in evidence):
            errors.append(
                f"Quantitative claim requires linked evidence with structured_value: {claim.claim_id}"
            )

    for ev in bundle.evidence_records:
        if ev.source_kind in {"measurement", "derived_metric", "benchmark"}:
            if not ev.provenance:
                errors.append(f"Evidence missing provenance: {ev.evidence_id}")
            if not ev.execution_context_id:
                errors.append(f"Evidence missing execution context: {ev.evidence_id}")
            elif ev.execution_context_id not in execs:
                errors.append(
                    f"Evidence references missing execution context: {ev.evidence_id} -> {ev.execution_context_id}"
                )

    return errors


def merge_claim_graph(
    draft: ClaimGraphDraft,
    execution_contexts: list[ExecutionContext],
    evidence_records: list[EvidenceRecord],
) -> ClaimGraphBundle:
    return ClaimGraphBundle(
        execution_contexts=execution_contexts,
        evidence_records=evidence_records,
        claims=draft.claims,
        claim_evidence_links=draft.claim_evidence_links,
        claim_dependency_links=draft.claim_dependency_links,
        output=draft.output,
    )
