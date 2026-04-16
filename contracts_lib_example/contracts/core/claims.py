from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SupportLevel = Literal["direct", "partial", "contextual"]


class Claim(BaseModel):
    """Narrative claim with inline evidence IDs (legacy dossier / questionnaire shape)."""

    text: str = Field(..., min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)
    support: SupportLevel = "direct"
    notes: str | None = None

    def has_support(self) -> bool:
        return bool(self.evidence_ids)
