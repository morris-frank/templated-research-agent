from future import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

from contracts.core.claims import Claim

AnswerKind = Literal["short_text", "bullet_list", "enum", "matrix", "claim_set"]
EvidencePolicy = Literal["web_ok", "papers_preferred", "papers_required", "mixed_required"]
QuestionStatus = Literal["answered", "partial", "not_applicable", "insufficient_evidence"]

class QuestionSpec(BaseModel):
id: str
category: str
prompt_template: str
variables: list[str] = Field(default_factory=list)
answer_kind: AnswerKind = "claim_set"
applicability_rules: list[str] = Field(default_factory=list)
required_context: list[str] = Field(default_factory=list)
evidence_policy: EvidencePolicy = "mixed_required"
guidance: str | None = None
tags: list[str] = Field(default_factory=list)

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
