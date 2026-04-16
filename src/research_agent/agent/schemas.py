from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class InputVars(BaseModel):
    company: str | None = None
    topic: str
    region: str | None = None
    source_urls: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    id: str
    source_type: Literal["web", "paper", "seed_url"]
    retrieval_method: str
    title: str
    url: str
    doi: str | None = None
    abstract_or_snippet: str = ""
    venue: str | None = None
    year: int | None = None
    authors: list[str] = Field(default_factory=list)
    score: float = 0.0
    supports: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class Claim(BaseModel):
    text: str
    evidence_ids: list[str] = Field(min_length=1)
    evidence_urls: list[str] = Field(default_factory=list)
    support: Literal["direct", "partial", "contextual"] = "direct"
    notes: str | None = None


class FinalReport(BaseModel):
    summary: str
    key_findings: list[Claim]
    scientific_evidence: list[Claim]
    market_context: list[Claim]
    open_questions: list[str]
    confidence: Literal["low", "medium", "high"]


class PlanOut(BaseModel):
    subquestions: list[str]
    web_queries: list[str]
    paper_queries: list[str]
    evidence_requirements: list[str]


class GapQueries(BaseModel):
    web_queries: list[str] = Field(default_factory=list)
    paper_queries: list[str] = Field(default_factory=list)
