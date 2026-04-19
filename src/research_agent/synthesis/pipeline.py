"""Deterministic cross-crop synthesis from dossier + questionnaire JSON (v1: no claim graphs)."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from research_agent.contracts.agronomy.dossier import CropDossier
from research_agent.contracts.agronomy.synthesis import (
    ConceptKind,
    CrossCropPattern,
    NormalizedConcept,
    OntologyNode,
    PlatformPrimitive,
    PrimitiveKind,
    SynthesisOutput,
)
from research_agent.contracts.core.questionnaire import QuestionnaireExecutionResult


def _norm_label(label: str) -> str:
    return " ".join(label.lower().split())


def _concept_key(kind: ConceptKind, label: str) -> str:
    return f"{kind}:{_norm_label(label)}"


_KIND_TO_PRIMITIVE: dict[ConceptKind, PrimitiveKind] = {
    "lifecycle_stage": "lifecycle_stage",
    "yield_driver": "monitoring_target",
    "limiting_factor": "yield_limiting_factor",
    "intervention": "intervention_effect",
    "pathogen": "pathogen_pressure",
    "microbiome": "microbiome_function",
    "soil": "monitoring_target",
    "questionnaire_answer": "trial_confounder",
    "questionnaire_claim": "monitoring_target",
}


def extract_concepts_from_dossier(dossier: CropDossier, run_id: str) -> list[NormalizedConcept]:
    out: list[NormalizedConcept] = []
    for st in dossier.lifecycle_ontology:
        lab = st.stage
        k: ConceptKind = "lifecycle_stage"
        out.append(
            NormalizedConcept(
                concept_key=_concept_key(k, lab),
                kind=k,
                label=_norm_label(lab),
                source_run_id=run_id,
                source_artifact="dossier",
                provenance={"field": "lifecycle_ontology.stage"},
            )
        )
    for yd in dossier.yield_drivers:
        k = "yield_driver"
        out.append(
            NormalizedConcept(
                concept_key=_concept_key(k, yd.name),
                kind=k,
                label=_norm_label(yd.name),
                source_run_id=run_id,
                source_artifact="dossier",
                provenance={"field": "yield_drivers", "id": yd.id},
            )
        )
    for lf in dossier.limiting_factors:
        k = "limiting_factor"
        out.append(
            NormalizedConcept(
                concept_key=_concept_key(k, lf.factor),
                kind=k,
                label=_norm_label(lf.factor),
                source_run_id=run_id,
                source_artifact="dossier",
                provenance={"field": "limiting_factors", "id": lf.id},
            )
        )
    for inv in dossier.interventions:
        k = "intervention"
        out.append(
            NormalizedConcept(
                concept_key=_concept_key(k, inv.name),
                kind=k,
                label=_norm_label(inv.name),
                source_run_id=run_id,
                source_artifact="dossier",
                provenance={"field": "interventions", "id": inv.id},
            )
        )
    for p in dossier.pathogens:
        k = "pathogen"
        out.append(
            NormalizedConcept(
                concept_key=_concept_key(k, p.name),
                kind=k,
                label=_norm_label(p.name),
                source_run_id=run_id,
                source_artifact="dossier",
                provenance={"field": "pathogens", "id": p.id},
            )
        )
    for m in dossier.microbiome_roles:
        k = "microbiome"
        out.append(
            NormalizedConcept(
                concept_key=_concept_key(k, m.function),
                kind=k,
                label=_norm_label(m.function),
                source_run_id=run_id,
                source_artifact="dossier",
                provenance={"field": "microbiome_roles", "id": m.id},
            )
        )
    for s in dossier.soil_dependencies:
        k = "soil"
        out.append(
            NormalizedConcept(
                concept_key=_concept_key(k, s.variable),
                kind=k,
                label=_norm_label(s.variable),
                source_run_id=run_id,
                source_artifact="dossier",
                provenance={"field": "soil_dependencies", "id": s.id},
            )
        )
    return out


def extract_concepts_from_questionnaire(qexec: QuestionnaireExecutionResult, run_id: str) -> list[NormalizedConcept]:
    out: list[NormalizedConcept] = []
    for r in qexec.responses.responses:
        if not r.is_useful():
            continue
        blob = (r.answer_markdown or "")[:800]
        if blob.strip():
            k: ConceptKind = "questionnaire_answer"
            lab = blob.strip().split("\n", 1)[0][:240]
            out.append(
                NormalizedConcept(
                    concept_key=_concept_key(k, lab),
                    kind=k,
                    label=_norm_label(lab),
                    source_run_id=run_id,
                    source_artifact="questionnaire",
                    provenance={"question_id": r.question_id, "field": "answer_markdown"},
                )
            )
        for c in r.key_claims:
            if not c.text.strip():
                continue
            k2: ConceptKind = "questionnaire_claim"
            lt = c.text.strip()
            out.append(
                NormalizedConcept(
                    concept_key=_concept_key(k2, lt),
                    kind=k2,
                    label=_norm_label(lt[:500]),
                    source_run_id=run_id,
                    source_artifact="questionnaire",
                    provenance={"question_id": r.question_id, "field": "key_claims"},
                )
            )
    return out


def run_synthesis(
    *,
    runs: list[dict[str, Any]],
    base_path: Path,
    min_crops_for_pattern: int = 2,
    min_mentions: int = 1,
) -> SynthesisOutput:
    """Load dossier (required) and optional questionnaire per run; aggregate patterns."""
    all_concepts: list[NormalizedConcept] = []
    contexts: list[dict[str, Any]] = []
    warnings: list[str] = []

    for run in runs:
        run_id = str(run["run_id"])
        if "prioritization_context" in run and run["prioritization_context"] is not None:
            ctx = dict(run["prioritization_context"])
            ctx["run_id"] = run_id
            contexts.append(ctx)

        dossier_path = base_path / run["dossier"]
        raw_d = json.loads(dossier_path.read_text(encoding="utf-8"))
        dossier = CropDossier.model_validate(raw_d)
        all_concepts.extend(extract_concepts_from_dossier(dossier, run_id))

        qpath = run.get("questionnaire")
        if qpath:
            qraw = json.loads((base_path / qpath).read_text(encoding="utf-8"))
            qexec = QuestionnaireExecutionResult.model_validate(qraw)
            all_concepts.extend(extract_concepts_from_questionnaire(qexec, run_id))
        elif run.get("questionnaire") is not None:
            warnings.append(f"run {run_id}: questionnaire path missing or null")

    # Group by concept_key
    by_key: dict[str, list[NormalizedConcept]] = defaultdict(list)
    for c in all_concepts:
        by_key[c.concept_key].append(c)

    patterns: list[CrossCropPattern] = []
    nodes: list[OntologyNode] = []
    primitives: list[PlatformPrimitive] = []
    pid = 0

    for key, items in by_key.items():
        run_ids = sorted({i.source_run_id for i in items})
        mention_count = len(items)
        if not items:
            continue
        kind = items[0].kind
        label = items[0].label
        if len(run_ids) >= min_crops_for_pattern and mention_count >= min_mentions:
            pid += 1
            pat_id = f"pat-{pid:04d}"
            patterns.append(
                CrossCropPattern(
                    pattern_id=pat_id,
                    kind=kind,
                    normalized_label=label,
                    run_ids=run_ids,
                    mention_count=mention_count,
                )
            )
            nodes.append(
                OntologyNode(
                    node_id=f"node-{pid:04d}",
                    label=label,
                    kind=kind,
                    pattern_id=pat_id,
                )
            )
            pk = _KIND_TO_PRIMITIVE.get(kind)
            if pk:
                primitives.append(
                    PlatformPrimitive(
                        primitive_id=f"prim-{uuid.uuid4().hex[:10]}",
                        kind=pk,
                        label=label,
                        supporting_pattern_ids=[pat_id],
                        run_ids=run_ids,
                    )
                )

    return SynthesisOutput(
        synthesis_id=f"syn-{uuid.uuid4().hex[:12]}",
        normalized_concepts=all_concepts,
        cross_crop_patterns=patterns,
        ontology_nodes=nodes,
        platform_primitives=primitives,
        prioritization_context=contexts,
        validation_warnings=warnings,
    )


def load_manifest(path: Path) -> tuple[list[dict[str, Any]], Path, int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    runs = data.get("runs") or data.get("inputs")
    if not isinstance(runs, list) or not runs:
        raise ValueError("manifest must contain a non-empty 'runs' or 'inputs' array")
    base = path.parent
    th = data.get("thresholds") if isinstance(data.get("thresholds"), dict) else {}
    min_crops = int(data.get("min_crops_for_pattern", th.get("min_crops", 2)))
    min_m = int(data.get("min_mentions", th.get("min_mentions", 1)))
    return runs, base, min_crops, min_m
