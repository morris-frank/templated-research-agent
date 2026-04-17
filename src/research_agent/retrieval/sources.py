from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus, unquote

import feedparser
from bs4 import BeautifulSoup

from research_agent.types import EvidenceItem, InputVars, PlanOut
from research_agent.retrieval.doi import extract_doi_from_text, extract_doi_from_url, normalize_doi
from research_agent.retrieval.cache import (
    CACHE_SCHEMA_VERSION,
    EVIDENCE_SERIALIZATION_SCHEMA_VERSION,
    SCORING_SCHEMA_VERSION,
    CacheSettings,
    cache_key,
    get_cache,
    normalize_url_for_cache,
    should_read_cache,
    should_write_cache,
    TTL_AGGREGATE_SEC,
    TTL_DOI_LOOKUP_SEC,
    TTL_EMPTY_SHORT_SEC,
    TTL_PAGE_METADATA_SEC,
    TTL_PAPER_QUERY_SEC,
    TTL_TAVILY_SEC,
)
from research_agent.retrieval.http import USER_AGENT, http_get
from research_agent.retrieval.scoring import dedupe_evidence, score_evidence


def _base_cache_payload(**kwargs: object) -> dict[str, object]:
    return {
        "cache_schema": CACHE_SCHEMA_VERSION,
        "scoring_schema": SCORING_SCHEMA_VERSION,
        "evidence_serialization_schema": EVIDENCE_SERIALIZATION_SCHEMA_VERSION,
        **kwargs,
    }


def _serialize_evidence_items(items: list[EvidenceItem]) -> list[dict]:
    return [e.model_dump(mode="json") for e in items]


def _deserialize_evidence_items(rows: list[dict]) -> list[EvidenceItem]:
    return [EvidenceItem.model_validate(row) for row in rows]


def _cache_get_rows(key: str, settings: CacheSettings) -> list[dict] | None:
    if not should_read_cache(settings):
        return None
    cache = get_cache(settings.cache_dir)
    return cache.get(key)


def _cache_set_rows(key: str, rows: list[dict], ttl_sec: int, settings: CacheSettings) -> None:
    if not should_write_cache(settings):
        return
    cache = get_cache(settings.cache_dir)
    cache.set(key, rows, expire=ttl_sec)


def _cache_set_optional_row(key: str, row: dict | None, ttl_sec: int, settings: CacheSettings) -> None:
    if not should_write_cache(settings):
        return
    cache = get_cache(settings.cache_dir)
    cache.set(key, row, expire=ttl_sec)


def tavily_search(
    query: str, max_results: int = 5, *, cache_settings: CacheSettings | None = None
) -> list[EvidenceItem]:
    settings = cache_settings or CacheSettings()
    key = cache_key(
        "tavily_search",
        _base_cache_payload(query=query, max_results=max_results),
    )
    cached = _cache_get_rows(key, settings)
    if cached is not None:
        return _deserialize_evidence_items(cached)

    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is required")

    import requests

    r = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "advanced",
            "include_raw_content": False,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()

    results: list[EvidenceItem] = []
    for row in data.get("results", []):
        item = EvidenceItem(
            id="",
            source_type="web",
            retrieval_method="tavily_search",
            title=row.get("title", ""),
            url=row.get("url", ""),
            abstract_or_snippet=row.get("content", "") or "",
            score=0.0,
            raw=row,
        )
        item.score = score_evidence(item, query)
        results.append(item)
    ttl = TTL_EMPTY_SHORT_SEC if not results else TTL_TAVILY_SEC
    _cache_set_rows(key, _serialize_evidence_items(results), ttl, settings)
    return results


