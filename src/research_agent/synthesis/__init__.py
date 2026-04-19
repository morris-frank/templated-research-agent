"""Cross-crop deterministic synthesis (dossier + questionnaire JSON)."""

from research_agent.synthesis.manifest import SynthesisManifest
from research_agent.synthesis.pipeline import (
    extract_concepts_from_dossier,
    extract_concepts_from_questionnaire,
    load_manifest,
    resolve_safe_path,
    run_synthesis,
)

__all__ = [
    "SynthesisManifest",
    "extract_concepts_from_dossier",
    "extract_concepts_from_questionnaire",
    "load_manifest",
    "resolve_safe_path",
    "run_synthesis",
]
