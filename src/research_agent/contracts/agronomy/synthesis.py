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
    "intervention_effect_link",
    "beneficial",
    "cover_crop_effect",
    "production_context",
    "rotation_claim",
    "open_question",
    "heuristic_rule",
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

RelationKind = Literal["depends_on", "affects", "mitigated_by", "observed_in_stage", "targets"]


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
    """Minimal taxonomy node (pattern-backed cross-crop inventory)."""

    node_id: str
    label: str
    kind: ConceptKind
    pattern_id: str | None = None


class OntologyEdge(BaseModel):
    """Deterministic relationship between endpoints (stable node ids)."""

    edge_id: str
    relation: RelationKind
    source_node_id: str
    target_node_id: str
    provenance: dict[str, Any] = Field(default_factory=dict)


class PlatformPrimitive(BaseModel):
    """Derived primitive from repeated cross-crop patterns or composite rules."""

    primitive_id: str
    kind: PrimitiveKind
    label: str
    supporting_pattern_ids: list[str] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(
        default_factory=dict,
        description="e.g. composite_rule when derived from co-occurring patterns.",
    )


class SynthesisOutput(BaseModel):
    synthesis_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = "1.1"
    normalized_concepts: list[NormalizedConcept] = Field(default_factory=list)
    cross_crop_patterns: list[CrossCropPattern] = Field(default_factory=list)
    ontology_nodes: list[OntologyNode] = Field(default_factory=list)
    ontology_edges: list[OntologyEdge] = Field(default_factory=list)
    platform_primitives: list[PlatformPrimitive] = Field(default_factory=list)
    prioritization_context: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Optional manifest metadata only; not used to derive concepts in v1.",
    )
    validation_warnings: list[str] = Field(default_factory=list)
