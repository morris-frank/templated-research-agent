"""Structured validation for :class:`CropDossier`.

Mirrors the shape of :func:`research_agent.contracts.core.claim_graph.validate_claim_graph_detailed`:
errors-only today, with ``ValidationIssue(level="error", code=..., message=...)`` for stable
machine-readable codes. Thresholds (minimum yield drivers / interventions / pathogens /
evidence-linkage fraction) are configurable via :class:`DossierThresholds` so callers can
tune them per workflow without forking the validator.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from research_agent.contracts.agronomy.dossier import CropDossier
from research_agent.contracts.core.claim_graph import ValidationIssue


class DossierThresholds(BaseModel):
    min_yield_drivers: int = 3
    min_interventions: int = 3
    min_pathogens: int = 2
    min_evidence_linked_fraction: float = 0.5
    min_evidence_linked_per_section: dict[str, int] = Field(
        default_factory=lambda: {"yield_drivers": 1, "interventions": 1, "pathogens": 1}
    )


class CropDossierValidationResult(BaseModel):
    ok: bool
    errors: list[ValidationIssue] = Field(default_factory=list)


def _err(code: str, message: str) -> ValidationIssue:
    return ValidationIssue(level="error", code=code, message=message)


def _collect_target_ids(dossier: CropDossier) -> set[str]:
    """IDs that an InterventionEffect.target_ref may legitimately point to."""
    ids: set[str] = set()
    ids.update(d.id for d in dossier.yield_drivers)
    ids.update(p.id for p in dossier.pathogens)
    ids.update(s.id for s in dossier.soil_dependencies)
    ids.update(m.id for m in dossier.microbiome_roles)
    ids.update(l.id for l in dossier.limiting_factors)
    return ids


def _iter_evidence_bearers(dossier: CropDossier):
    """Yield (label, evidence_ids) for every object in the dossier that carries evidence_ids.

    Used both for dangling-reference checks and coverage computation.
    """
    for d in dossier.yield_drivers:
        yield f"yield_driver:{d.id}", d.evidence_ids
        yield f"yield_driver:{d.id}:mechanism", d.mechanism.evidence_ids
    for f in dossier.limiting_factors:
        yield f"limiting_factor:{f.id}", f.evidence_ids
        for i, sym in enumerate(f.symptoms):
            yield f"limiting_factor:{f.id}:symptom[{i}]", sym.evidence_ids
    for h in dossier.agronomist_heuristics:
        yield f"heuristic:{h.id}", h.evidence_ids
        yield f"heuristic:{h.id}:rationale", h.rationale.evidence_ids
    for iv in dossier.interventions:
        yield f"intervention:{iv.id}", iv.evidence_ids
    for i, eff in enumerate(dossier.intervention_effects):
        yield f"intervention_effect[{i}]", eff.evidence_ids
        if eff.rationale is not None:
            yield f"intervention_effect[{i}]:rationale", eff.rationale.evidence_ids
    for p in dossier.pathogens:
        yield f"pathogen:{p.id}", p.evidence_ids
    for b in dossier.beneficials:
        yield f"beneficial:{b.id}", b.evidence_ids
    for s in dossier.soil_dependencies:
        yield f"soil_dependency:{s.id}", s.evidence_ids
        yield f"soil_dependency:{s.id}:role", s.role.evidence_ids
    for m in dossier.microbiome_roles:
        yield f"microbiome_role:{m.id}", m.evidence_ids
        yield f"microbiome_role:{m.id}:importance", m.importance.evidence_ids
    for i, cc in enumerate(dossier.cover_crop_effects):
        yield f"cover_crop_effect[{i}]", cc.evidence_ids
        yield f"cover_crop_effect[{i}]:effect", cc.effect.evidence_ids

    # Legacy Claim-bearing fields on existing dossier sub-structures.
    for stage in dossier.lifecycle_ontology:
        for i, c in enumerate(stage.key_decisions):
            yield f"lifecycle:{stage.stage}:key_decisions[{i}]", c.evidence_ids
        for i, c in enumerate(stage.observables):
            yield f"lifecycle:{stage.stage}:observables[{i}]", c.evidence_ids
        for i, c in enumerate(stage.failure_modes):
            yield f"lifecycle:{stage.stage}:failure_modes[{i}]", c.evidence_ids
    for i, c in enumerate(dossier.rotation_role.typical_preceding_crops):
        yield f"rotation_role:typical_preceding_crops[{i}]", c.evidence_ids
    for i, c in enumerate(dossier.rotation_role.typical_succeeding_crops):
        yield f"rotation_role:typical_succeeding_crops[{i}]", c.evidence_ids
    for i, c in enumerate(dossier.rotation_role.known_rotation_effects):
        yield f"rotation_role:known_rotation_effects[{i}]", c.evidence_ids


def validate_crop_dossier_detailed(
    dossier: CropDossier,
    thresholds: DossierThresholds | None = None,
) -> CropDossierValidationResult:
    """Return structured validation result with machine-readable error codes."""
    th = thresholds or DossierThresholds()
    errors: list[ValidationIssue] = []

    missing_stages = dossier.validate_required_stages()
    if missing_stages:
        errors.append(
            _err(
                "lifecycle_missing_stages",
                f"Missing required lifecycle stages: {', '.join(missing_stages)}",
            )
        )

    if len(dossier.yield_drivers) < th.min_yield_drivers:
        errors.append(
            _err(
                "too_few_yield_drivers",
                f"Dossier has {len(dossier.yield_drivers)} yield drivers; "
                f"threshold is {th.min_yield_drivers}",
            )
        )
    if len(dossier.interventions) < th.min_interventions:
        errors.append(
            _err(
                "too_few_interventions",
                f"Dossier has {len(dossier.interventions)} interventions; "
                f"threshold is {th.min_interventions}",
            )
        )
    if len(dossier.pathogens) < th.min_pathogens:
        errors.append(
            _err(
                "too_few_pathogens",
                f"Dossier has {len(dossier.pathogens)} pathogens; "
                f"threshold is {th.min_pathogens}",
            )
        )

    intervention_ids = {iv.id for iv in dossier.interventions}
    target_ids = _collect_target_ids(dossier)
    for i, eff in enumerate(dossier.intervention_effects):
        if eff.intervention_id not in intervention_ids:
            errors.append(
                _err(
                    "intervention_effect_dangling_fk",
                    f"intervention_effects[{i}].intervention_id "
                    f"{eff.intervention_id!r} does not reference a known Intervention.id",
                )
            )
        if eff.target_ref not in target_ids:
            errors.append(
                _err(
                    "intervention_effect_dangling_fk",
                    f"intervention_effects[{i}].target_ref {eff.target_ref!r} does not "
                    "reference a known yield_driver / pathogen / soil_dependency / "
                    "microbiome_role / limiting_factor id",
                )
            )

    known_evidence_ids = {e.id for e in dossier.evidence_index}
    dangling_seen: set[tuple[str, str]] = set()
    total_bearers = 0
    evidence_linked = 0
    for label, eids in _iter_evidence_bearers(dossier):
        total_bearers += 1
        if eids:
            evidence_linked += 1
        for eid in eids:
            if eid not in known_evidence_ids:
                key = (label, eid)
                if key not in dangling_seen:
                    dangling_seen.add(key)
                    errors.append(
                        _err(
                            "evidence_id_dangling",
                            f"{label} references evidence_id {eid!r} which is not in evidence_index",
                        )
                    )

    if total_bearers > 0:
        fraction = evidence_linked / total_bearers
        if fraction < th.min_evidence_linked_fraction:
            errors.append(
                _err(
                    "low_evidence_coverage",
                    f"{evidence_linked}/{total_bearers} evidence-bearing items have at "
                    f"least one evidence_id ({fraction:.0%}); threshold is "
                    f"{th.min_evidence_linked_fraction:.0%}",
                )
            )

    section_floors = th.min_evidence_linked_per_section
    section_counts = {
        "yield_drivers": sum(1 for item in dossier.yield_drivers if item.evidence_ids),
        "interventions": sum(1 for item in dossier.interventions if item.evidence_ids),
        "pathogens": sum(1 for item in dossier.pathogens if item.evidence_ids),
    }
    for section, floor in section_floors.items():
        if section_counts.get(section, 0) < floor:
            errors.append(
                _err(
                    f"per_section_evidence_floor:{section}",
                    f"Section {section!r} has {section_counts.get(section, 0)} evidence-linked items; floor is {floor}",
                )
            )

    return CropDossierValidationResult(ok=not errors, errors=errors)


def validate_crop_dossier(
    dossier: CropDossier,
    thresholds: DossierThresholds | None = None,
) -> list[str]:
    """Return human-readable error messages only.

    For error codes and structured reports, use :func:`validate_crop_dossier_detailed`.
    """
    return [e.message for e in validate_crop_dossier_detailed(dossier, thresholds).errors]


__all__ = [
    "DossierThresholds",
    "CropDossierValidationResult",
    "validate_crop_dossier_detailed",
    "validate_crop_dossier",
]
