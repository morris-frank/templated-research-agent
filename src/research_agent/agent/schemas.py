from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from research_agent.types import EvidenceItem, InputVars, PlanOut

__all__ = [
    "Claim",
    "EvidenceItem",
    "FinalReport",
    "GapQueries",
    "InputVars",
    "PlanOut",
]


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    evidence_ids: list[str] = Field(min_length=1)
    evidence_urls: list[str] = Field(default_factory=list)
    support: Literal["direct", "partial", "contextual"] = "direct"
    notes: str | None = None


class FinalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    key_findings: list[Claim]
    scientific_evidence: list[Claim]
    market_context: list[Claim]
    open_questions: list[str]
    confidence: Literal["low", "medium", "high"]


class GapQueries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    web_queries: list[str] = Field(default_factory=list)
    paper_queries: list[str] = Field(default_factory=list)
