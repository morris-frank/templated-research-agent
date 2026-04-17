# 1) Complete the dossier schema

## Objective

Upgrade `CropDossier` from descriptive summary → **decision-support artifact + ontology seed**

## Target structure (MECE)

```python
class CropDossier(BaseModel):
    # A. Identity
    crop: str
    use_case: Optional[str]

    # B. Production context
    production_systems: list[str]  # e.g. irrigated maize, dryland wheat

    # C. Biological structure
    lifecycle_stages: list[LifecycleStage]
    cultivar_segments: list[CultivarSegment]

    # D. Agronomic model (NEW CORE)
    yield_drivers: list[YieldDriver]            # causal factors
    limiting_factors: list[LimitingFactor]      # common constraints
    agronomist_heuristics: list[HeuristicRule]  # decision rules

    # E. Intervention layer
    interventions: list[Intervention]
    intervention_effects: list[InterventionEffect]

    # F. Biotic risks
    pathogens: list[Pathogen]
    beneficials: list[BeneficialOrganism]

    # G. Soil / microbiome relevance
    soil_dependencies: list[SoilDependency]
    microbiome_roles: list[MicrobiomeFunction]

    # H. System interactions
    rotation_effects: list[RotationEffect]
    cover_crop_effects: list[CoverCropEffect]

    # I. Evidence
    evidence_items: list[EvidenceRef]
    confidence: float
    open_questions: list[str]
```

## New atomic types (minimal)

```python
class YieldDriver:
    name: str
    mechanism: str
    measurable_proxies: list[str]

class LimitingFactor:
    factor: str
    stage: Optional[str]
    symptoms: list[str]

class HeuristicRule:
    condition: str   # "low N + early vegetative"
    action: str      # "apply X"
    rationale: str

class Intervention:
    type: str  # input / management / genetic
    name: str

class InterventionEffect:
    intervention: str
    target: str   # yield driver / pathogen / soil property
    effect: str   # increase/decrease/conditional

class Pathogen:
    name: str
    pressure_conditions: list[str]
    affected_stages: list[str]

class SoilDependency:
    variable: str  # pH, texture, SOM
    role: str

class MicrobiomeFunction:
    function: str  # N fixation, pathogen suppression
    importance: str
```

## Implementation steps

1. Extend Pydantic models
2. Update dossier renderer (sectioned markdown)
3. Update research prompts:

   * force extraction into these fields
4. Add validation:

   * minimum coverage thresholds (e.g. ≥3 yield drivers)

## Acceptance criteria

* Dossier contains **causal structure**, not just description
* At least:

  * 3 yield drivers
  * 3 interventions
  * 2 pathogens
* Evidence references linked to ≥50% of claims

---

# 2) Questionnaire instantiation + filtering

## Objective

Turn questionnaire from static spec → **dynamic, dossier-aware execution plan**

## Workflow

### Step 1 — Instantiate

Input:

* `QuestionnaireSpec`
* variables: `{crop}`, `{use_case}`

Output:

* `InstantiatedQuestionSet`

```python
class InstantiatedQuestion:
    id: str
    text: str
    variables: dict
```

---

### Step 2 — Applicability filtering (NEW CORE)

Filter questions using dossier signals.

```python
class ApplicabilityRule:
    requires: list[str]  # e.g. "microbiome_roles"
    condition: Optional[str]  # simple expression
```

Example:

```yaml
- id: microbe_interaction
  requires: ["microbiome_roles"]
```

---

### Step 3 — Filtering engine

```python
def filter_questions(dossier, questions):
    return [
        q for q in questions
        if satisfies(q.applicability, dossier)
    ]
```

`satisfies()`:

* field presence
* simple keyword match
* optional heuristic scoring

---

### Step 4 — Answer generation

Each question answered with:

```python
class QuestionAnswer:
    question_id: str
    answer: str
    evidence_ids: list[str]
    confidence: float
```

Constraint:

* must reference:

  * ≥1 dossier element
  * ≥1 external evidence item

---

### Step 5 — Coverage report

```python
class QuestionnaireCoverage:
    total: int
    applicable: int
    answered: int
    coverage_ratio: float
```

---

## Implementation steps

