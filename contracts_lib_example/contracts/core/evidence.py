from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

SourceType = Literal["web", "paper", "report", "institutional", "internal"]


class EvidenceRef(BaseModel):
    id: str = Field(..., description="Stable evidence ID within a run or artifact bundle")
    source_type: SourceType
    title: str
    url: HttpUrl
    snippet: str = ""
    publisher: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    accessed_at: str | None = None
    score: float = 0.0
    query: str | None = None
    notes: str | None = None
