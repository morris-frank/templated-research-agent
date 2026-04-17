"""Shared, dependency-light schemas used by both retrieval and the agent loop.

Kept separate from ``research_agent.agent.schemas`` so that retrieval modules do
not have to import the agent package (which pulls in the OpenAI client stack via
``research_agent.agent.llm``).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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


class PlanOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subquestions: list[str]
    web_queries: list[str]
    paper_queries: list[str]
    evidence_requirements: list[str]


__all__ = ["InputVars", "EvidenceItem", "PlanOut"]
