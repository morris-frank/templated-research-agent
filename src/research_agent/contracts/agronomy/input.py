from __future__ import annotations

from pydantic import BaseModel, Field

from research_agent.contracts.agronomy.dossier import CropCategory, PriorityTier


class DossierInputVars(BaseModel):
    """Seed context for building a crop dossier artifact."""

    crop_name: str
    crop_category: CropCategory
    primary_use_cases: list[str] = Field(default_factory=list)
    priority_tier: PriorityTier = "T2"
    use_case: str | None = None

