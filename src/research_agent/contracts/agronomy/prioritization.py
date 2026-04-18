"""Crop × use-case prioritization artifact (Tier 1 ranking, evidence-backed rationale)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from research_agent.contracts.core.claims import Claim

PriorityTier = Literal["T1", "T2", "T3"]


class CropUseCaseCandidate(BaseModel):
    """One prioritization row (stable id for joins and LLM output)."""

    candidate_id: str
    crop: str
    use_case: str
    crop_category: str | None = None
    notes: str | None = None


class ScoreComponents(BaseModel):
    """Explicit 0–1 components; aggregate is computed deterministically from these."""

    icp_fit: float = Field(ge=0.0, le=1.0, description="Fit with primary ICP (e.g. agri-input R&D).")
    platform_leverage: float = Field(ge=0.0, le=1.0, description="Leverage of platform / workflow fit.")
    data_availability: float = Field(ge=0.0, le=1.0, description="Observable data and trial comparability.")
    evidence_strength: float = Field(ge=0.0, le=1.0, description="Strength of retrieved evidence backing the row.")


class RankedCandidate(BaseModel):
    candidate: CropUseCaseCandidate
    components: ScoreComponents
    aggregate_score: float = Field(ge=0.0, le=1.0)
    rationale_claims: list[Claim] = Field(
        default_factory=list,
        description="Short claims supporting the rank; must cite evidence_ids from the retrieval run.",
    )


class TierList(BaseModel):
    tier: PriorityTier
    candidates: list[RankedCandidate] = Field(default_factory=list)


class PrioritizationResult(BaseModel):
    prioritization_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    rubric_version: str = "1.0"
    ranked: list[RankedCandidate] = Field(
        default_factory=list,
        description="All candidates sorted by aggregate_score descending.",
    )
    tier_lists: list[TierList] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
