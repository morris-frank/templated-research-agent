"""Deterministic cross-crop synthesis from dossier + questionnaire JSON (Phase 4.1: IDs, edges, validation)."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from research_agent.contracts.agronomy.dossier import CropDossier
from research_agent.contracts.agronomy.synthesis import (
    ConceptKind,
    CrossCropPattern,
    NormalizedConcept,
    OntologyEdge,
    OntologyNode,
    PlatformPrimitive,
    PrimitiveKind,
    RelationKind,
    SynthesisOutput,
)
from research_agent.contracts.core.questionnaire import QuestionnaireExecutionResult, QuestionnaireSpec
from research_agent.synthesis.manifest import SynthesisManifest


def _norm_label(label: str) -> str:
    return " ".join(label.lower().split())


def _concept_key(kind: ConceptKind, label: str) -> str:
    return f"{kind}:{_norm_label(label)}"


def short_hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]


def stable_node_id(kind: str, label: str) -> str:
    return f"n-{short_hash(kind, _norm_label(label))}"


def canonical_json_obj(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def synthesis_id_from_runs(
    run_payloads: list[tuple[str, dict[str, Any], dict[str, Any] | None]],
) -> str:
    """Content-addressed id from ordered (run_id, dossier_dict, questionnaire_dict_or_none)."""
    blob = []
    for run_id, d, q in run_payloads:
        blob.append(
            {
                "run_id": run_id,
                "dossier": d,
                "questionnaire": q,
            }
        )
    canonical = json.dumps(blob, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"syn-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def resolve_safe_path(base: Path, rel: str) -> Path:
    if not rel or Path(rel).is_absolute():
        raise ValueError(f"path must be relative to manifest directory: {rel!r}")
    base_r = base.resolve()
    target = (base_r / rel).resolve()
    try:
        target.relative_to(base_r)
    except ValueError as e:
        raise ValueError(f"path escapes manifest directory: {rel!r}") from e
    return target


_KIND_TO_PRIMITIVE: dict[str, PrimitiveKind] = {
    "lifecycle_stage": "lifecycle_stage",
    "yield_driver": "monitoring_target",
    "limiting_factor": "yield_limiting_factor",
    "intervention": "intervention_effect",
    "pathogen": "pathogen_pressure",
    "microbiome": "microbiome_function",
    "soil": "monitoring_target",
    "questionnaire_answer": "trial_confounder",
    "questionnaire_claim": "monitoring_target",
    "intervention_effect_link": "intervention_effect",
    "beneficial": "microbiome_function",
    "cover_crop_effect": "intervention_effect",
    "production_context": "monitoring_target",
    "rotation_claim": "monitoring_target",
    "open_question": "trial_confounder",
    "heuristic_rule": "monitoring_target",
}


def _intervention_name(dossier: CropDossier, intervention_id: str) -> str:
    for inv in dossier.interventions:
        if inv.id == intervention_id:
            return inv.name
    return intervention_id


def _resolve_target_label(dossier: CropDossier, target_ref: str) -> tuple[str, ConceptKind]:
    for yd in dossier.yield_drivers:
        if yd.id == target_ref:
            return yd.name, "yield_driver"
    for p in dossier.pathogens:
        if p.id == target_ref:
            return p.name, "pathogen"
    for lf in dossier.limiting_factors:
        if lf.id == target_ref:
            return lf.factor, "limiting_factor"
    for s in dossier.soil_dependencies:
        if s.id == target_ref:
            return s.variable, "soil"
    for m in dossier.microbiome_roles:
        if m.id == target_ref:
            return m.function, "microbiome"
    return target_ref, "yield_driver"


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
        for cl in st.key_decisions + st.observables + st.failure_modes:
            if cl.text.strip():
                kk: ConceptKind = "rotation_claim"
                tx = cl.text.strip()
                out.append(
                    NormalizedConcept(
                        concept_key=_concept_key(kk, tx[:500]),
                        kind=kk,
                        label=_norm_label(tx[:500]),
                        source_run_id=run_id,
                        source_artifact="dossier",
                        provenance={"field": "lifecycle_ontology.claim"},
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
    for hr in dossier.agronomist_heuristics:
        k = "heuristic_rule"
        lab = f"{hr.condition} -> {hr.action}"
        out.append(
            NormalizedConcept(
                concept_key=_concept_key(k, lab),
                kind=k,
                label=_norm_label(lab)[:500],
                source_run_id=run_id,
                source_artifact="dossier",
                provenance={"field": "agronomist_heuristics", "id": hr.id},
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
    for ie in dossier.intervention_effects:
        tgt_name, tgt_kind = _resolve_target_label(dossier, ie.target_ref)
        inv_name = _intervention_name(dossier, ie.intervention_id)
        lab = f"{inv_name}->{tgt_name}:{ie.effect!s}"
        k = "intervention_effect_link"
        out.append(
            NormalizedConcept(
                concept_key=_concept_key(k, lab),
                kind=k,
                label=_norm_label(lab)[:500],
                source_run_id=run_id,
                source_artifact="dossier",
                provenance={
                    "field": "intervention_effects",
                    "intervention_id": ie.intervention_id,
                    "target_ref": ie.target_ref,
                },
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
    for b in dossier.beneficials:
        k = "beneficial"
        lab = f"{b.name}:{b.function}"
        out.append(
            NormalizedConcept(
                concept_key=_concept_key(k, lab),
                kind=k,
                label=_norm_label(lab)[:500],
                source_run_id=run_id,
                source_artifact="dossier",
                provenance={"field": "beneficials", "id": b.id},
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
    for cce in dossier.cover_crop_effects:
        k = "cover_crop_effect"
        lab = f"{cce.cover_crop}->{cce.target_ref}"
        eff = cce.effect.text.strip() if cce.effect.text else ""
        lab = f"{lab}:{eff}"[:500]
        out.append(
            NormalizedConcept(
                concept_key=_concept_key(k, lab),
                kind=k,
                label=_norm_label(lab)[:500],
                source_run_id=run_id,
                source_artifact="dossier",
                provenance={"field": "cover_crop_effects"},
            )
        )
    ctx = dossier.production_system_context
    for region in ctx.core_regions + ctx.climate_zones + ctx.environments + ctx.management_modes:
        if region.strip():
            k = "production_context"
            out.append(
                NormalizedConcept(
                    concept_key=_concept_key(k, region),
                    kind=k,
                    label=_norm_label(region),
                    source_run_id=run_id,
                    source_artifact="dossier",
                    provenance={"field": "production_system_context"},
                )
            )
    for cl in dossier.rotation_role.typical_preceding_crops + dossier.rotation_role.typical_succeeding_crops:
        if cl.text.strip():
            k = "rotation_claim"
            tx = cl.text.strip()
            out.append(
                NormalizedConcept(
                    concept_key=_concept_key(k, tx[:500]),
                    kind=k,
                    label=_norm_label(tx[:500]),
                    source_run_id=run_id,
                    source_artifact="dossier",
                    provenance={"field": "rotation_role"},
                )
            )
    for oq in dossier.open_questions:
        if oq.strip():
            k = "open_question"
            out.append(
                NormalizedConcept(
                    concept_key=_concept_key(k, oq[:500]),
                    kind=k,
                    label=_norm_label(oq[:500]),
                    source_run_id=run_id,
                    source_artifact="dossier",
                    provenance={"field": "open_questions"},
                )
            )
    return out


def extract_concepts_from_questionnaire(
    qexec: QuestionnaireExecutionResult,
    run_id: str,
    *,
    category_by_question: dict[str, str] | None = None,
    include_answer_blobs: bool = False,
) -> list[NormalizedConcept]:
    out: list[NormalizedConcept] = []
    for r in qexec.responses.responses:
        if not r.is_useful():
            continue
        cat = (category_by_question or {}).get(r.question_id)
        prov_base: dict[str, Any] = {"question_id": r.question_id, "field": "key_claims"}
        if cat:
            prov_base["question_category"] = cat
        for c in r.key_claims:
            if not c.text.strip():
                continue
            k2: ConceptKind = "questionnaire_claim"
            lt = c.text.strip()
            out.append(
                NormalizedConcept(
                    concept_key=_concept_key(k2, lt[:800]),
                    kind=k2,
                    label=_norm_label(lt[:500]),
                    source_run_id=run_id,
                    source_artifact="questionnaire",
                    provenance={**prov_base, "claim_index": len(out)},
                )
            )
        if include_answer_blobs:
            blob = (r.answer_markdown or "")[:800]
            if blob.strip():
                k: ConceptKind = "questionnaire_answer"
                lab = blob.strip().split("\n", 1)[0][:240]
                p = {"question_id": r.question_id, "field": "answer_markdown"}
                if cat:
                    p["question_category"] = cat
                out.append(
                    NormalizedConcept(
                        concept_key=_concept_key(k, lab),
                        kind=k,
                        label=_norm_label(lab),
                        source_run_id=run_id,
                        source_artifact="questionnaire",
                        provenance=p,
                    )
                )
    return out


def _pattern_id(kind: ConceptKind, label: str, run_ids: list[str]) -> str:
    return f"pat-{short_hash(kind, _norm_label(label), ','.join(run_ids))}"


def _primitive_id(pk: PrimitiveKind, label: str, pat_ids: list[str]) -> str:
    return f"prim-{short_hash(pk, _norm_label(label), ','.join(sorted(pat_ids)))}"


def _build_edges_from_dossiers(
    dossiers: dict[str, CropDossier],
) -> list[OntologyEdge]:
    edges: list[OntologyEdge] = []
    for run_id, d in dossiers.items():
        for p in d.pathogens:
            p_node = stable_node_id("pathogen", p.name)
            for st in p.affected_stages:
                s_node = stable_node_id("lifecycle_stage", st)
                eid = f"e-{short_hash('obs', p.name, st, run_id)}"
                edges.append(
                    OntologyEdge(
                        edge_id=eid,
                        relation="observed_in_stage",
                        source_node_id=p_node,
                        target_node_id=s_node,
                        provenance={"run_id": run_id, "pathogen_id": p.id},
                    )
                )
        for ie in d.intervention_effects:
            inv_name = _intervention_name(d, ie.intervention_id)
            tgt_name, tgt_k = _resolve_target_label(d, ie.target_ref)
            src = stable_node_id("intervention", inv_name)
            tgt = stable_node_id(tgt_k, tgt_name)
            eid = f"e-{short_hash('tgt', ie.intervention_id, ie.target_ref, run_id)}"
            edges.append(
                OntologyEdge(
                    edge_id=eid,
                    relation="targets",
                    source_node_id=src,
                    target_node_id=tgt,
                    provenance={"run_id": run_id, "effect": str(ie.effect)},
                )
            )
    return edges


def _composite_primitives(patterns: list[CrossCropPattern]) -> list[PlatformPrimitive]:
    """Co-occurring pathogen + lifecycle stage across runs -> monitoring composite."""
    by_kind: dict[str, list[CrossCropPattern]] = defaultdict(list)
    for p in patterns:
        by_kind[p.kind].append(p)
    pathogens = {p.normalized_label: p for p in by_kind.get("pathogen", [])}
    stages = {p.normalized_label: p for p in by_kind.get("lifecycle_stage", [])}
    out: list[PlatformPrimitive] = []
    for plab, pp in pathogens.items():
        for slab, sp in stages.items():
            shared = sorted(set(pp.run_ids) & set(sp.run_ids))
            if not shared:
                continue
            pids = sorted([pp.pattern_id, sp.pattern_id])
            lab = f"co_occur:{plab}@{slab}"
            out.append(
                PlatformPrimitive(
                    primitive_id=_primitive_id("monitoring_target", lab, pids),
                    kind="monitoring_target",
                    label=lab,
                    supporting_pattern_ids=pids,
                    run_ids=shared,
                    provenance={"composite_rule": "pathogen_lifecycle_cooccurrence"},
                )
            )
    for ilab, ip in {p.normalized_label: p for p in by_kind.get("intervention", [])}.items():
        for llab, lp in {p.normalized_label: p for p in by_kind.get("limiting_factor", [])}.items():
            shared = sorted(set(ip.run_ids) & set(lp.run_ids))
            if not shared:
                continue
            pids = sorted([ip.pattern_id, lp.pattern_id])
            lab = f"co_occur:{ilab}|{llab}"
            out.append(
                PlatformPrimitive(
                    primitive_id=_primitive_id("intervention_effect", lab, pids),
                    kind="intervention_effect",
                    label=lab,
                    supporting_pattern_ids=pids,
                    run_ids=shared,
                    provenance={"composite_rule": "intervention_limiting_cooccurrence"},
                )
            )
    return out


def _validate_output(
    out: SynthesisOutput,
    had_runs: int,
    dossier_non_empty: bool,
) -> None:
    w = list(out.validation_warnings)
    if had_runs > 0 and dossier_non_empty and not out.normalized_concepts:
        w.append("empty_normalized_concepts_despite_non_empty_dossiers")
    seen_pat: set[str] = set()
    for p in out.cross_crop_patterns:
        if p.pattern_id in seen_pat:
            w.append(f"duplicate_pattern_id:{p.pattern_id}")
        seen_pat.add(p.pattern_id)
    seen_nid: set[str] = set()
    for n in out.ontology_nodes:
        if n.node_id in seen_nid:
            w.append(f"duplicate_node_id:{n.node_id}")
        seen_nid.add(n.node_id)
    pattern_ids = {p.pattern_id for p in out.cross_crop_patterns}
    for pr in out.platform_primitives:
        for pid in pr.supporting_pattern_ids:
            if pid not in pattern_ids:
                w.append(f"primitive_references_unknown_pattern:{pr.primitive_id}:{pid}")
        if pr.supporting_pattern_ids:
            pat_runs = {rid for p in out.cross_crop_patterns if p.pattern_id in pr.supporting_pattern_ids for rid in p.run_ids}
            if pr.run_ids and not set(pr.run_ids).issubset(pat_runs):
                w.append(f"primitive_run_ids_not_covered_by_patterns:{pr.primitive_id}")
    out.validation_warnings = w


def run_synthesis(*, manifest: SynthesisManifest, base_path: Path) -> SynthesisOutput:
    all_concepts: list[NormalizedConcept] = []
    contexts: list[dict[str, Any]] = []
    warnings: list[str] = []
    dossiers: dict[str, CropDossier] = {}
    run_payloads: list[tuple[str, dict[str, Any], dict[str, Any] | None]] = []
    any_dossier_content = False

    for run in manifest.runs:
        run_id = str(run.run_id)
        if run.prioritization_context is not None:
            ctx = dict(run.prioritization_context)
            ctx["run_id"] = run_id
            contexts.append(ctx)

        dpath = resolve_safe_path(base_path, run.dossier)
        raw_d = json.loads(dpath.read_text(encoding="utf-8"))
        if raw_d:
            any_dossier_content = True
        dossier = CropDossier.model_validate(raw_d)
        dossiers[run_id] = dossier
        qdict: dict[str, Any] | None = None

        category_map: dict[str, str] | None = None
        if run.questionnaire_spec:
            spath = resolve_safe_path(base_path, run.questionnaire_spec)
            spec = QuestionnaireSpec.model_validate(json.loads(spath.read_text(encoding="utf-8")))
            category_map = {q.id: q.category for q in spec.questions}

        if run.questionnaire:
            qpath = resolve_safe_path(base_path, run.questionnaire)
            qdict = json.loads(qpath.read_text(encoding="utf-8"))
            qexec = QuestionnaireExecutionResult.model_validate(qdict)
            all_concepts.extend(
                extract_concepts_from_questionnaire(
                    qexec,
                    run_id,
                    category_by_question=category_map,
                    include_answer_blobs=manifest.include_questionnaire_answer_blobs,
                )
            )
        elif run.questionnaire is not None and run.questionnaire == "":
            warnings.append(f"run {run_id}: empty questionnaire path")

        all_concepts.extend(extract_concepts_from_dossier(dossier, run_id))
        run_payloads.append((run_id, raw_d, qdict))

    synthesis_id = synthesis_id_from_runs(run_payloads)

    by_key: dict[str, list[NormalizedConcept]] = defaultdict(list)
    for c in all_concepts:
        by_key[c.concept_key].append(c)

    patterns: list[CrossCropPattern] = []
    nodes: list[OntologyNode] = []
    primitives: list[PlatformPrimitive] = []

    for _key, items in by_key.items():
        run_ids = sorted({i.source_run_id for i in items})
        mention_count = len(items)
        if not items:
            continue
        kind = items[0].kind
        label = items[0].label
        th = manifest.threshold_for_kind(kind)
        if len(run_ids) >= th.min_crops and mention_count >= th.min_mentions:
            pid = _pattern_id(kind, label, run_ids)
            patterns.append(
                CrossCropPattern(
                    pattern_id=pid,
                    kind=kind,
                    normalized_label=label,
                    run_ids=run_ids,
                    mention_count=mention_count,
                )
            )
            nid = stable_node_id(kind, label)
            nodes.append(
                OntologyNode(
                    node_id=nid,
                    label=label,
                    kind=kind,
                    pattern_id=pid,
                )
            )
            pk = _KIND_TO_PRIMITIVE.get(kind)
            if pk:
                primitives.append(
                    PlatformPrimitive(
                        primitive_id=_primitive_id(pk, label, [pid]),
                        kind=pk,
                        label=label,
                        supporting_pattern_ids=[pid],
                        run_ids=run_ids,
                        provenance={},
                    )
                )

    primitives.extend(_composite_primitives(patterns))
    edges = _build_edges_from_dossiers(dossiers)

    out = SynthesisOutput(
        synthesis_id=synthesis_id,
        normalized_concepts=all_concepts,
        cross_crop_patterns=patterns,
        ontology_nodes=nodes,
        ontology_edges=edges,
        platform_primitives=primitives,
        prioritization_context=contexts,
        validation_warnings=warnings,
    )
    _validate_output(out, had_runs=len(manifest.runs), dossier_non_empty=any_dossier_content)
    return out


def load_manifest(path: Path) -> tuple[SynthesisManifest, Path]:
    from research_agent.synthesis.manifest import parse_manifest_file as _parse

    return _parse(path)
