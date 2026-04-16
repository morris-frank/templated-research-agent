from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Any

from pydantic import BaseModel, Field, ValidationError


# -----------------------------------------------------------------------------
# Types
# -----------------------------------------------------------------------------

ClaimKind = Literal[
    "observation",
    "comparison",
    "inference",
    "recommendation",
    "open_question",
]

ClaimStatus = Literal[
    "supported",
    "weakly_supported",
    "unsupported",
    "contested",
]

Confidence = Literal["low", "medium", "high"]

EvidenceSourceKind = Literal[
    "paper",
    "web",
    "measurement",
    "derived_metric",
    "benchmark",
    "customer_input",
    "report_artifact",
    "discovery_note",
]

LinkRelation = Literal[
    "direct_support",
    "indirect_support",
    "context_only",
    "contradicts",
    "motivates_recommendation",
]

ExecutionKind = Literal[
    "retrieval",
    "lab",
    "analysis",
    "model_inference",
    "report",
]

DependencyRelation = Literal[
    "depends_on",
    "derived_from",
    "generalizes",
    "narrows",
    "motivates",
    "contradicts",
]


# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------


class ExecutionContext(BaseModel):
    execution_id: str
    pipeline_kind: ExecutionKind
    pipeline_version: str
    run_at: datetime
    parameters: dict[str, Any] = Field(default_factory=dict)


class EvidenceRecord(BaseModel):
    evidence_id: str
    source_kind: EvidenceSourceKind

    title: str | None = None
    locator: str
    excerpt: str | None = None

    structured_value: dict[str, Any] | None = None
    units: str | None = None

    provenance: dict[str, Any] = Field(default_factory=dict)
    execution_context_id: str | None = None

    authority_score: float | None = None
    retrieved_at: datetime | None = None


class Claim(BaseModel):
    claim_id: str
    text: str
    claim_kind: ClaimKind

    scope: dict[str, Any] = Field(default_factory=dict)
    confidence: Confidence
    status: ClaimStatus


class ClaimEvidenceLink(BaseModel):
    link_id: str
    claim_id: str
    evidence_id: str

    relation: LinkRelation
    rationale: str
    strength: float


class ClaimDependencyLink(BaseModel):
    link_id: str
    from_claim_id: str
    to_claim_id: str

    relation: DependencyRelation
    rationale: str


class InsightItem(BaseModel):
    insight_id: str
    text: str
    claim_refs: list[str]


class RecommendationItem(BaseModel):
    recommendation_id: str
    action: str
    rationale_claim_refs: list[str]
    dependency_claim_refs: list[str] = Field(default_factory=list)


class FinalProjection(BaseModel):
    summary_claim_refs: list[str]
    strengths: list[InsightItem] = Field(default_factory=list)
    weaknesses: list[InsightItem] = Field(default_factory=list)
    implications: list[InsightItem] = Field(default_factory=list)
    recommendations: list[RecommendationItem] = Field(default_factory=list)
    open_question_claim_refs: list[str] = Field(default_factory=list)


class ClaimGraphBundle(BaseModel):
    execution_contexts: list[ExecutionContext]
    evidence_records: list[EvidenceRecord]
    claims: list[Claim]
    claim_evidence_links: list[ClaimEvidenceLink]
    claim_dependency_links: list[ClaimDependencyLink]
    output: FinalProjection


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def index_by_id(items: list[BaseModel], attr: str) -> dict[str, BaseModel]:
    out: dict[str, BaseModel] = {}
    for item in items:
        key = getattr(item, attr)
        if key in out:
            raise ValueError(f"Duplicate {attr}: {key}")
        out[key] = item
    return out


def stable_slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "item"


def parse_iso_dt(value: str) -> datetime:
    # Accepts trailing Z.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------


class ValidationIssue(BaseModel):
    level: Literal["error", "warning"]
    code: str
    message: str


class ValidationReport(BaseModel):
    ok: bool
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]


def _contains_numeric_assertion(text: str) -> bool:
    return bool(re.search(r"\b\d+(?:\.\d+)?\b|%|percentile|ratio\b", text.lower()))


