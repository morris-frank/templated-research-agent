from future import annotations

from pydantic import BaseModel, Field

from contracts.core.questionnaire import QuestionSpec

class AgronomyQuestionSpec(QuestionSpec):
target_entities: list[str] = Field(default_factory=lambda: ["crop", "use_case"])
source_bias: list[str] = Field(
default_factory=lambda: ["extension", "scientific", "industry", "institutional"]
)