def crossref_lookup_doi(doi: str, *, cache_settings: CacheSettings | None = None) -> EvidenceItem | None:
    settings = cache_settings or CacheSettings()
    key = cache_key("crossref_lookup_doi", _base_cache_payload(doi=normalize_doi(doi) or doi))
    if should_read_cache(settings):
        cached = get_cache(settings.cache_dir).get(key)
        if cached is not None:
            return EvidenceItem.model_validate(cached) if cached else None

    url = f"https://api.crossref.org/works/{quote_plus(doi)}"
    r = http_get(url)
    msg = r.json().get("message", {})
    title = (msg.get("title") or [""])[0]
    authors = [
        " ".join(part for part in [a.get("given", ""), a.get("family", "")] if part).strip()
        for a in msg.get("author", [])
    ]
    year = None
    for key in ("published-print", "published-online", "created"):
        parts = (((msg.get(key) or {}).get("date-parts") or [[None]])[0])
        if parts and parts[0]:
            year = int(parts[0])
            break
    item = EvidenceItem(
        id="",
        source_type="paper",
        retrieval_method="crossref_doi",
        title=title,
        url=(msg.get("URL") or f"https://doi.org/{doi}"),
        doi=normalize_doi(msg.get("DOI") or doi),
        abstract_or_snippet=(msg.get("abstract") or "")[:4000],
        venue=(msg.get("container-title") or [None])[0],
        year=year,
        authors=[a for a in authors if a],
        raw=msg,
    )
    item.score = score_evidence(item, doi)
    out = item if item.title else None
    ttl = TTL_DOI_LOOKUP_SEC if out else TTL_EMPTY_SHORT_SEC
    _cache_set_optional_row(key, out.model_dump(mode="json") if out else None, ttl, settings)
    return out


def crossref_search_title(
    title: str, rows: int = 5, *, cache_settings: CacheSettings | None = None
) -> list[EvidenceItem]:
    settings = cache_settings or CacheSettings()
    key = cache_key("crossref_search_title", _base_cache_payload(title=title, rows=rows))
    cached = _cache_get_rows(key, settings)
    if cached is not None:
        return _deserialize_evidence_items(cached)

    r = http_get(
        "https://api.crossref.org/works",
        params={"query.title": title, "rows": rows},
    )
    items = []
    for msg in r.json().get("message", {}).get("items", []):
        t = (msg.get("title") or [""])[0]
        authors = [
            " ".join(part for part in [a.get("given", ""), a.get("family", "")] if part).strip()
            for a in msg.get("author", [])
        ]
        year = None
        for key in ("published-print", "published-online", "created"):
            parts = (((msg.get(key) or {}).get("date-parts") or [[None]])[0])
            if parts and parts[0]:
                year = int(parts[0])
                break
        item = EvidenceItem(
            id="",
            source_type="paper",
            retrieval_method="crossref_title",
            title=t,
            url=(msg.get("URL") or ""),
            doi=normalize_doi(msg.get("DOI")),
            abstract_or_snippet=(msg.get("abstract") or "")[:4000],
            venue=(msg.get("container-title") or [None])[0],
            year=year,
            authors=[a for a in authors if a],
            raw=msg,
        )
        item.score = score_evidence(item, title)
        items.append(item)
    ttl = TTL_EMPTY_SHORT_SEC if not items else TTL_PAPER_QUERY_SEC
    _cache_set_rows(key, _serialize_evidence_items(items), ttl, settings)
    return items


def openalex_lookup_doi(doi: str, *, cache_settings: CacheSettings | None = None) -> EvidenceItem | None:
    settings = cache_settings or CacheSettings()
    key = cache_key("openalex_lookup_doi", _base_cache_payload(doi=normalize_doi(doi) or doi))
    if should_read_cache(settings):
        cached = get_cache(settings.cache_dir).get(key)
        if cached is not None:
            return EvidenceItem.model_validate(cached) if cached else None

    doi_url = f"https://doi.org/{doi}"
    r = http_get("https://api.openalex.org/works", params={"filter": f"doi:{doi_url}", "per-page": 1})
    rows = r.json().get("results", [])
    if not rows:
        _cache_set_optional_row(key, None, TTL_EMPTY_SHORT_SEC, settings)
        return None
    row = rows[0]
    authors = [a.get("author", {}).get("display_name", "") for a in row.get("authorships", [])]
    item = EvidenceItem(
        id="",
        source_type="paper",
        retrieval_method="openalex_doi",
        title=row.get("display_name", ""),
        url=(row.get("primary_location") or {}).get("landing_page_url") or doi_url,
        doi=normalize_doi((row.get("ids") or {}).get("doi") or doi),
        abstract_or_snippet="",
        venue=((row.get("primary_location") or {}).get("source") or {}).get("display_name"),
        year=row.get("publication_year"),
        authors=[a for a in authors if a],
        raw=row,
    )
    item.score = score_evidence(item, doi)
    out = item if item.title else None
    ttl = TTL_DOI_LOOKUP_SEC if out else TTL_EMPTY_SHORT_SEC
    _cache_set_optional_row(key, out.model_dump(mode="json") if out else None, ttl, settings)
    return out