def validate_claim_graph(bundle: ClaimGraphBundle) -> ValidationReport:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    claims = index_by_id(bundle.claims, "claim_id")
    evidence = index_by_id(bundle.evidence_records, "evidence_id")
    execs = index_by_id(bundle.execution_contexts, "execution_id")

    # Referential integrity.
    for link in bundle.claim_evidence_links:
        if link.claim_id not in claims:
            errors.append(ValidationIssue(
                level="error",
                code="missing_claim_for_evidence_link",
                message=f"Evidence link {link.link_id} references missing claim {link.claim_id}",
            ))
        if link.evidence_id not in evidence:
            errors.append(ValidationIssue(
                level="error",
                code="missing_evidence_for_evidence_link",
                message=f"Evidence link {link.link_id} references missing evidence {link.evidence_id}",
            ))
        if not (0.0 <= link.strength <= 1.0):
            errors.append(ValidationIssue(
                level="error",
                code="invalid_link_strength",
                message=f"Evidence link {link.link_id} has strength outside [0,1]",
            ))

    for link in bundle.claim_dependency_links:
        if link.from_claim_id not in claims:
            errors.append(ValidationIssue(
                level="error",
                code="missing_from_claim_for_dependency_link",
                message=f"Dependency link {link.link_id} references missing from-claim {link.from_claim_id}",
            ))
        if link.to_claim_id not in claims:
            errors.append(ValidationIssue(
                level="error",
                code="missing_to_claim_for_dependency_link",
                message=f"Dependency link {link.link_id} references missing to-claim {link.to_claim_id}",
            ))

    # Output references.
    output_claim_refs: list[str] = []
    output_claim_refs.extend(bundle.output.summary_claim_refs)
    output_claim_refs.extend(bundle.output.open_question_claim_refs)

    for section in (bundle.output.strengths, bundle.output.weaknesses, bundle.output.implications):
        for item in section:
            output_claim_refs.extend(item.claim_refs)

    for rec in bundle.output.recommendations:
        output_claim_refs.extend(rec.rationale_claim_refs)
        output_claim_refs.extend(rec.dependency_claim_refs)

    for claim_id in output_claim_refs:
        if claim_id not in claims:
            errors.append(ValidationIssue(
                level="error",
                code="missing_output_claim_ref",
                message=f"Output references missing claim {claim_id}",
            ))

    evidence_links_by_claim: dict[str, list[ClaimEvidenceLink]] = {}
    dep_links_by_claim: dict[str, list[ClaimDependencyLink]] = {}
    for link in bundle.claim_evidence_links:
        evidence_links_by_claim.setdefault(link.claim_id, []).append(link)
    for link in bundle.claim_dependency_links:
        dep_links_by_claim.setdefault(link.from_claim_id, []).append(link)

    for claim in bundle.claims:
        e_links = evidence_links_by_claim.get(claim.claim_id, [])
        d_links = dep_links_by_claim.get(claim.claim_id, [])

        if claim.status == "supported":
            strong_direct = [
                link for link in e_links
                if link.relation == "direct_support" and link.strength >= 0.7
            ]
            if not strong_direct and not d_links:
                errors.append(ValidationIssue(
                    level="error",
                    code="supported_claim_without_support_path",
                    message=f"Supported claim {claim.claim_id} has no direct support or dependency path",
                ))

        if claim.claim_kind == "recommendation":
            motivating_links = [link for link in d_links if link.relation == "motivates"]
            if not motivating_links:
                errors.append(ValidationIssue(
                    level="error",
                    code="recommendation_without_motivation",
                    message=f"Recommendation claim {claim.claim_id} has no motivating dependency",
                ))

        if _contains_numeric_assertion(claim.text):
            has_structured = any(evidence[link.evidence_id].structured_value is not None for link in e_links if link.evidence_id in evidence)
            if not has_structured:
                warnings.append(ValidationIssue(
                    level="warning",
                    code="numeric_claim_without_structured_evidence",
                    message=f"Claim {claim.claim_id} looks quantitative but has no structured evidence",
                ))

    for ev in bundle.evidence_records:
        if ev.source_kind in {"measurement", "derived_metric", "benchmark"}:
            if not ev.provenance:
                errors.append(ValidationIssue(
                    level="error",
                    code="evidence_missing_provenance",
                    message=f"Evidence {ev.evidence_id} is missing provenance",
                ))
            if not ev.execution_context_id:
                errors.append(ValidationIssue(
                    level="error",
                    code="evidence_missing_execution_context",
                    message=f"Evidence {ev.evidence_id} is missing execution context",
                ))
            elif ev.execution_context_id not in execs:
                errors.append(ValidationIssue(
                    level="error",
                    code="evidence_references_missing_execution_context",
                    message=f"Evidence {ev.evidence_id} references missing execution context {ev.execution_context_id}",
                ))

    return ValidationReport(ok=not errors, errors=errors, warnings=warnings)


# -----------------------------------------------------------------------------
# Rendering
# -----------------------------------------------------------------------------


