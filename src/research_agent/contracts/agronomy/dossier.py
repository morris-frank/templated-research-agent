from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from research_agent.contracts.core.artifact_meta import ArtifactMeta
from research_agent.contracts.core.claims import Claim
from research_agent.contracts.core.evidence import EvidenceRef

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

InterventionKind = Literal["input", "management", "genetic"]
EffectDirection = Literal["increase", "decrease", "conditional"]


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


class YieldDriver(BaseModel):
    """Causal factor whose state meaningfully influences yield outcomes."""

    id: str
    name: str
    mechanism: Claim
    measurable_proxies: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class LimitingFactor(BaseModel):
    """Common constraint that caps or depresses yield at a particular stage."""

    id: str
    factor: str
    stage: LifecycleStageName | None = None
    symptoms: list[Claim] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class HeuristicRule(BaseModel):
    """Agronomist decision rule: free-form condition expression for now."""

    id: str
    condition: str
    action: str
    rationale: Claim
    evidence_ids: list[str] = Field(default_factory=list)


class Intervention(BaseModel):
    id: str
    kind: InterventionKind
    name: str
    evidence_ids: list[str] = Field(default_factory=list)


class InterventionEffect(BaseModel):
    """Effect of a single intervention on a target entity (driver/pathogen/soil)."""

    intervention_id: str
    target_ref: str
    effect: EffectDirection
    rationale: Claim | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class Pathogen(BaseModel):
    id: str
    name: str
    pressure_conditions: list[str] = Field(default_factory=list)
    affected_stages: list[LifecycleStageName] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class BeneficialOrganism(BaseModel):
    id: str
    name: str
    function: str
    evidence_ids: list[str] = Field(default_factory=list)


class SoilDependency(BaseModel):
    id: str
    variable: str
    role: Claim
    evidence_ids: list[str] = Field(default_factory=list)


class MicrobiomeFunction(BaseModel):
    id: str
    function: str
    importance: Claim
    evidence_ids: list[str] = Field(default_factory=list)


class CoverCropEffect(BaseModel):
    cover_crop: str
    target_ref: str
    effect: Claim
    evidence_ids: list[str] = Field(default_factory=list)


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

    yield_drivers: list[YieldDriver] = Field(default_factory=list)
    limiting_factors: list[LimitingFactor] = Field(default_factory=list)
    agronomist_heuristics: list[HeuristicRule] = Field(default_factory=list)

    interventions: list[Intervention] = Field(default_factory=list)
    intervention_effects: list[InterventionEffect] = Field(default_factory=list)

    pathogens: list[Pathogen] = Field(default_factory=list)
    beneficials: list[BeneficialOrganism] = Field(default_factory=list)

    soil_dependencies: list[SoilDependency] = Field(default_factory=list)
    microbiome_roles: list[MicrobiomeFunction] = Field(default_factory=list)

    cover_crop_effects: list[CoverCropEffect] = Field(default_factory=list)

    evidence_index: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = 0.0
    open_questions: list[str] = Field(default_factory=list)

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
