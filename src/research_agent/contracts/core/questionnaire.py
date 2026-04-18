from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from research_agent.contracts.core.claims import Claim

AnswerKind = Literal["short_text", "bullet_list", "enum", "matrix", "claim_set"]
EvidencePolicy = Literal["web_ok", "papers_preferred", "papers_required", "mixed_required"]
QuestionStatus = Literal["answered", "partial", "not_applicable", "insufficient_evidence"]

ApplicabilityOp = Literal["present", "non_empty", "contains_keyword", "has_tag"]


class ApplicabilityRule(BaseModel):
    """Typed applicability predicate; semantics are resolved by domain execution helpers."""

    op: ApplicabilityOp
    field: str = ""
    value: str | None = None


class SkippedQuestion(BaseModel):
    question_id: str
    applicable: bool
    skip_reason: str | None = None


class QuestionnaireCoverage(BaseModel):
    total: int
    applicable: int
    answered: int
    insufficient_evidence: int
    not_applicable: int
    coverage_ratio: float = Field(
        ...,
        description="answered / applicable when applicable > 0, else 0.0",
    )


class QuestionSpec(BaseModel):
    id: str
    category: str
    prompt_template: str
    variables: list[str] = Field(default_factory=list)
    answer_kind: AnswerKind = "claim_set"
    applicability_rules: list[ApplicabilityRule] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)
    evidence_policy: EvidencePolicy = "mixed_required"
    guidance: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("applicability_rules", mode="before")
    @classmethod
    def _coerce_legacy_string_rules(cls, v: Any) -> Any:
        """Allow legacy YAML where each rule was a dossier field name string (treated as ``present``)."""
        if v is None:
            return []
        out: list[Any] = []
        for item in v:
            if isinstance(item, str):
                out.append({"op": "present", "field": item})
            else:
                out.append(item)
        return out

    def render_prompt(self, variables: dict[str, Any]) -> str:
        return self.prompt_template.format(**variables)


class QuestionInstance(BaseModel):
    spec_id: str
    variables: dict[str, str]
    rendered_prompt: str
    category: str
    answer_kind: AnswerKind
    evidence_policy: EvidencePolicy
    required_context: list[str] = Field(default_factory=list)


class QuestionAnswerDraft(BaseModel):
    """LLM output shape for a single question; question_id is added when building QuestionAnswer."""

    model_config = ConfigDict(extra="forbid")

    status: QuestionStatus
    answer_markdown: str
    key_claims: list[Claim] = Field(default_factory=list)
    rationale: str | None = None


class QuestionAnswer(BaseModel):
    question_id: str
    status: QuestionStatus
    answer_markdown: str
    key_claims: list[Claim] = Field(default_factory=list)
    rationale: str | None = None

    def is_useful(self) -> bool:
        return self.status in {"answered", "partial"}


class QuestionnaireSpec(BaseModel):
    questionnaire_id: str
    domain: str
    version: str = "0.1.0"
    questions: list[QuestionSpec]


class QuestionnaireResponseSet(BaseModel):
    questionnaire_id: str
    subject_id: str
    responses: list[QuestionAnswer]


class QuestionnaireExecutionResult(BaseModel):
    responses: QuestionnaireResponseSet
    coverage: QuestionnaireCoverage
    skipped_questions: list[SkippedQuestion] = Field(default_factory=list)
    stop_reason: str | None = None
    evidence_validation_errors: list[str] = Field(
        default_factory=list,
        description="Deterministic post-pass checks (e.g. claim evidence_ids not in retrieved set).",
    )
