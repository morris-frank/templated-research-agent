"""Cross-crop deterministic synthesis (dossier + questionnaire JSON)."""

from research_agent.synthesis.pipeline import (
    extract_concepts_from_dossier,
    extract_concepts_from_questionnaire,
    load_manifest,
    run_synthesis,
)

__all__ = [
    "extract_concepts_from_dossier",
    "extract_concepts_from_questionnaire",
    "load_manifest",
    "run_synthesis",
]
