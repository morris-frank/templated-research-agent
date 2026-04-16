from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from research_agent.contracts.agronomy.dossier import (
    CropDossier,
    LifecycleStage,
    ProductionSystemContext,
    RotationRole,
)
from research_agent.contracts.core.artifact_meta import ArtifactMeta
from research_agent.contracts.core.claims import Claim
from research_agent.contracts.core.questionnaire import (
    QuestionAnswer,
    QuestionnaireResponseSet,
    QuestionnaireSpec,
)
from research_agent.contracts.renderers.markdown import (
    render_crop_dossier_markdown,
    render_questionnaire_response_markdown,
)


def demo_dossier() -> CropDossier:
    return CropDossier(
        meta=ArtifactMeta(
            artifact_id="dossier-wheat",
            artifact_type="crop_dossier",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            tags=["agronomy", "demo"],
        ),
        crop_name="Wheat",
        crop_category="cereal",
        primary_use_cases=["pathogen panel", "inoculant validation"],
        priority_tier="T1",
        last_updated=date.today(),
        production_system_context=ProductionSystemContext(
            core_regions=["EU", "North America"],
            climate_zones=["temperate"],
            environments=["open field", "trial station"],
            management_modes=["conventional", "organic"],
        ),
        rotation_role=RotationRole(
            typical_preceding_crops=[
                Claim(text="Oilseed rape often precedes wheat in temperate rotations", evidence_ids=["E001"])
            ],
            typical_succeeding_crops=[
                Claim(
                    text="Wheat is often followed by barley or break crops depending on region",
                    evidence_ids=["E002"],
                )
            ],
            known_rotation_effects=[
                Claim(text="Rotation affects disease pressure and nutrient carryover", evidence_ids=["E003"])
            ],
        ),
        lifecycle_ontology=[
            LifecycleStage(
                stage="Pre-plant",
                description="Field and seed preparation before sowing.",
                key_decisions=[Claim(text="Seed treatment selection", evidence_ids=["E010"])],
                observables=[Claim(text="Soil condition and residue load", evidence_ids=["E011"])],
                failure_modes=[Claim(text="Poor seedbed conditions", evidence_ids=["E012"])],
            ),
            LifecycleStage(
                stage="Establishment",
                description="Emergence and stand establishment.",
                key_decisions=[Claim(text="Replant threshold decisions", evidence_ids=["E013"])],
                observables=[Claim(text="Stand count and emergence uniformity", evidence_ids=["E014"])],
                failure_modes=[Claim(text="Uneven emergence", evidence_ids=["E015"])],
            ),
            LifecycleStage(
                stage="Vegetative",
                description="Canopy development and biomass accumulation.",
                key_decisions=[Claim(text="Nitrogen timing", evidence_ids=["E016"])],
                observables=[Claim(text="Canopy vigor and disease incidence", evidence_ids=["E017"])],
                failure_modes=[Claim(text="Early disease establishment", evidence_ids=["E018"])],
            ),
            LifecycleStage(
                stage="Reproductive",
                description="Heading, flowering, grain set.",
                key_decisions=[Claim(text="Fungicide timing near flowering", evidence_ids=["E019"])],
                observables=[Claim(text="Spike health and flowering progression", evidence_ids=["E020"])],
                failure_modes=[Claim(text="Fusarium risk around flowering", evidence_ids=["E021"])],
            ),
            LifecycleStage(
                stage="Senescence",
                description="Maturation and canopy decline.",
                key_decisions=[Claim(text="Harvest timing trade-offs", evidence_ids=["E022"])],
                observables=[Claim(text="Dry-down status", evidence_ids=["E023"])],
                failure_modes=[Claim(text="Lodging before harvest", evidence_ids=["E024"])],
            ),
            LifecycleStage(
                stage="Post-harvest",
                description="Residue, storage, and rotation transition period.",
                key_decisions=[Claim(text="Residue management strategy", evidence_ids=["E025"])],
                observables=[Claim(text="Residue distribution and grain quality outcomes", evidence_ids=["E026"])],
                failure_modes=[Claim(text="Storage contamination risks", evidence_ids=["E027"])],
            ),
        ],
    )


def demo_response_set() -> QuestionnaireResponseSet:
    return QuestionnaireResponseSet(
        questionnaire_id="agronomy-core-v1",
        subject_id="wheat__pathogen_panel",
        responses=[
            QuestionAnswer(
                question_id="reusable_benchmark",
                status="answered",
                answer_markdown=(
                    "- A reusable benchmark is a stage-specific pathogen pressure panel tied to emergence, "
                    "canopy closure, and flowering.\n"
                    "- A companion diagnostic is a standardized sampling + assay bundle for dominant fungal pressure windows."
                ),
                key_claims=[
                    Claim(
                        text="Stage-specific pathogen pressure panels can be standardized across wheat trials.",
                        evidence_ids=["E100", "E101"],
                        evidence_urls=["https://example.org/a", "https://example.org/b"],
                        support="direct",
                    )
                ],
            ),
            QuestionAnswer(
                question_id="recurring_monitoring",
                status="partial",
                answer_markdown=(
                    "- Recurring monitoring is most defensible during vegetative and reproductive windows.\n"
                    "- Frequency should be tied to disease pressure and weather transitions rather than a fixed universal cadence."
                ),
                key_claims=[
                    Claim(
                        text="Monitoring cadence should follow disease pressure windows rather than a single fixed schedule.",
                        evidence_ids=["E102"],
                        evidence_urls=["https://example.org/c"],
                        support="partial",
                    )
                ],
            ),
        ],
    )


def main() -> None:
    root = Path(__file__).resolve().parent
    dossier = demo_dossier()
    response_set = demo_response_set()

    md_dir = root / "generated"
    md_dir.mkdir(exist_ok=True)

    (md_dir / "wheat.dossier.md").write_text(render_crop_dossier_markdown(dossier), encoding="utf-8")
    (md_dir / "wheat.questionnaire.md").write_text(
        render_questionnaire_response_markdown(response_set), encoding="utf-8"
    )
    (md_dir / "wheat.dossier.json").write_text(
        json.dumps(dossier.model_dump(mode="json"), indent=2, default=str), encoding="utf-8"
    )
    (md_dir / "wheat.questionnaire.json").write_text(
        json.dumps(response_set.model_dump(mode="json"), indent=2, default=str), encoding="utf-8"
    )

    spec_path = root / "questionnaire.agronomy.yaml"
    spec = QuestionnaireSpec.model_validate(yaml.safe_load(spec_path.read_text(encoding="utf-8")))
    (md_dir / "questionnaire_spec.json").write_text(
        json.dumps(spec.model_dump(mode="json"), indent=2, default=str), encoding="utf-8"
    )

    print(f"Wrote demo artifacts to: {md_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
