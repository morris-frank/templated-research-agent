from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from research_agent.agent.schemas import CropDossierDraft
from research_agent.contracts.agronomy.dossier import CropDossier, LifecycleStageName
from research_agent.contracts.core.artifact_meta import ArtifactMeta
from research_agent.contracts.core.evidence import EvidenceRef
from research_agent.types import EvidenceItem


@dataclass(frozen=True)
class DroppedRef:
    kind: str
    location: str
    value: str
    reason: str


def evidence_items_to_refs(items: list[EvidenceItem]) -> list[EvidenceRef]:
    out: list[EvidenceRef] = []
    for item in items:
        source_type = item.source_type if item.source_type in {"web", "paper"} else "report"
        out.append(
            EvidenceRef(
                id=item.id,
                source_type=source_type,
                title=item.title or item.url,
                url=item.url,
                snippet=item.abstract_or_snippet or "",
                publisher=item.venue,
                authors=item.authors,
                year=item.year,
                doi=item.doi,
                score=item.score,
                query=item.raw.get("query") if isinstance(item.raw, dict) else None,
            )
        )
    return out


def _normalize_references(draft: CropDossierDraft) -> tuple[CropDossierDraft, list[DroppedRef]]:
    dropped: list[DroppedRef] = []
    intervention_ids = {i.id for i in draft.interventions}
    target_ids = {
        *(y.id for y in draft.yield_drivers),
        *(l.id for l in draft.limiting_factors),
        *(p.id for p in draft.pathogens),
        *(s.id for s in draft.soil_dependencies),
        *(m.id for m in draft.microbiome_roles),
    }
    normalized_effects = []
    for idx, eff in enumerate(draft.intervention_effects):
        if eff.intervention_id not in intervention_ids:
            dropped.append(
                DroppedRef(
                    kind="intervention_effect",
                    location=f"intervention_effects[{idx}]",
                    value=eff.intervention_id,
                    reason="unknown_intervention_id",
                )
            )
            continue
        if eff.target_ref not in target_ids:
            dropped.append(
                DroppedRef(
                    kind="intervention_effect",
                    location=f"intervention_effects[{idx}]",
                    value=eff.target_ref,
                    reason="unknown_target_ref",
                )
            )
            continue
        normalized_effects.append(eff)

    allowed_stages = set(LifecycleStageName.__args__)  # type: ignore[attr-defined]
    normalized_pathogens = []
    for p_idx, pathogen in enumerate(draft.pathogens):
        kept = []
        for s_idx, stage in enumerate(pathogen.affected_stages):
            if stage in allowed_stages:
                kept.append(stage)
            else:
                dropped.append(
                    DroppedRef(
                        kind="affected_stage",
                        location=f"pathogens[{p_idx}].affected_stages[{s_idx}]",
                        value=stage,
                        reason="not_a_lifecycle_stage",
                    )
                )
        normalized_pathogens.append(pathogen.model_copy(update={"affected_stages": kept}))

    normalized_cover_crop = []
    for idx, effect in enumerate(draft.cover_crop_effects):
        if effect.target_ref not in target_ids:
            dropped.append(
                DroppedRef(
                    kind="cover_crop_effect",
                    location=f"cover_crop_effects[{idx}]",
                    value=effect.target_ref,
                    reason="unknown_target_ref",
                )
            )
            continue
        normalized_cover_crop.append(effect)

    normalized = draft.model_copy(
        update={
            "intervention_effects": normalized_effects,
            "pathogens": normalized_pathogens,
            "cover_crop_effects": normalized_cover_crop,
        }
    )
    return normalized, dropped


def merge_crop_dossier(
    draft: CropDossierDraft,
    evidence_refs: list[EvidenceRef],
    *,
    artifact_id: str,
    now: datetime,
) -> tuple[CropDossier, list[DroppedRef]]:
    cleaned, dropped = _normalize_references(draft)
    dossier = CropDossier(
        meta=ArtifactMeta(
            artifact_id=artifact_id,
            artifact_type="crop_dossier",
            created_at=now,
            updated_at=now,
            tags=["agronomy"],
        ),
        last_updated=now.date(),
        evidence_index=evidence_refs,
        **cleaned.model_dump(),
    )
    return dossier, dropped


__all__ = ["DroppedRef", "evidence_items_to_refs", "merge_crop_dossier"]