1. Add `InstantiatedQuestion` + rules
2. Implement filter engine (simple first: field presence)
3. Update answer prompt:

   * include dossier context
4. Add coverage metrics

## Acceptance criteria

* ≥70% of applicable questions answered
* Each answer links:

  * ≥1 dossier field
  * ≥1 external source

---

# 3) Crop/use-case prioritization artifact

## Objective

Formalize Tier-1 selection instead of ad hoc reasoning

## Data model

```python
class CropUseCaseCandidate:
    crop: str
    use_case: str

    # Scores
    icp_fit: float
    platform_leverage: float
    data_availability: float
    evidence_strength: float

    # Derived
    priority_score: float

    rationale: list[str]  # claim IDs or short statements
```

---

## Scoring dimensions (MECE)

### A. ICP fit

* alignment with agri-input R&D
* relevance to biologicals / trials

### B. Platform leverage

* reuse of:

  * microbiome diagnostics
  * soil analytics
  * intervention modeling

### C. Data availability

* literature density
* public datasets

### D. Evidence strength

* consistency across sources

---

## Scoring function

```python
priority_score =
    0.35 * icp_fit +
    0.35 * platform_leverage +
    0.15 * data_availability +
    0.15 * evidence_strength
```

---

## Workflow

1. Generate candidate set (manual or seeded list)
2. Run research-lite pass per candidate
3. Score via LLM rubric + heuristics
4. Sort → Tier 1

---

## Output

```python
class TierList:
    tier_1: list[CropUseCaseCandidate]
    tier_2: list[CropUseCaseCandidate]
```

---

## Implementation steps

1. Define scoring rubric prompt
2. Implement batch evaluation CLI
3. Persist results (JSON)

## Acceptance criteria

* Ranked list reproducible given same inputs
* Rationales reference evidence (not free text only)

---

# 4) Cross-crop synthesis → ontology → platform primitives

## Objective

Turn many dossiers into **reusable system design inputs**

---

## Step 1 — Normalize dossiers

Extract canonical elements:

```python
class NormalizedConcept:
    type: str  # yield_driver / pathogen / intervention
    name: str
```

---

## Step 2 — Cluster concepts

Simple initial approach:

```python
group by (type, normalized_name)
```

Future: embedding similarity

---

## Step 3 — Identify cross-crop patterns

```python
class CrossCropPattern:
    concept: str
    occurrence_count: int
    crops: list[str]
```

Filter:

* keep patterns appearing in ≥2 crops

---

## Step 4 — Derive ontology

```python
class OntologyNode:
    name: str
    type: str
    relationships: list[str]
```

Relationships:

* affects
* depends_on
* mitigated_by

---

## Step 5 — Platform primitives

```python
class PlatformPrimitive:
    name: str
    type: str  # entity / process / metric
    description: str
    derived_from: list[str]  # patterns
```

Examples:

* `SoilNitrogenAvailability`
* `PathogenPressureIndex`
* `MicrobiomeFunctionalCapacity`
* `InterventionEffectModel`

---

## Step 6 — Output artifact

```python
class SynthesisOutput:
    patterns: list[CrossCropPattern]
    ontology: list[OntologyNode]
    primitives: list[PlatformPrimitive]
```

---

## Implementation steps

1. Write extractor from dossier → normalized concepts
2. Implement grouping logic
3. Add simple frequency thresholding
4. Generate primitives via template + LLM summarization

---

## Acceptance criteria

* ≥10 cross-crop patterns identified (for ≥3 crops)
* ≥5 reusable primitives generated
* Each primitive linked to ≥2 source crops

---

# Execution order (critical path)

1. **Dossier schema (1)**
   → unlocks structured knowledge

2. **Questionnaire filtering (2)**
   → operationalizes dossier

3. **Prioritization (3)**
   → defines what to run

4. **Synthesis (4)**
   → extracts platform value

---

# Key dependency graph

```
Dossier → Questionnaire → (per crop outputs)
        → Synthesis → Platform primitives

Prioritization → selects which dossiers to build
```

---

# Final constraint (important)

If dossiers remain descriptive (current state), then:

* questionnaire filtering will be weak
* synthesis will collapse into noisy text clustering

So **(1) is the linchpin**.
