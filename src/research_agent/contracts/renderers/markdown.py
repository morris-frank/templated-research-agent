from __future__ import annotations

from typing import Literal

from research_agent.contracts.agronomy.dossier import (
    CropDossier,
    Intervention,
)
from research_agent.contracts.core.claim_graph import ClaimGraphBundle, FinalProjection
from research_agent.contracts.core.questionnaire import QuestionnaireResponseSet


def _claim_lines(items: list) -> str:
    if not items:
        return "-"
    lines = []
    for item in items:
        suffix = ""
        if item.evidence_ids:
            suffix = f" [evidence: {', '.join(item.evidence_ids)}]"
        lines.append(f"- {item.text}{suffix}")
    return "\n".join(lines)


def _claim_inline(claim) -> str:
    ev = f" [evidence: {', '.join(claim.evidence_ids)}]" if claim.evidence_ids else ""
    return f"{claim.text}{ev}"


def _evidence_suffix(evidence_ids: list[str]) -> str:
    return f" [evidence: {', '.join(evidence_ids)}]" if evidence_ids else ""


def _resolve_target(dossier: CropDossier, target_ref: str) -> str:
    for d in dossier.yield_drivers:
        if d.id == target_ref:
            return f"yield driver: {d.name}"
    for p in dossier.pathogens:
        if p.id == target_ref:
            return f"pathogen: {p.name}"
    for s in dossier.soil_dependencies:
        if s.id == target_ref:
            return f"soil: {s.variable}"
    for m in dossier.microbiome_roles:
        if m.id == target_ref:
            return f"microbiome: {m.function}"
    for lf in dossier.limiting_factors:
        if lf.id == target_ref:
            return f"limiting factor: {lf.factor}"
    return target_ref