def openalex_search_title(
    title: str, rows: int = 5, *, cache_settings: CacheSettings | None = None
) -> list[EvidenceItem]:
    settings = cache_settings or CacheSettings()
    key = cache_key("openalex_search_title", _base_cache_payload(title=title, rows=rows))
    cached = _cache_get_rows(key, settings)
    if cached is not None:
        return _deserialize_evidence_items(cached)

    r = http_get("https://api.openalex.org/works", params={"search": title, "per-page": rows})
    out = []
    for row in r.json().get("results", []):
        authors = [a.get("author", {}).get("display_name", "") for a in row.get("authorships", [])]
        item = EvidenceItem(
            id="",
            source_type="paper",
            retrieval_method="openalex_title",
            title=row.get("display_name", ""),
            url=(row.get("primary_location") or {}).get("landing_page_url") or "",
            doi=normalize_doi((row.get("ids") or {}).get("doi")),
            abstract_or_snippet="",
            venue=((row.get("primary_location") or {}).get("source") or {}).get("display_name"),
            year=row.get("publication_year"),
            authors=[a for a in authors if a],
            raw=row,
        )
        item.score = score_evidence(item, title)
        out.append(item)
    ttl = TTL_EMPTY_SHORT_SEC if not out else TTL_PAPER_QUERY_SEC
    _cache_set_rows(key, _serialize_evidence_items(out), ttl, settings)
    return out


def arxiv_search(
    query: str, max_results: int = 5, *, cache_settings: CacheSettings | None = None
) -> list[EvidenceItem]:
    settings = cache_settings or CacheSettings()
    key = cache_key("arxiv_search", _base_cache_payload(query=query, max_results=max_results))
    cached = _cache_get_rows(key, settings)
    if cached is not None:
        return _deserialize_evidence_items(cached)

    url = (
        "http://export.arxiv.org/api/query"
        f"?search_query=all:{quote_plus(query)}&start=0&max_results={max_results}"
    )
    feed = feedparser.parse(url)
    items: list[EvidenceItem] = []
    for entry in feed.entries:
        authors = [a.name for a in getattr(entry, "authors", [])]
        item = EvidenceItem(
            id="",
            source_type="paper",
            retrieval_method="arxiv_search",
            title=entry.title,
            url=entry.link,
            abstract_or_snippet=(entry.summary or "")[:4000],
            venue="arXiv",
            year=int(entry.published[:4]) if getattr(entry, "published", None) else None,
            authors=authors,
            raw={"id": getattr(entry, "id", None)},
        )
        item.score = score_evidence(item, query)
        items.append(item)
    ttl = TTL_EMPTY_SHORT_SEC if not items else TTL_PAPER_QUERY_SEC
    _cache_set_rows(key, _serialize_evidence_items(items), ttl, settings)
    return items


