"""Validated synthesis manifest (JSON on disk)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ThresholdSpec(BaseModel):
    min_crops: int = 2
    min_mentions: int = 1


class ManifestThresholds(BaseModel):
    default: ThresholdSpec = Field(default_factory=ThresholdSpec)
    by_kind: dict[str, ThresholdSpec] = Field(default_factory=dict)


class RunSpec(BaseModel):
    run_id: str
    dossier: str
    questionnaire: str | None = None
    questionnaire_spec: str | None = None
    prioritization_context: dict[str, Any] | None = None


class SynthesisManifest(BaseModel):
    """Manifest for research-agent-synthesize."""

    version: int = 1
    runs: list[RunSpec] = Field(default_factory=list)
    inputs: list[RunSpec] | None = None
    thresholds: ManifestThresholds | None = None
    min_crops_for_pattern: int | None = None
    min_mentions: int | None = None
    include_questionnaire_answer_blobs: bool = False

    @model_validator(mode="after")
    def _runs_alias(self) -> SynthesisManifest:
        if not self.runs and self.inputs:
            object.__setattr__(self, "runs", list(self.inputs))
        return self

    def effective_thresholds(self) -> ManifestThresholds:
        th = self.thresholds or ManifestThresholds()
        if self.min_crops_for_pattern is not None:
            th = th.model_copy(
                update={
                    "default": th.default.model_copy(
                        update={"min_crops": self.min_crops_for_pattern}
                    )
                }
            )
        if self.min_mentions is not None:
            d = th.default.model_copy(update={"min_mentions": self.min_mentions})
            th = th.model_copy(update={"default": d})
        return th

    def threshold_for_kind(self, kind: str) -> ThresholdSpec:
        eff = self.effective_thresholds()
        if kind in eff.by_kind:
            return eff.by_kind[kind]
        return eff.default


def parse_manifest_file(path: Path) -> tuple[SynthesisManifest, Path]:
    data = json.loads(path.read_text(encoding="utf-8"))
    m = SynthesisManifest.model_validate(data)
    if not m.runs:
        raise ValueError("manifest must contain a non-empty runs (or inputs) array")
    return m, path.parent