def render_markdown(bundle: ClaimGraphBundle) -> str:
    claims = index_by_id(bundle.claims, "claim_id")

    def claim_texts(ids: list[str]) -> list[str]:
        return [claims[cid].text for cid in ids if cid in claims]

    lines: list[str] = []
    lines.append("# Claim-Linked Report")
    lines.append("")

    summary = claim_texts(bundle.output.summary_claim_refs)
    if summary:
        lines.append("## Summary")
        for text in summary:
            lines.append(f"- {text}")
        lines.append("")

    sections = [
        ("Strengths", bundle.output.strengths),
        ("Weaknesses", bundle.output.weaknesses),
        ("Implications", bundle.output.implications),
    ]
    for title, items in sections:
        if not items:
            continue
        lines.append(f"## {title}")
        for item in items:
            refs = ", ".join(item.claim_refs)
            lines.append(f"- {item.text}  ")
            lines.append(f"  claim_refs: {refs}")
        lines.append("")

    if bundle.output.recommendations:
        lines.append("## Recommendations")
        for item in bundle.output.recommendations:
            rationale = ", ".join(item.rationale_claim_refs)
            deps = ", ".join(item.dependency_claim_refs)
            lines.append(f"- {item.action}  ")
            lines.append(f"  rationale_claim_refs: {rationale}")
            if deps:
                lines.append(f"  dependency_claim_refs: {deps}")
        lines.append("")

    if bundle.output.open_question_claim_refs:
        lines.append("## Open Questions")
        for text in claim_texts(bundle.output.open_question_claim_refs):
            lines.append(f"- {text}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# -----------------------------------------------------------------------------
# Demo bundle
# -----------------------------------------------------------------------------


def build_agrinova_demo_bundle() -> ClaimGraphBundle:
    return ClaimGraphBundle(
        execution_contexts=[
            ExecutionContext(
                execution_id="exec-analysis-agrinova-2026-04-02",
                pipeline_kind="analysis",
                pipeline_version="soil-insight-v1.4",
                run_at=parse_iso_dt("2026-04-02T10:00:00Z"),
                parameters={
                    "customer": "Agrinova",
                    "engagement_type": "pilot",
                    "samples": 4,
                    "fields": 2,
                },
            ),
            ExecutionContext(
                execution_id="exec-report-agrinova-2026-04-02",
                pipeline_kind="report",
                pipeline_version="report-composer-v0.9",
                run_at=parse_iso_dt("2026-04-02T14:00:00Z"),
                parameters={},
            ),
        ],
        evidence_records=[
            EvidenceRecord(
                evidence_id="E1",
                source_kind="derived_metric",
                title="F:B ratio",
                locator="sample_set:agrinova/F:B_ratio",
                structured_value={"metric": "F:B_ratio", "value": 0.09},
                provenance={"sample_set_id": "agrinova-pilot-1"},
                execution_context_id="exec-analysis-agrinova-2026-04-02",
            ),
            EvidenceRecord(
                evidence_id="E2",
                source_kind="derived_metric",
                title="Nitrogen fixation proxy",
                locator="sample_set:agrinova/nitrogen_fixation",
                structured_value={"metric": "nitrogen_fixation", "value": 0.01},
                provenance={"sample_set_id": "agrinova-pilot-1"},
                execution_context_id="exec-analysis-agrinova-2026-04-02",
            ),
            EvidenceRecord(
                evidence_id="E3",
                source_kind="derived_metric",
                title="AMF abundance",
                locator="sample_set:agrinova/AMF",
                structured_value={"metric": "AMF", "value": "near_absent"},
                provenance={"sample_set_id": "agrinova-pilot-1"},
                execution_context_id="exec-analysis-agrinova-2026-04-02",
            ),
            EvidenceRecord(
                evidence_id="E4",
                source_kind="benchmark",
                title="SOC percentile",
                locator="benchmark:agrinova/SOC_percentile",
                structured_value={"metric": "SOC", "percentile": 95},
                provenance={"benchmark_set": "soil-health-reference-v2"},
                execution_context_id="exec-analysis-agrinova-2026-04-02",
            ),
            EvidenceRecord(
                evidence_id="E5",
                source_kind="customer_input",
                title="Discovery pain point",
                locator="discovery:agrinova:2026-03-17",
                excerpt="Need proof of efficacy of Rhizobium products and integration with remote sensing data.",
                provenance={"artifact": "discovery_call_notes"},
            ),
            EvidenceRecord(
                evidence_id="E6",
                source_kind="report_artifact",
                title="Recommendations document",
                locator="report:agrinova:recommendations:2026-04-02",
                excerpt="Increase fungal biomass, restore AMF, add legumes, improve residue decomposition.",
                provenance={"artifact": "recommendations_doc"},
                execution_context_id="exec-report-agrinova-2026-04-02",
            ),
        ],
        claims=[
            Claim(
                claim_id="C1",
                text="The sampled soils are chemically strong.",
                claim_kind="observation",
                scope={"customer": "Agrinova", "sample_set_id": "agrinova-pilot-1"},
                confidence="high",
                status="supported",
            ),
            Claim(
                claim_id="C2",
                text="The sampled soils are biologically underperforming.",
                claim_kind="observation",
                scope={"customer": "Agrinova", "sample_set_id": "agrinova-pilot-1"},
                confidence="high",
                status="supported",
            ),
            Claim(
                claim_id="C3",
                text="The main limiting signal in this pilot appears biological rather than chemical.",
                claim_kind="inference",
                scope={"customer": "Agrinova", "sample_set_id": "agrinova-pilot-1"},
                confidence="medium",
                status="supported",
            ),
            Claim(
                claim_id="C4",
                text="Agrinova's highest-value job is product validation for biological inputs rather than generic soil-health reporting alone.",
                claim_kind="inference",
                scope={"customer": "Agrinova"},
                confidence="medium",
                status="supported",
            ),
            Claim(
                claim_id="C5",
                text="A higher-value follow-on engagement would test inoculant establishment and product efficacy explicitly.",
                claim_kind="recommendation",
                scope={"customer": "Agrinova"},
                confidence="medium",
                status="supported",
            ),
            Claim(
                claim_id="C6",
                text="Restoring fungal biomass and AMF is a plausible agronomic intervention direction.",
                claim_kind="recommendation",
                scope={"customer": "Agrinova"},
                confidence="medium",
                status="supported",
            ),
        ],
        claim_evidence_links=[
            ClaimEvidenceLink(
                link_id="L1",
                claim_id="C1",
                evidence_id="E4",
                relation="direct_support",
                rationale="SOC percentile directly supports strong chemical/structural condition.",
                strength=0.92,
            ),
            ClaimEvidenceLink(
                link_id="L2",
                claim_id="C2",
                evidence_id="E1",
                relation="direct_support",
                rationale="Very low F:B ratio directly supports weak fungal balance.",
                strength=0.95,
            ),
            ClaimEvidenceLink(
                link_id="L3",
                claim_id="C2",
                evidence_id="E2",
                relation="direct_support",
                rationale="Near-zero nitrogen fixation proxy directly supports biological underperformance.",
                strength=0.90,
            ),
            ClaimEvidenceLink(
                link_id="L4",
                claim_id="C2",
                evidence_id="E3",
                relation="direct_support",
                rationale="Near-absent AMF directly supports impaired biological functioning.",
                strength=0.93,
            ),
            ClaimEvidenceLink(
                link_id="L5",
                claim_id="C4",
                evidence_id="E5",
                relation="direct_support",
                rationale="Discovery notes explicitly state product efficacy validation as a customer pain point.",
                strength=0.91,
            ),
            ClaimEvidenceLink(
                link_id="L6",
                claim_id="C6",
                evidence_id="E6",
                relation="direct_support",
                rationale="Recommendation artifact explicitly proposes restoring fungal biomass and AMF.",
                strength=0.85,
            ),
        ],
        claim_dependency_links=[
            ClaimDependencyLink(
                link_id="D1",
                from_claim_id="C3",
                to_claim_id="C1",
                relation="depends_on",
                rationale="Inference requires chemical strength context.",
            ),
            ClaimDependencyLink(
                link_id="D2",
                from_claim_id="C3",
                to_claim_id="C2",
                relation="depends_on",
                rationale="Inference requires biological weakness observations.",
            ),
            ClaimDependencyLink(
                link_id="D3",
                from_claim_id="C5",
                to_claim_id="C3",
                relation="motivates",
                rationale="Follow-on product-validation engagement follows from identified biological limitation.",
            ),
            ClaimDependencyLink(
                link_id="D4",
                from_claim_id="C5",
                to_claim_id="C4",
                relation="motivates",
                rationale="Follow-on scope should align with customer job-to-be-done.",
            ),
            ClaimDependencyLink(
                link_id="D5",
                from_claim_id="C6",
                to_claim_id="C2",
                relation="motivates",
                rationale="Intervention direction follows from biological underperformance.",
            ),
        ],
        output=FinalProjection(
            summary_claim_refs=["C3", "C4"],
            strengths=[
                InsightItem(
                    insight_id="S1",
                    text="Chemically and structurally, the soils look strong.",
                    claim_refs=["C1"],
                )
            ],
            weaknesses=[
                InsightItem(
                    insight_id="W1",
                    text="Biological performance is weak, including fungal balance, AMF presence, and nitrogen fixation proxies.",
                    claim_refs=["C2"],
                )
            ],
            implications=[
                InsightItem(
                    insight_id="I1",
                    text="The key limiting signal in this pilot is biological rather than chemical.",
                    claim_refs=["C3"],
                ),
                InsightItem(
                    insight_id="I2",
                    text="The commercial wedge is product validation, not generic dashboarding alone.",
                    claim_refs=["C4"],
                ),
            ],
            recommendations=[
                RecommendationItem(
                    recommendation_id="R1",
                    action="Design a follow-on engagement focused on inoculant establishment and efficacy validation.",
                    rationale_claim_refs=["C5"],
                    dependency_claim_refs=["C3", "C4"],
                ),
                RecommendationItem(
                    recommendation_id="R2",
                    action="Prioritize interventions that restore fungal biomass and AMF.",
                    rationale_claim_refs=["C6"],
                    dependency_claim_refs=["C2"],
                ),
            ],
            open_question_claim_refs=[],
        ),
    )


# -----------------------------------------------------------------------------
# Optional drafting hook
# -----------------------------------------------------------------------------


class DraftInput(BaseModel):
    context_name: str
    evidence_records: list[EvidenceRecord]


class DraftResult(BaseModel):
    claims: list[Claim]
    claim_evidence_links: list[ClaimEvidenceLink]
    claim_dependency_links: list[ClaimDependencyLink]
    output: FinalProjection


DRAFTING_PROMPT = """You are generating a claim graph.
Return valid JSON only.
Rules:
- Emit claims first.
- Use evidence-backed observation/inference claims.
- Recommendations must be motivated by other claims.
- Output sections must reference claim IDs, never evidence IDs.
- Do not invent evidence beyond what is provided.
"""


def draft_from_provider(_: DraftInput) -> DraftResult:
    raise NotImplementedError(
        "Provider hook not configured. Replace draft_from_provider() with your model client, "
        "or use --demo / --input-json modes."
    )


# -----------------------------------------------------------------------------
# File IO
# -----------------------------------------------------------------------------


def write_json(path: Path, obj: BaseModel | dict[str, Any]) -> None:
    if isinstance(obj, BaseModel):
        data = obj.model_dump(mode="json")
    else:
        data = obj
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_bundle(path: Path) -> ClaimGraphBundle:
    return ClaimGraphBundle.model_validate_json(path.read_text(encoding="utf-8"))


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Single-file claim-to-evidence prototype with demo, validation, and rendering.",
    )
    parser.add_argument("--demo", action="store_true", help="Use the built-in Agrinova demo bundle.")
    parser.add_argument("--input-json", type=Path, help="Path to an input ClaimGraphBundle JSON file.")
    parser.add_argument("--validate-only", action="store_true", help="Validate the bundle and exit.")
    parser.add_argument("--render-markdown", type=Path, help="Render report markdown to this path.")
    parser.add_argument("--write-json", type=Path, help="Write the resolved bundle JSON to this path.")
    parser.add_argument("--print-summary", action="store_true", help="Print a concise summary to stdout.")
    return parser