def fetch_page_metadata(url: str, *, cache_settings: CacheSettings | None = None) -> EvidenceItem | None:
    settings = cache_settings or CacheSettings()
    normalized_url = normalize_url_for_cache(url)
    key = cache_key("fetch_page_metadata", _base_cache_payload(url=normalized_url))
    if should_read_cache(settings):
        cached = get_cache(settings.cache_dir).get(key)
        if cached is not None:
            return EvidenceItem.model_validate(cached) if cached else None

    r = http_get(url, headers={"Accept": "text/html,application/xhtml+xml"}, timeout=30)
    ctype = r.headers.get("content-type", "")
    if "html" not in ctype:
        _cache_set_optional_row(key, None, TTL_EMPTY_SHORT_SEC, settings)
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    def first_meta(*names: str) -> str | None:
        for n in names:
            tag = soup.find("meta", attrs={"name": n}) or soup.find("meta", attrs={"property": n})
            if tag and tag.get("content"):
                return tag["content"].strip()
        return None

    title = (
        first_meta("citation_title", "dc.title", "og:title")
        or (soup.title.string.strip() if soup.title and soup.title.string else None)
        or ""
    )
    doi = normalize_doi(first_meta("citation_doi", "dc.identifier", "dc.Identifier")) or extract_doi_from_text(r.text)
    abstract = first_meta("description", "og:description", "citation_abstract") or ""
    venue = first_meta("citation_journal_title", "dc.source")
    year = None
    date_text = first_meta("citation_publication_date", "dc.date", "article:published_time")
    if date_text:
        m = re.search(r"(19|20)\d{2}", date_text)
        if m:
            year = int(m.group(0))
    authors = [t.get("content", "").strip() for t in soup.find_all("meta", attrs={"name": "citation_author"}) if t.get("content")]

    item = EvidenceItem(
        id="",
        source_type="seed_url",
        retrieval_method="direct_url_meta",
        title=title,
        url=url,
        doi=doi,
        abstract_or_snippet=abstract[:4000],
        venue=venue,
        year=year,
        authors=authors,
        raw={},
    )
    item.score = score_evidence(item)
    out = item if item.title else None
    ttl = TTL_PAGE_METADATA_SEC if out else TTL_EMPTY_SHORT_SEC
    _cache_set_optional_row(key, out.model_dump(mode="json") if out else None, ttl, settings)
    return out


def retrieve_scholarly_by_url(url: str, *, cache_settings: CacheSettings | None = None) -> list[EvidenceItem]:
    settings = cache_settings or CacheSettings()
    out: list[EvidenceItem] = []

    doi = extract_doi_from_url(url)
    if doi:
        for fn in (crossref_lookup_doi, openalex_lookup_doi):
            try:
                item = fn(doi, cache_settings=settings)
            except Exception:
                item = None
            if item:
                out.append(item)

    page_item = None
    try:
        page_item = fetch_page_metadata(url, cache_settings=settings)
    except Exception:
        page_item = None
    if page_item:
        out.append(page_item)

        if page_item.doi and page_item.doi != doi:
            for fn in (crossref_lookup_doi, openalex_lookup_doi):
                try:
                    item = fn(page_item.doi, cache_settings=settings)
                except Exception:
                    item = None
                if item:
                    out.append(item)

        if page_item.title:
            try:
                out.extend(crossref_search_title(page_item.title, rows=3, cache_settings=settings))
            except Exception:
                pass
            try:
                out.extend(openalex_search_title(page_item.title, rows=3, cache_settings=settings))
            except Exception:
                pass

    return dedupe_evidence(out)


def retrieve_scholarly_by_query(query: str, *, cache_settings: CacheSettings | None = None) -> list[EvidenceItem]:
    settings = cache_settings or CacheSettings()
    out: list[EvidenceItem] = []
    try:
        out.extend(crossref_search_title(query, rows=5, cache_settings=settings))
    except Exception:
        pass
    try:
        out.extend(openalex_search_title(query, rows=5, cache_settings=settings))
    except Exception:
        pass
    try:
        out.extend(arxiv_search(query, max_results=5, cache_settings=settings))
    except Exception:
        pass
    return dedupe_evidence(out)


