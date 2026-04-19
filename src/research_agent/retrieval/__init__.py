"""Evidence retrieval (web + scholarly). Optional dependency: pip install 'research-agent[retrieval]'.

Importing this package loads only :mod:`scoring` (uses ``research_agent.types``). Functions that need
HTTP, feed parsing, or Tavily live in :mod:`research_agent.retrieval.sources` and are re-exported
lazily via :func:`__getattr__` so ``import research_agent.retrieval`` does not pull optional deps.
"""

from __future__ import annotations

from typing import Any

from research_agent.retrieval.scoring import assign_evidence_ids, dedupe_evidence, score_evidence

__all__ = [
    "assign_evidence_ids",
    "dedupe_evidence",
    "score_evidence",
    "tavily_search",
    "retrieve_scholarly_by_url",
    "retrieve_scholarly_by_query",
]


def __getattr__(name: str) -> Any:
    if name in ("tavily_search", "retrieve_scholarly_by_url", "retrieve_scholarly_by_query"):
        from research_agent.retrieval import sources as _sources

        return getattr(_sources, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
