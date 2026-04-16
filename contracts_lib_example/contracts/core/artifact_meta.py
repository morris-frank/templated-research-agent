from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class ArtifactMeta(BaseModel):
    artifact_id: str = Field(..., description="Stable artifact identifier")
    artifact_type: str = Field(..., description="Logical artifact type")
    created_at: datetime | None = None
    updated_at: datetime | None = None
    version: str = "0.1.0"
    source_run_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    owner: str | None = None
    effective_date: date | None = None