def render_crop_dossier_markdown(dossier: CropDossier) -> str:
    lines = [
        "# External Crop Dossier Template",
        "",
        "### Metadata",
        "",
        f"- Crop Name: {dossier.crop_name}",
        f"- Crop Category: {dossier.crop_category}",
        f"- Primary Use Cases: {', '.join(dossier.primary_use_cases)}",
        f"- Priority Tier: {dossier.priority_tier}",
        f"- Last Updated: {dossier.last_updated.isoformat()}",
        "",
        "### Production System Context",
        "",
        "#### Geographies",
        "",
        f"- Core regions: {', '.join(dossier.production_system_context.core_regions) or '-'}",
        f"- Climate zones: {', '.join(dossier.production_system_context.climate_zones) or '-'}",
        "",
        "#### Production Modes",
        "",
        f"- Open field / greenhouse / trial station: {', '.join(dossier.production_system_context.environments) or '-'}",
        f"- Conventional / organic / biological-heavy: {', '.join(dossier.production_system_context.management_modes) or '-'}",
        "",
        "#### Rotation Role",
        "",
        f"- Typical preceding crops:\n{_claim_lines(dossier.rotation_role.typical_preceding_crops)}",
        f"- Typical succeeding crops:\n{_claim_lines(dossier.rotation_role.typical_succeeding_crops)}",
        f"- Known rotation effects:\n{_claim_lines(dossier.rotation_role.known_rotation_effects)}",
        "",
        "### Lifecycle Ontology (CRITICAL)",
        "",
        "Define discrete, platform-relevant stages.",
        "",
        "| Stage | Description | Key Decisions | Observables | Failure Modes |",
        "| --- | --- | --- | --- | --- |",
    ]

    for stage in dossier.lifecycle_ontology:
        key_decisions = "; ".join(item.text for item in stage.key_decisions) or "-"
        observables = "; ".join(item.text for item in stage.observables) or "-"
        failure_modes = "; ".join(item.text for item in stage.failure_modes) or "-"
        description = stage.description or "-"
        lines.append(
            f"| {stage.stage} | {description} | {key_decisions} | {observables} | {failure_modes} |"
        )

    if dossier.yield_drivers:
        lines.extend(["", "### Yield Drivers", "",
                      "| Name | Mechanism | Proxies | Evidence |",
                      "| --- | --- | --- | --- |"])
        for d in dossier.yield_drivers:
            proxies = "; ".join(d.measurable_proxies) or "-"
            ev = ", ".join(sorted(set(d.evidence_ids) | set(d.mechanism.evidence_ids))) or "-"
            lines.append(f"| {d.name} | {d.mechanism.text} | {proxies} | {ev} |")

    if dossier.limiting_factors:
        lines.extend(["", "### Limiting Factors", "",
                      "| Factor | Stage | Symptoms | Evidence |",
                      "| --- | --- | --- | --- |"])
        for lf in dossier.limiting_factors:
            stage = lf.stage or "-"
            symptoms = "; ".join(s.text for s in lf.symptoms) or "-"
            ev = ", ".join(lf.evidence_ids) or "-"
            lines.append(f"| {lf.factor} | {stage} | {symptoms} | {ev} |")

    if dossier.agronomist_heuristics:
        lines.extend(["", "### Agronomist Heuristics", ""])
        for h in dossier.agronomist_heuristics:
            lines.append(
                f"- If `{h.condition}` then **{h.action}** "
                f"(rationale: {_claim_inline(h.rationale)})"
                f"{_evidence_suffix(h.evidence_ids)}"
            )

    if dossier.interventions:
        lines.extend(["", "### Interventions", "",
                      "| Kind | Name | Evidence |",
                      "| --- | --- | --- |"])
        for iv in dossier.interventions:
            ev = ", ".join(iv.evidence_ids) or "-"
            lines.append(f"| {iv.kind} | {iv.name} | {ev} |")

    if dossier.intervention_effects:
        by_id: dict[str, Intervention] = {iv.id: iv for iv in dossier.interventions}
        lines.extend(["", "### Intervention Effects", ""])
        for eff in dossier.intervention_effects:
            iv = by_id.get(eff.intervention_id)
            iv_label = iv.name if iv else eff.intervention_id
            target_label = _resolve_target(dossier, eff.target_ref)
            rationale = (
                f" — rationale: {_claim_inline(eff.rationale)}"
                if eff.rationale is not None
                else ""
            )
            lines.append(
                f"- **{iv_label}** {eff.effect} {target_label}"
                f"{rationale}{_evidence_suffix(eff.evidence_ids)}"
            )

    if dossier.pathogens or dossier.beneficials:
        lines.extend(["", "### Biotic Risks", ""])
        if dossier.pathogens:
            lines.append("**Pathogens**")
            lines.append("")
            for p in dossier.pathogens:
                conditions = "; ".join(p.pressure_conditions) or "-"
                stages = ", ".join(p.affected_stages) or "-"
                lines.append(
                    f"- {p.name} — pressure: {conditions}; stages: {stages}"
                    f"{_evidence_suffix(p.evidence_ids)}"
                )
            lines.append("")
        if dossier.beneficials:
            lines.append("**Beneficials**")
            lines.append("")
            for b in dossier.beneficials:
                lines.append(
                    f"- {b.name} — {b.function}{_evidence_suffix(b.evidence_ids)}"
                )

    if dossier.soil_dependencies or dossier.microbiome_roles:
        lines.extend(["", "### Soil & Microbiome", ""])
        if dossier.soil_dependencies:
            lines.append("**Soil dependencies**")
            lines.append("")
            for s in dossier.soil_dependencies:
                lines.append(
                    f"- {s.variable} — {_claim_inline(s.role)}"
                    f"{_evidence_suffix(s.evidence_ids)}"
                )
            lines.append("")
        if dossier.microbiome_roles:
            lines.append("**Microbiome functions**")
            lines.append("")
            for m in dossier.microbiome_roles:
                lines.append(
                    f"- {m.function} — {_claim_inline(m.importance)}"
                    f"{_evidence_suffix(m.evidence_ids)}"
                )

    if dossier.cover_crop_effects:
        lines.extend(["", "### Cover Crop Effects", ""])
        for cc in dossier.cover_crop_effects:
            target_label = _resolve_target(dossier, cc.target_ref)
            lines.append(
                f"- {cc.cover_crop} → {target_label}: {_claim_inline(cc.effect)}"
                f"{_evidence_suffix(cc.evidence_ids)}"
            )

    if dossier.open_questions:
        lines.extend(["", "### Open Questions", ""])
        for q in dossier.open_questions:
            lines.append(f"- {q}")

    if dossier.confidence:
        lines.extend(["", "### Confidence", "", f"- {dossier.confidence:.2f}"])

    return "\n".join(lines)


