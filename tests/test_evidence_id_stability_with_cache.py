from __future__ import annotations

from research_agent.retrieval.cache import CacheSettings
from research_agent.retrieval.sources import collect_evidence_for_queries
from research_agent.types import EvidenceItem, PlanOut


def test_evidence_ids_stable_across_cache_hits(monkeypatch, tmp_path) -> None:
    def fake_tavily(query: str, max_results: int = 5, *, cache_settings=None):
        return [
            EvidenceItem(
                id="",
                source_type="web",
                retrieval_method="test",
                title=f"A-{query}",
                url=f"https://example.org/a/{query}",
                score=0.8,
            )
        ]

    def fake_scholarly(query: str, *, cache_settings=None):
        return [
            EvidenceItem(
                id="",
                source_type="paper",
                retrieval_method="test",
                title=f"B-{query}",
                url=f"https://example.org/b/{query}",
                score=1.2,
            )
        ]

    monkeypatch.setattr("research_agent.retrieval.sources.tavily_search", fake_tavily)
    monkeypatch.setattr("research_agent.retrieval.sources.retrieve_scholarly_by_query", fake_scholarly)
    plan = PlanOut(subquestions=[], web_queries=["q"], paper_queries=["q"], evidence_requirements=[])
    settings = CacheSettings(mode="default", cache_dir=str(tmp_path))
    run1 = collect_evidence_for_queries(plan, cache_settings=settings)
    run2 = collect_evidence_for_queries(plan, cache_settings=settings)
    assert [e.id for e in run1] == [e.id for e in run2]

