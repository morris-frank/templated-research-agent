from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from research_agent.contracts.agronomy.dossier import (
    BeneficialOrganism,
    CoverCropEffect,
    CropCategory,
    HeuristicRule,
    Intervention,
    InterventionEffect,
    LifecycleStage,
    LimitingFactor,
    MicrobiomeFunction,
    Pathogen,
    PriorityTier,
    ProductionSystemContext,
    RotationRole,
    SoilDependency,
    YieldDriver,
)
from research_agent.types import EvidenceItem, InputVars, PlanOut

__all__ = [
    "Claim",
    "CropDossierDraft",
    "DossierAgronomicPartial",
    "DossierInterventionPartial",
    "DossierStructurePartial",
    "EvidenceItem",
    "FinalReport",
    "GapQueries",
    "InputVars",
    "PlanOut",
]


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    evidence_ids: list[str] = Field(min_length=1)
    evidence_urls: list[str] = Field(default_factory=list)
    support: Literal["direct", "partial", "contextual"] = "direct"
    notes: str | None = None


class FinalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    key_findings: list[Claim]
    scientific_evidence: list[Claim]
    market_context: list[Claim]
    open_questions: list[str]
    confidence: Literal["low", "medium", "high"]


class GapQueries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    web_queries: list[str] = Field(default_factory=list)
    paper_queries: list[str] = Field(default_factory=list)


class DossierStructurePartial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    crop_name: str
    crop_category: CropCategory
    primary_use_cases: list[str] = Field(default_factory=list)
    priority_tier: PriorityTier
    production_system_context: ProductionSystemContext = Field(default_factory=ProductionSystemContext)
    rotation_role: RotationRole = Field(default_factory=RotationRole)
    lifecycle_ontology: list[LifecycleStage] = Field(default_factory=list)


class DossierAgronomicPartial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    yield_drivers: list[YieldDriver] = Field(default_factory=list)
    limiting_factors: list[LimitingFactor] = Field(default_factory=list)
    agronomist_heuristics: list[HeuristicRule] = Field(default_factory=list)


class DossierInterventionPartial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interventions: list[Intervention] = Field(default_factory=list)
    intervention_effects: list[InterventionEffect] = Field(default_factory=list)
    pathogens: list[Pathogen] = Field(default_factory=list)
    beneficials: list[BeneficialOrganism] = Field(default_factory=list)
    soil_dependencies: list[SoilDependency] = Field(default_factory=list)
    microbiome_roles: list[MicrobiomeFunction] = Field(default_factory=list)
    cover_crop_effects: list[CoverCropEffect] = Field(default_factory=list)
    confidence: float = 0.0
    open_questions: list[str] = Field(default_factory=list)


class CropDossierDraft(BaseModel):
    """Near-final dossier shape produced by LLM, excluding meta/evidence envelope."""

    model_config = ConfigDict(extra="forbid")

    crop_name: str
    crop_category: CropCategory
    primary_use_cases: list[str] = Field(default_factory=list)
    priority_tier: PriorityTier
    production_system_context: ProductionSystemContext = Field(default_factory=ProductionSystemContext)
    rotation_role: RotationRole = Field(default_factory=RotationRole)
    lifecycle_ontology: list[LifecycleStage] = Field(default_factory=list)
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
    confidence: float = 0.0
    open_questions: list[str] = Field(default_factory=list)
