from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from research_agent.contracts.agronomy.dossier import (
    CoverCropEffect,
    CropDossier,
    HeuristicRule,
    Intervention,
    InterventionEffect,
    LifecycleStage,
    LimitingFactor,
    MicrobiomeFunction,
    Pathogen,
    ProductionSystemContext,
    RotationRole,
    SoilDependency,
    YieldDriver,
)
from research_agent.contracts.core.artifact_meta import ArtifactMeta
from research_agent.contracts.core.claims import Claim
from research_agent.contracts.core.evidence import EvidenceRef
from research_agent.contracts.core.questionnaire import (
    QuestionAnswer,
    QuestionnaireCoverage,
    QuestionnaireExecutionResult,
    QuestionnaireResponseSet,
    QuestionnaireSpec,
    SkippedQuestion,
)
from research_agent.contracts.renderers.markdown import (
    render_crop_dossier_markdown,
    render_questionnaire_execution_markdown,
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
        yield_drivers=[
            YieldDriver(
                id="YD001",
                name="Canopy nitrogen status",
                mechanism=Claim(
                    text="Canopy N drives photosynthetic capacity and grain fill duration.",
                    evidence_ids=["E200"],
                ),
                measurable_proxies=["SPAD", "canopy NDRE", "tissue N"],
                evidence_ids=["E200", "E201"],
            ),
            YieldDriver(
                id="YD002",
                name="Water availability during grain fill",
                mechanism=Claim(
                    text="Water stress during grain fill shortens the effective fill window.",
                    evidence_ids=["E202"],
                ),
                measurable_proxies=["soil moisture", "ET estimates"],
                evidence_ids=["E202"],
            ),
            YieldDriver(
                id="YD003",
                name="Disease pressure at flowering",
                mechanism=Claim(
                    text="Flowering-window disease pressure reduces grain number and quality.",
                    evidence_ids=["E203"],
                ),
                measurable_proxies=["weather-based disease models", "scouting counts"],
                evidence_ids=["E203"],
            ),
        ],
        limiting_factors=[
            LimitingFactor(
                id="LF001",
                factor="Early-season nitrogen deficiency",
                stage="Vegetative",
                symptoms=[
                    Claim(
                        text="Chlorotic lower leaves and reduced tillering",
                        evidence_ids=["E210"],
                    )
                ],
                evidence_ids=["E210"],
            ),
            LimitingFactor(
                id="LF002",
                factor="Fusarium head blight at flowering",
                stage="Reproductive",
                symptoms=[
                    Claim(
                        text="Bleached spikelets and DON accumulation",
                        evidence_ids=["E211"],
                    )
                ],
                evidence_ids=["E211"],
            ),
        ],
        agronomist_heuristics=[
            HeuristicRule(
                id="HR001",
                condition="low canopy N AND early vegetative",
                action="apply split N top-dressing",
                rationale=Claim(
                    text="Split N applications align supply with vegetative demand peaks.",
                    evidence_ids=["E220"],
                ),
                evidence_ids=["E220"],
            ),
        ],
        interventions=[
            Intervention(
                id="IV001",
                kind="input",
                name="Seed treatment (fungicide + biocontrol)",
                evidence_ids=["E230"],
            ),
            Intervention(
                id="IV002",
                kind="management",
                name="Split nitrogen application",
                evidence_ids=["E231"],
            ),
            Intervention(
                id="IV003",
                kind="genetic",
                name="Fusarium-resistant cultivar",
                evidence_ids=["E232"],
            ),
        ],
        intervention_effects=[
            InterventionEffect(
                intervention_id="IV002",
                target_ref="YD001",
                effect="increase",
                rationale=Claim(
                    text="Split N keeps canopy N above critical through stem elongation.",
                    evidence_ids=["E240"],
                ),
                evidence_ids=["E240"],
            ),
            InterventionEffect(
                intervention_id="IV003",
                target_ref="PG001",
                effect="decrease",
                rationale=Claim(
                    text="Resistant cultivars reduce Fusarium severity under conducive weather.",
                    evidence_ids=["E241"],
                ),
                evidence_ids=["E241"],
            ),
        ],
        pathogens=[
            Pathogen(
                id="PG001",
                name="Fusarium graminearum",
                pressure_conditions=["warm, humid flowering window"],
                affected_stages=["Reproductive"],
                evidence_ids=["E250"],
            ),
            Pathogen(
                id="PG002",
                name="Septoria tritici",
                pressure_conditions=["prolonged leaf wetness"],
                affected_stages=["Vegetative", "Reproductive"],
                evidence_ids=["E251"],
            ),
        ],
        soil_dependencies=[
            SoilDependency(
                id="SD001",
                variable="pH",
                role=Claim(
                    text="Soil pH governs micronutrient availability and Fusarium inoculum dynamics.",
                    evidence_ids=["E260"],
                ),
                evidence_ids=["E260"],
            ),
        ],
        microbiome_roles=[
            MicrobiomeFunction(
                id="MB001",
                function="Soil pathogen suppression",
                importance=Claim(
                    text="Suppressive soils reduce Fusarium inoculum load season over season.",
                    evidence_ids=["E270"],
                ),
                evidence_ids=["E270"],
            ),
        ],
        cover_crop_effects=[
            CoverCropEffect(
                cover_crop="Mustard",
                target_ref="SD001",
                effect=Claim(
                    text="Brassica cover crops can shift soil microbial communities and suppress some soil pathogens.",
                    evidence_ids=["E280"],
                ),
                evidence_ids=["E280"],
            ),
        ],
        evidence_index=[
            EvidenceRef(
                id=eid,
                source_type="paper",
                title=f"Demo evidence {eid}",
                url="https://example.org/evidence",
            )
            for eid in [
                "E001", "E002", "E003",
                "E010", "E011", "E012", "E013", "E014", "E015",
                "E016", "E017", "E018", "E019", "E020", "E021",
                "E022", "E023", "E024", "E025", "E026", "E027",
                "E200", "E201", "E202", "E203",
                "E210", "E211",
                "E220",
                "E230", "E231", "E232",
                "E240", "E241",
                "E250", "E251",
                "E260", "E270", "E280",
            ]
        ],
        confidence=0.72,
        open_questions=[
            "Which microbiome signals best predict Fusarium suppression at field scale?",
            "Does split-N interact with resistant-cultivar deployment on DON accumulation?",
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
    demo_execution = QuestionnaireExecutionResult(
        responses=response_set,
        coverage=QuestionnaireCoverage(
            total=4,
            applicable=3,
            answered=2,
            insufficient_evidence=0,
            not_applicable=1,
            coverage_ratio=2 / 3,
        ),
        skipped_questions=[
            SkippedQuestion(
                question_id="fixed_scope_pilot",
                applicable=False,
                skip_reason="not_applicable:keyword_missing:barley",
            )
        ],
        stop_reason="demo_artifact",
    )
    (md_dir / "wheat.questionnaire.execution.md").write_text(
        render_questionnaire_execution_markdown(demo_execution), encoding="utf-8"
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
