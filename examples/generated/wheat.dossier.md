# External Crop Dossier Template

### Metadata

- Crop Name: Wheat
- Crop Category: cereal
- Primary Use Cases: pathogen panel, inoculant validation
- Priority Tier: T1
- Last Updated: 2026-04-17

### Production System Context

#### Geographies

- Core regions: EU, North America
- Climate zones: temperate

#### Production Modes

- Open field / greenhouse / trial station: open field, trial station
- Conventional / organic / biological-heavy: conventional, organic

#### Rotation Role

- Typical preceding crops:
- Oilseed rape often precedes wheat in temperate rotations [evidence: E001]
- Typical succeeding crops:
- Wheat is often followed by barley or break crops depending on region [evidence: E002]
- Known rotation effects:
- Rotation affects disease pressure and nutrient carryover [evidence: E003]

### Lifecycle Ontology (CRITICAL)

Define discrete, platform-relevant stages.

| Stage | Description | Key Decisions | Observables | Failure Modes |
| --- | --- | --- | --- | --- |
| Pre-plant | Field and seed preparation before sowing. | Seed treatment selection | Soil condition and residue load | Poor seedbed conditions |
| Establishment | Emergence and stand establishment. | Replant threshold decisions | Stand count and emergence uniformity | Uneven emergence |
| Vegetative | Canopy development and biomass accumulation. | Nitrogen timing | Canopy vigor and disease incidence | Early disease establishment |
| Reproductive | Heading, flowering, grain set. | Fungicide timing near flowering | Spike health and flowering progression | Fusarium risk around flowering |
| Senescence | Maturation and canopy decline. | Harvest timing trade-offs | Dry-down status | Lodging before harvest |
| Post-harvest | Residue, storage, and rotation transition period. | Residue management strategy | Residue distribution and grain quality outcomes | Storage contamination risks |

### Yield Drivers

| Name | Mechanism | Proxies | Evidence |
| --- | --- | --- | --- |
| Canopy nitrogen status | Canopy N drives photosynthetic capacity and grain fill duration. | SPAD; canopy NDRE; tissue N | E200, E201 |
| Water availability during grain fill | Water stress during grain fill shortens the effective fill window. | soil moisture; ET estimates | E202 |
| Disease pressure at flowering | Flowering-window disease pressure reduces grain number and quality. | weather-based disease models; scouting counts | E203 |

### Limiting Factors

| Factor | Stage | Symptoms | Evidence |
| --- | --- | --- | --- |
| Early-season nitrogen deficiency | Vegetative | Chlorotic lower leaves and reduced tillering | E210 |
| Fusarium head blight at flowering | Reproductive | Bleached spikelets and DON accumulation | E211 |

### Agronomist Heuristics

- If `low canopy N AND early vegetative` then **apply split N top-dressing** (rationale: Split N applications align supply with vegetative demand peaks. [evidence: E220]) [evidence: E220]

### Interventions

| Kind | Name | Evidence |
| --- | --- | --- |
| input | Seed treatment (fungicide + biocontrol) | E230 |
| management | Split nitrogen application | E231 |
| genetic | Fusarium-resistant cultivar | E232 |

### Intervention Effects

- **Split nitrogen application** increase yield driver: Canopy nitrogen status — rationale: Split N keeps canopy N above critical through stem elongation. [evidence: E240] [evidence: E240]
- **Fusarium-resistant cultivar** decrease pathogen: Fusarium graminearum — rationale: Resistant cultivars reduce Fusarium severity under conducive weather. [evidence: E241] [evidence: E241]

### Biotic Risks

**Pathogens**

- Fusarium graminearum — pressure: warm, humid flowering window; stages: Reproductive [evidence: E250]
- Septoria tritici — pressure: prolonged leaf wetness; stages: Vegetative, Reproductive [evidence: E251]


### Soil & Microbiome

**Soil dependencies**

- pH — Soil pH governs micronutrient availability and Fusarium inoculum dynamics. [evidence: E260] [evidence: E260]

**Microbiome functions**

- Soil pathogen suppression — Suppressive soils reduce Fusarium inoculum load season over season. [evidence: E270] [evidence: E270]

### Cover Crop Effects

- Mustard → soil: pH: Brassica cover crops can shift soil microbial communities and suppress some soil pathogens. [evidence: E280] [evidence: E280]

### Open Questions

- Which microbiome signals best predict Fusarium suppression at field scale?
- Does split-N interact with resistant-cultivar deployment on DON accumulation?

### Confidence

- 0.72