def load_bundle_from_args(args: argparse.Namespace) -> ClaimGraphBundle:
    if args.demo:
        return build_agrinova_demo_bundle()
    if args.input_json:
        return read_bundle(args.input_json)
    raise SystemExit("Provide either --demo or --input-json PATH")


def print_summary(bundle: ClaimGraphBundle, report: ValidationReport) -> None:
    print(
        json.dumps(
            {
                "claims": len(bundle.claims),
                "evidence_records": len(bundle.evidence_records),
                "claim_evidence_links": len(bundle.claim_evidence_links),
                "claim_dependency_links": len(bundle.claim_dependency_links),
                "ok": report.ok,
                "error_count": len(report.errors),
                "warning_count": len(report.warnings),
            },
            indent=2,
        )
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        bundle = load_bundle_from_args(args)
    except ValidationError as exc:
        print(exc, file=sys.stderr)
        return 2

    report = validate_claim_graph(bundle)

    if args.write_json:
        write_json(args.write_json, bundle)

    if args.render_markdown:
        args.render_markdown.write_text(render_markdown(bundle), encoding="utf-8")

    if args.print_summary:
        print_summary(bundle, report)

    if report.errors or report.warnings:
        payload = report.model_dump(mode="json")
        print(json.dumps(payload, indent=2, ensure_ascii=False))

    if args.validate_only:
        return 0 if report.ok else 1

    if not args.print_summary and not args.render_markdown and not args.write_json:
        # Default stdout behavior: print rendered markdown when not otherwise specified.
        print(render_markdown(bundle))

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