def collect_evidence_for_queries(
    plan: PlanOut,
    cache_settings: CacheSettings | None = None,
) -> list[EvidenceItem]:
    """Incremental retrieval: run plan web + paper queries only.

    Use this for gap-fill passes where seed URLs were already fetched on the
    initial retrieval and should not be re-requested.
    """
    import sys

    settings = cache_settings or CacheSettings()
    key = cache_key(
        "collect_evidence_for_queries",
        _base_cache_payload(
            web_queries=plan.web_queries,
            paper_queries=plan.paper_queries,
        ),
    )
    stale_key = f"{key}:stale"
    cache = get_cache(settings.cache_dir)
    stale_before = cache.get(stale_key)
    if settings.mode == "off":
        print("cache off: collect_evidence_for_queries", file=sys.stderr)
    elif settings.mode == "refresh":
        print("cache refresh: collect_evidence_for_queries", file=sys.stderr)
    else:
        cached = cache.get(key)
        if cached is not None:
            print("cache hit: collect_evidence_for_queries", file=sys.stderr)
            return _deserialize_evidence_items(cached)
        print("cache miss: collect_evidence_for_queries", file=sys.stderr)

    evidence: list[EvidenceItem] = []
    had_failure = False

    for q in plan.web_queries:
        try:
            evidence.extend(tavily_search(q, max_results=5, cache_settings=settings))
        except Exception as e:
            had_failure = True
            print(f"[warn] tavily query failed: {q}: {e}", file=sys.stderr)

    for q in plan.paper_queries:
        try:
            evidence.extend(retrieve_scholarly_by_query(q, cache_settings=settings))
        except Exception as e:
            had_failure = True
            print(f"[warn] paper query failed: {q}: {e}", file=sys.stderr)

    merged = dedupe_evidence(evidence)
    rows = _serialize_evidence_items(merged)
    if should_write_cache(settings) and not had_failure:
        cache.set(key, rows, expire=TTL_AGGREGATE_SEC)
        cache.set(stale_key, {"rows": rows, "stored_at": datetime.now(timezone.utc).isoformat()})
    if had_failure and settings.mode == "default":
        stale = stale_before
        if stale and isinstance(stale, dict) and isinstance(stale.get("rows"), list):
            print("cache stale_fallback: collect_evidence_for_queries", file=sys.stderr)
            return _deserialize_evidence_items(stale["rows"])
    return merged


def collect_evidence_for_plan(
    plan: PlanOut,
    input_vars: InputVars,
    cache_settings: CacheSettings | None = None,
) -> list[EvidenceItem]:
    """Initial retrieval: fetch seed URLs from ``input_vars`` then run plan queries."""
    import sys

    settings = cache_settings or CacheSettings()
    normalized_urls = [normalize_url_for_cache(url) for url in input_vars.source_urls]
    key = cache_key(
        "collect_evidence_for_plan",
        _base_cache_payload(
            topic=input_vars.topic,
            company=input_vars.company,
            region=input_vars.region,
            source_urls=normalized_urls,
            web_queries=plan.web_queries,
            paper_queries=plan.paper_queries,
        ),
    )
    stale_key = f"{key}:stale"
    cache = get_cache(settings.cache_dir)
    stale_before = cache.get(stale_key)
    if settings.mode == "off":
        print("cache off: collect_evidence_for_plan", file=sys.stderr)
    elif settings.mode == "refresh":
        print("cache refresh: collect_evidence_for_plan", file=sys.stderr)
    else:
        cached = cache.get(key)
        if cached is not None:
            print("cache hit: collect_evidence_for_plan", file=sys.stderr)
            return _deserialize_evidence_items(cached)
        print("cache miss: collect_evidence_for_plan", file=sys.stderr)

    evidence: list[EvidenceItem] = []
    had_failure = False

    for url in input_vars.source_urls:
        try:
            evidence.extend(retrieve_scholarly_by_url(url, cache_settings=settings))
        except Exception as e:
            had_failure = True
            print(f"[warn] seed URL retrieval failed for {url}: {e}", file=sys.stderr)

    evidence.extend(collect_evidence_for_queries(plan, cache_settings=settings))
    merged = dedupe_evidence(evidence)
    rows = _serialize_evidence_items(merged)
    if should_write_cache(settings) and not had_failure:
        cache.set(key, rows, expire=TTL_AGGREGATE_SEC)
        cache.set(stale_key, {"rows": rows, "stored_at": datetime.now(timezone.utc).isoformat()})
    if had_failure and settings.mode == "default":
        stale = stale_before
        if stale and isinstance(stale, dict) and isinstance(stale.get("rows"), list):
            print("cache stale_fallback: collect_evidence_for_plan", file=sys.stderr)
            return _deserialize_evidence_items(stale["rows"])
    return merged