def render_questionnaire_response_markdown(response_set: QuestionnaireResponseSet) -> str:
    lines = [
        f"# Questionnaire Responses: {response_set.subject_id}",
        "",
        f"- Questionnaire ID: {response_set.questionnaire_id}",
        "",
    ]
    for response in response_set.responses:
        lines.extend(
            [
                f"## {response.question_id}",
                "",
                f"- Status: {response.status}",
                "",
                response.answer_markdown.strip(),
                "",
            ]
        )
        if response.key_claims:
            lines.append("### Key Claims")
            lines.append("")
            for claim in response.key_claims:
                ev = ", ".join(claim.evidence_ids) if claim.evidence_ids else "-"
                lines.append(f"- {claim.text} (support={claim.support}, evidence={ev})")
            lines.append("")
    return "\n".join(lines)


def render_final_projection_markdown(
    projection: FinalProjection,
    bundle: ClaimGraphBundle | None = None,
    *,
    style: Literal["customer", "debug"] = "customer",
) -> str:
    """
    Prose from a validated FinalProjection. Optional bundle resolves claim text and refs.

    - customer: concise sections with optional kind footnotes.
    - debug: explicit claim_ref lines (legacy claim_graph_prototype layout).
    """
    claims_by_id = {c.claim_id: c for c in (bundle.claims if bundle else [])}

    def ref_note(claim_ids: list[str]) -> str:
        if not bundle or not claim_ids:
            return ""
        parts = []
        for cid in claim_ids:
            c = claims_by_id.get(cid)
            if c:
                parts.append(f"[{cid}: {c.claim_kind}]")
            else:
                parts.append(f"[{cid}]")
        return " " + " ".join(parts) if parts else ""

    lines: list[str] = []
    if style == "debug":
        lines.extend(["# Claim-Linked Report", ""])

    def claim_texts(ids: list[str]) -> list[str]:
        return [claims_by_id[cid].text for cid in ids if cid in claims_by_id]

    if style == "debug":
        summary = claim_texts(projection.summary_claim_refs)
        if summary:
            lines.extend(["## Summary", ""])
            for text in summary:
                lines.append(f"- {text}")
            lines.append("")
        for title, items in (
            ("Strengths", projection.strengths),
            ("Weaknesses", projection.weaknesses),
            ("Implications", projection.implications),
        ):
            if not items:
                continue
            lines.extend([f"## {title}", ""])
            for item in items:
                refs = ", ".join(item.claim_refs)
                lines.append(f"- {item.text}  ")
                lines.append(f"  claim_refs: {refs}")
            lines.append("")
        if projection.recommendations:
            lines.extend(["## Recommendations", ""])
            for item in projection.recommendations:
                rationale = ", ".join(item.rationale_claim_refs)
                deps = ", ".join(item.dependency_claim_refs)
                lines.append(f"- {item.action}  ")
                lines.append(f"  rationale_claim_refs: {rationale}")
                if deps:
                    lines.append(f"  dependency_claim_refs: {deps}")
            lines.append("")
        if projection.open_question_claim_refs:
            lines.extend(["## Open Questions", ""])
            for text in claim_texts(projection.open_question_claim_refs):
                lines.append(f"- {text}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    lines.extend(
        [
            "## Summary",
            "",
        ]
    )
    for cid in projection.summary_claim_refs:
        c = claims_by_id.get(cid)
        lines.append(f"- {c.text if c else cid}")
    lines.extend(["", "## Strengths", ""])
    for s in projection.strengths:
        lines.append(f"- {s.text}{ref_note(s.claim_refs)}")
    lines.extend(["", "## Weaknesses", ""])
    for w in projection.weaknesses:
        lines.append(f"- {w.text}{ref_note(w.claim_refs)}")
    lines.extend(["", "## Implications", ""])
    for i in projection.implications:
        lines.append(f"- {i.text}{ref_note(i.claim_refs)}")
    lines.extend(["", "## Recommendations", ""])
    for r in projection.recommendations:
        dep = ref_note(r.dependency_claim_refs)
        rat = ref_note(r.rationale_claim_refs)
        lines.append(f"- **{r.action}**{rat}{dep}")
    if projection.open_question_claim_refs:
        lines.extend(["", "## Open questions", ""])
        for cid in projection.open_question_claim_refs:
            c = claims_by_id.get(cid)
            lines.append(f"- {c.text if c else cid}")
    return "\n".join(lines)
