from future import annotations

from contracts.agronomy.dossier import CropDossier
from contracts.core.questionnaire import QuestionAnswer, QuestionnaireResponseSet

def _claim_lines(items) -> str:
if not items:
return "-"
lines = []
for item in items:
suffix = ""
if item.evidence_ids:
suffix = f" [evidence: {', '.join(item.evidence_ids)}]"
lines.append(f"- {item.text}{suffix}")
return "
".join(lines)

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
f"- Typical preceding crops:
{_claim_lines(dossier.rotation_role.typical_preceding_crops)}",
f"- Typical succeeding crops:
{_claim_lines(dossier.rotation_role.typical_succeeding_crops)}",
f"- Known rotation effects:
{_claim_lines(dossier.rotation_role.known_rotation_effects)}",
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

return "\n".join(lines)

def render_questionnaire_response_markdown(response_set: QuestionnaireResponseSet) -> str:
lines = [
f"# Questionnaire Responses: {response_set.subject_id}",
"",
f"- Questionnaire ID: {response_set.questionnaire_id}",
"",
]
for response in response_set.responses:
lines.extend([
f"## {response.question_id}",
"",
f"- Status: {response.status}",
"",
response.answer_markdown.strip(),
"",
])
if response.key_claims:
lines.append("### Key Claims")
lines.append("")
for claim in response.key_claims:
ev = ", ".join(claim.evidence_ids) if claim.evidence_ids else "-"
lines.append(f"- {claim.text} (support={claim.support}, evidence={ev})")
lines.append("")
return "
".join(lines)
