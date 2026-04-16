"""Evidence retrieval (web + scholarly). Optional dependency: pip install 'research-agent[retrieval]'."""

from research_agent.retrieval.scoring import assign_evidence_ids, dedupe_evidence, score_evidence
from research_agent.retrieval.sources import (
    retrieve_scholarly_by_query,
    retrieve_scholarly_by_url,
    tavily_search,
)

__all__ = [
    "assign_evidence_ids",
    "dedupe_evidence",
    "score_evidence",
    "tavily_search",
    "retrieve_scholarly_by_url",
    "retrieve_scholarly_by_query",
]
