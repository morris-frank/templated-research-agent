from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from contracts.core.artifact_meta import ArtifactMeta
from contracts.core.claims import Claim

CropCategory = Literal["cereal", "tuber", "legume", "horticulture", "specialty"]
PriorityTier = Literal["T1", "T2", "T3"]
LifecycleStageName = Literal[
    "Pre-plant",
    "Establishment",
    "Vegetative",
    "Reproductive",
    "Senescence",
    "Post-harvest",
]


class LifecycleStage(BaseModel):
    stage: LifecycleStageName
    description: str = ""
    key_decisions: list[Claim] = Field(default_factory=list)
    observables: list[Claim] = Field(default_factory=list)
    failure_modes: list[Claim] = Field(default_factory=list)


class ProductionSystemContext(BaseModel):
    core_regions: list[str] = Field(default_factory=list)
    climate_zones: list[str] = Field(default_factory=list)
    environments: list[str] = Field(
        default_factory=list, description="open field / greenhouse / trial station"
    )
    management_modes: list[str] = Field(
        default_factory=list, description="conventional / organic / biological-heavy"
    )


class RotationRole(BaseModel):
    typical_preceding_crops: list[Claim] = Field(default_factory=list)
    typical_succeeding_crops: list[Claim] = Field(default_factory=list)
    known_rotation_effects: list[Claim] = Field(default_factory=list)


class CropDossier(BaseModel):
    meta: ArtifactMeta
    crop_name: str
    crop_category: CropCategory
    primary_use_cases: list[str] = Field(default_factory=list)
    priority_tier: PriorityTier
    last_updated: date

    production_system_context: ProductionSystemContext = Field(default_factory=ProductionSystemContext)
    rotation_role: RotationRole = Field(default_factory=RotationRole)
    lifecycle_ontology: list[LifecycleStage]

    def validate_required_stages(self) -> list[str]:
        required = {
            "Pre-plant",
            "Establishment",
            "Vegetative",
            "Reproductive",
            "Senescence",
            "Post-harvest",
        }
        present = {stage.stage for stage in self.lifecycle_ontology}
        return sorted(required - present)
