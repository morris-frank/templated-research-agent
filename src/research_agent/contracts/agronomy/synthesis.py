"""Cross-crop synthesis artifacts (deterministic grouping over dossier + questionnaire JSON).

v1 does not ingest claim graphs; concept sources are dossier and questionnaire content only.
Prioritization may appear as optional manifest metadata, not as a driver for extraction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

ConceptKind = Literal[
    "lifecycle_stage",
    "yield_driver",
    "limiting_factor",
    "intervention",
    "pathogen",
    "microbiome",
    "soil",
    "questionnaire_answer",
    "questionnaire_claim",
]

PrimitiveKind = Literal[
    "pathogen_pressure",
    "intervention_effect",
    "lifecycle_stage",
    "microbiome_function",
    "trial_confounder",
    "monitoring_target",
    "yield_limiting_factor",
]


class NormalizedConcept(BaseModel):
    """One extracted, normalized string concept tied to a source run."""

    concept_key: str = Field(description="Stable key: kind + normalized label")
    kind: ConceptKind
    label: str = Field(description="Human-readable label after normalization")
    source_run_id: str
    source_artifact: Literal["dossier", "questionnaire"]
    provenance: dict[str, Any] = Field(default_factory=dict)


class CrossCropPattern(BaseModel):
    """Same normalized concept observed across multiple runs (thresholded)."""

    pattern_id: str
    kind: ConceptKind
    normalized_label: str
    run_ids: list[str] = Field(default_factory=list)
    mention_count: int = 0


class OntologyNode(BaseModel):
    """Minimal taxonomy node for v1 (pattern graph, not a full ontology)."""

    node_id: str
    label: str
    kind: ConceptKind
    pattern_id: str | None = None


class PlatformPrimitive(BaseModel):
    """Derived primitive from repeated cross-crop patterns."""

    primitive_id: str
    kind: PrimitiveKind
    label: str
    supporting_pattern_ids: list[str] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)


class SynthesisOutput(BaseModel):
    synthesis_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = "1.0"
    normalized_concepts: list[NormalizedConcept] = Field(default_factory=list)
    cross_crop_patterns: list[CrossCropPattern] = Field(default_factory=list)
    ontology_nodes: list[OntologyNode] = Field(default_factory=list)
    platform_primitives: list[PlatformPrimitive] = Field(default_factory=list)
    prioritization_context: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Optional manifest metadata only; not used to derive concepts in v1.",
    )
    validation_warnings: list[str] = Field(default_factory=list)
