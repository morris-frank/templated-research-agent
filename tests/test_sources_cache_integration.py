from __future__ import annotations

import pytest

pytestmark = pytest.mark.retrieval

from research_agent.retrieval.cache import CacheSettings
from research_agent.retrieval.sources import (
    collect_evidence_for_plan,
    collect_evidence_for_queries,
    tavily_search,
)
from research_agent.types import EvidenceItem, InputVars, PlanOut


def _item(eid: str, title: str) -> EvidenceItem:
    return EvidenceItem(
        id=eid,
        source_type="web",
        retrieval_method="test",
        title=title,
        url=f"https://example.org/{title}",
    )


def test_collect_queries_cache_hit_and_refresh(monkeypatch, tmp_path) -> None:
    calls = {"tavily": 0, "scholar": 0}

    def fake_tavily(query: str, max_results: int = 5, *, cache_settings=None):
        calls["tavily"] += 1
        return [_item("", f"w-{query}")]

    def fake_scholarly(query: str, *, cache_settings=None):
        calls["scholar"] += 1
        return [_item("", f"p-{query}")]

    monkeypatch.setattr("research_agent.retrieval.sources.tavily_search", fake_tavily)
    monkeypatch.setattr("research_agent.retrieval.sources.retrieve_scholarly_by_query", fake_scholarly)

    plan = PlanOut(subquestions=[], web_queries=["a"], paper_queries=["b"], evidence_requirements=[])
    s_default = CacheSettings(mode="default", cache_dir=str(tmp_path))
    first = collect_evidence_for_queries(plan, cache_settings=s_default)
    second = collect_evidence_for_queries(plan, cache_settings=s_default)
    assert [e.id for e in first] == [e.id for e in second]
    assert calls["tavily"] == 1
    assert calls["scholar"] == 1

    s_refresh = CacheSettings(mode="refresh", cache_dir=str(tmp_path))
    _ = collect_evidence_for_queries(plan, cache_settings=s_refresh)
    assert calls["tavily"] == 2
    assert calls["scholar"] == 2


def test_collect_plan_stale_fallback(monkeypatch, tmp_path) -> None:
    state = {"ok": True}

    def fake_url(url: str, *, cache_settings=None):
        return [_item("", "seed")]

    def fake_queries(plan: PlanOut, cache_settings=None):
        if state["ok"]:
            return [_item("", "query")]
        raise RuntimeError("boom")

    monkeypatch.setattr("research_agent.retrieval.sources.retrieve_scholarly_by_url", fake_url)
    monkeypatch.setattr("research_agent.retrieval.sources.collect_evidence_for_queries", fake_queries)

    plan = PlanOut(subquestions=[], web_queries=["a"], paper_queries=[], evidence_requirements=[])
    inp = InputVars(topic="t", source_urls=["https://example.org"])
    settings = CacheSettings(mode="default", cache_dir=str(tmp_path))
    first = collect_evidence_for_plan(plan, inp, cache_settings=settings)
    state["ok"] = False
    second = collect_evidence_for_plan(plan, inp, cache_settings=settings)
    assert [e.id for e in first] == [e.id for e in second]


def test_negative_cache_policy_does_not_write_on_exception(monkeypatch, tmp_path) -> None:
    writes = {"n": 0}

    def fail_post(*args, **kwargs):
        raise RuntimeError("network")

    def count_cache_set(*args, **kwargs):
        writes["n"] += 1

    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setattr("requests.post", fail_post)
    monkeypatch.setattr("research_agent.retrieval.sources._cache_set_rows", count_cache_set)
    settings = CacheSettings(mode="default", cache_dir=str(tmp_path))
    for _ in range(2):
        try:
            tavily_search("same-query", cache_settings=settings)
        except Exception:
            pass
    assert writes["n"] == 0


