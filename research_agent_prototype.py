#!/usr/bin/env python3
"""
Single-file prototype: template-constrained research agent.

What it does
------------
- Takes a task prompt, input variables, and a target JSON schema (via Pydantic model)
- Plans subquestions + retrieval queries with an LLM
- Retrieves evidence from:
  * Tavily (web/current information)
  * Crossref (DOI/title metadata)
  * OpenAlex (DOI/title scholarly metadata)
  * arXiv (preprints)
  * direct scholarly URL fetch + metadata extraction fallback
- Iteratively drafts structured output and evaluates it against the schema
- Stops when the schema validates and required sections are populated, or after N iterations

Why this retrieval stack
------------------------
DOI-centric APIs alone are too narrow for institutional outputs and mixed publisher pages.
This prototype therefore uses a scholarly resolution cascade:
    DOI/URL -> Crossref/OpenAlex -> title search -> direct page metadata extraction.
That makes direct URLs such as MDPI, Science/AAAS DOI landing pages, and institutional
repository/report pages much more likely to be findable in one pass.

Environment
-----------
Required:
  OPENAI_API_KEY
  TAVILY_API_KEY
Optional:
  OPENAI_MODEL=gpt-5.4-mini
  OPENAI_BASE_URL=...
  OPENAI_ORG=...

Install:
  pip install openai requests pydantic beautifulsoup4 feedparser

Run:
  python research_agent_prototype.py --demo
  python research_agent_prototype.py --task-file task.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal
from urllib.parse import quote_plus, unquote, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

_REPO_ROOT = Path(__file__).resolve().parent
_CONTRACTS_ROOT = _REPO_ROOT / "contracts_lib_example"
if _CONTRACTS_ROOT.is_dir():
    sys.path.insert(0, str(_CONTRACTS_ROOT))

from contracts.core.claim_graph import (  # type: ignore[import-untyped]
    ClaimGraphDraft,
    EvidenceRecord,
    EvidenceSourceKind,
    ExecutionContext,
    merge_claim_graph,
    validate_claim_graph,
)

# -----------------------------
# Contracts
# -----------------------------


class InputVars(BaseModel):
    company: str | None = None
    topic: str
    region: str | None = None
    source_urls: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    id: str
    source_type: Literal["web", "paper", "seed_url"]
    retrieval_method: str
    title: str
    url: str
    doi: str | None = None
    abstract_or_snippet: str = ""
    venue: str | None = None
    year: int | None = None
    authors: list[str] = Field(default_factory=list)
    score: float = 0.0
    supports: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class Claim(BaseModel):
    text: str
    evidence_ids: list[str] = Field(min_length=1)
    evidence_urls: list[str] = Field(default_factory=list)
    support: Literal["direct", "partial", "contextual"] = "direct"
    notes: str | None = None


class FinalReport(BaseModel):
    summary: str
    key_findings: list[Claim]
    scientific_evidence: list[Claim]
    market_context: list[Claim]
    open_questions: list[str]
    confidence: Literal["low", "medium", "high"]


def _evidence_source_kind(item: EvidenceItem) -> EvidenceSourceKind:
    if item.source_type == "paper":
        return "paper"
    return "web"


def evidence_items_to_records(items: list[EvidenceItem], *, execution_id: str) -> list[EvidenceRecord]:
    out: list[EvidenceRecord] = []
    for item in items:
        prov: dict[str, Any] = {
            "retrieval_method": item.retrieval_method,
            "source_type": item.source_type,
        }
        if item.venue:
            prov["venue"] = item.venue
        if item.doi:
            prov["doi"] = item.doi
        out.append(
            EvidenceRecord(
                evidence_id=item.id,
                source_kind=_evidence_source_kind(item),
                title=item.title or None,
                locator=item.url or f"urn:evidence:{item.id}",
                excerpt=(item.abstract_or_snippet or None) if item.abstract_or_snippet else None,
                structured_value=None,
                provenance=prov,
                execution_context_id=execution_id,
                authority_score=item.score,
            )
        )
    return out


# -----------------------------
# Model client
# -----------------------------


class LLMClient:
    def __init__(self, model: str | None = None):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required")

        kwargs: dict[str, Any] = {"api_key": api_key}
        if os.environ.get("OPENAI_BASE_URL"):
            kwargs["base_url"] = os.environ["OPENAI_BASE_URL"]
        if os.environ.get("OPENAI_ORG"):
            kwargs["organization"] = os.environ["OPENAI_ORG"]

        self.client = OpenAI(**kwargs)
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")

    def json_response(self, *, system: str, user_payload: dict[str, Any], schema_model: type[BaseModel]) -> dict[str, Any]:
        schema = schema_model.model_json_schema()
        resp = self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": system}]},
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": json.dumps(user_payload, ensure_ascii=False)}],
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema_model.__name__,
                    "schema": schema,
                    "strict": True,
                }
            },
        )
        return json.loads(resp.output_text)


# -----------------------------
# Planner / gap query schemas
# -----------------------------


class PlanOut(BaseModel):
    subquestions: list[str]
    web_queries: list[str]
    paper_queries: list[str]
    evidence_requirements: list[str]


class GapQueries(BaseModel):
    web_queries: list[str] = Field(default_factory=list)
    paper_queries: list[str] = Field(default_factory=list)


# -----------------------------
# Retrieval helpers
# -----------------------------


USER_AGENT = "research-agent-prototype/0.1 (mailto:example@example.com)"
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


def _http_get(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 30) -> requests.Response:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json,text/html,application/xml;q=0.9,*/*;q=0.8"}
    if headers:
        hdrs.update(headers)
    r = requests.get(url, params=params, headers=hdrs, timeout=timeout)
    r.raise_for_status()
    return r


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    value = value.replace("https://doi.org/", "").replace("http://doi.org/", "")
    value = value.replace("https://dx.doi.org/", "").replace("http://dx.doi.org/", "")
    m = DOI_RE.search(value)
    return m.group(0).lower() if m else None


def extract_doi_from_text(text: str | None) -> str | None:
    if not text:
        return None
    m = DOI_RE.search(text)
    return m.group(0).lower() if m else None


def extract_doi_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc.endswith("doi.org"):
        return normalize_doi(unquote(parsed.path.lstrip("/")))
    return extract_doi_from_text(unquote(url))


def score_evidence(item: EvidenceItem, query: str | None = None) -> float:
    score = 0.0
    if item.source_type == "paper":
        score += 3.0
    if item.doi:
        score += 2.0
    if item.year:
        score += max(0.0, 1.0 - max(0, 2026 - item.year) * 0.05)
    if item.abstract_or_snippet:
        score += min(1.0, len(item.abstract_or_snippet) / 1200.0)
    title_l = item.title.lower()
    if query:
        q_tokens = {t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2}
        overlap = sum(1 for t in q_tokens if t in title_l)
        score += min(2.0, overlap * 0.25)
    return round(score, 4)


def dedupe_evidence(items: Iterable[EvidenceItem]) -> list[EvidenceItem]:
    out: list[EvidenceItem] = []
    seen: set[str] = set()
    for item in items:
        key = item.doi or item.url or item.title.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    out.sort(key=lambda x: (x.score, x.year or 0, len(x.abstract_or_snippet)), reverse=True)
    return assign_evidence_ids(out)


def assign_evidence_ids(items: list[EvidenceItem]) -> list[EvidenceItem]:
    assigned: list[EvidenceItem] = []
    for idx, item in enumerate(items, start=1):
        assigned.append(item.model_copy(update={"id": f"E{idx:03d}"}))
    return assigned


def claim_lists(report: FinalReport) -> list[tuple[str, Claim]]:
    out: list[tuple[str, Claim]] = []
    for section_name in ("key_findings", "scientific_evidence", "market_context"):
        for claim in getattr(report, section_name):
            out.append((section_name, claim))
    return out


# -----------------------------
# Retrieval backends
# -----------------------------


def tavily_search(query: str, max_results: int = 5) -> list[EvidenceItem]:
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is required")

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
    return results


def crossref_lookup_doi(doi: str) -> EvidenceItem | None:
    url = f"https://api.crossref.org/works/{quote_plus(doi)}"
    r = _http_get(url)
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
    return item if item.title else None


def crossref_search_title(title: str, rows: int = 5) -> list[EvidenceItem]:
    r = _http_get(
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
    return items


def openalex_lookup_doi(doi: str) -> EvidenceItem | None:
    doi_url = f"https://doi.org/{doi}"
    r = _http_get("https://api.openalex.org/works", params={"filter": f"doi:{doi_url}", "per-page": 1})
    rows = r.json().get("results", [])
    if not rows:
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
    return item if item.title else None


def openalex_search_title(title: str, rows: int = 5) -> list[EvidenceItem]:
    r = _http_get("https://api.openalex.org/works", params={"search": title, "per-page": rows})
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
    return out


def arxiv_search(query: str, max_results: int = 5) -> list[EvidenceItem]:
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
    return items


def fetch_page_metadata(url: str) -> EvidenceItem | None:
    r = _http_get(url, headers={"Accept": "text/html,application/xhtml+xml"}, timeout=30)
    ctype = r.headers.get("content-type", "")
    if "html" not in ctype:
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
    return item if item.title else None


def retrieve_scholarly_by_url(url: str) -> list[EvidenceItem]:
    out: list[EvidenceItem] = []

    # 1) direct DOI in URL
    doi = extract_doi_from_url(url)
    if doi:
        for fn in (crossref_lookup_doi, openalex_lookup_doi):
            try:
                item = fn(doi)
            except Exception:
                item = None
            if item:
                out.append(item)

    # 2) page metadata
    page_item = None
    try:
        page_item = fetch_page_metadata(url)
    except Exception:
        page_item = None
    if page_item:
        out.append(page_item)

        # 3) DOI discovered in page metadata / HTML
        if page_item.doi and page_item.doi != doi:
            for fn in (crossref_lookup_doi, openalex_lookup_doi):
                try:
                    item = fn(page_item.doi)
                except Exception:
                    item = None
                if item:
                    out.append(item)

        # 4) title-based search fallback
        if page_item.title:
            try:
                out.extend(crossref_search_title(page_item.title, rows=3))
            except Exception:
                pass
            try:
                out.extend(openalex_search_title(page_item.title, rows=3))
            except Exception:
                pass

    return dedupe_evidence(out)


def retrieve_scholarly_by_query(query: str) -> list[EvidenceItem]:
    out: list[EvidenceItem] = []
    try:
        out.extend(crossref_search_title(query, rows=5))
    except Exception:
        pass
    try:
        out.extend(openalex_search_title(query, rows=5))
    except Exception:
        pass
    try:
        out.extend(arxiv_search(query, max_results=5))
    except Exception:
        pass
    return dedupe_evidence(out)


# -----------------------------
# Agent
# -----------------------------


@dataclass
class ResearchAgent:
    llm: LLMClient
    max_iterations: int = 3
    top_k_evidence: int = 25

    def plan(self, task_prompt: str, input_vars: dict[str, Any], target_schema: dict[str, Any]) -> PlanOut:
        payload = {
            "task_prompt": task_prompt,
            "input_vars": input_vars,
            "target_schema": target_schema,
            "instructions": [
                "Decompose the task into concrete subquestions.",
                "Produce web queries for current/general web search.",
                "Produce paper queries for scholarly databases.",
                "Prefer queries that can be resolved via DOI/title search when likely scholarly.",
            ],
        }
        out = self.llm.json_response(
            system=(
                "You are planning a bounded research workflow. Output only the JSON object matching the schema. "
                "Do not answer the task; only produce the research plan."
            ),
            user_payload=payload,
            schema_model=PlanOut,
        )
        return PlanOut.model_validate(out)

    def draft(self, task_prompt: str, input_vars: dict[str, Any], evidence: list[EvidenceItem]) -> dict[str, Any]:
        payload = {
            "task_prompt": task_prompt,
            "input_vars": input_vars,
            "evidence": [e.model_dump() for e in evidence[: self.top_k_evidence]],
            "instructions": [
                "Return JSON only.",
                "Use only supported claims from evidence.",
                "For every claim in key_findings, scientific_evidence, and market_context, include evidence_ids referencing the provided evidence items.",
                "Populate evidence_urls for each claim using the URLs corresponding to the cited evidence_ids.",
                "Use support='direct' when the cited evidence directly supports the claim; otherwise use 'partial' or 'contextual'.",
                "If evidence is weak or conflicting, reflect that in open_questions and confidence.",
                "Do not invent citations or facts not grounded in evidence.",
            ],
        }
        return self.llm.json_response(
            system="You synthesize retrieved evidence into the target report schema with explicit claim-level evidence linking.",
            user_payload=payload,
            schema_model=FinalReport,
        )

    def draft_claim_graph(
        self, task_prompt: str, input_vars: dict[str, Any], evidence: list[EvidenceItem]
    ) -> dict[str, Any]:
        payload = {
            "task_prompt": task_prompt,
            "input_vars": input_vars,
            "evidence": [e.model_dump() for e in evidence[: self.top_k_evidence]],
            "instructions": [
                "Return JSON only matching ClaimGraphDraft.",
                "Emit claims, claim_evidence_links, claim_dependency_links, and output (FinalProjection). Do not write long prose sections.",
                "Every claim needs claim_id (stable string), text, claim_kind, scope dict, confidence, status.",
                "Use claim_evidence_links only with evidence_id values from the provided evidence list.",
                "Use relation direct_support when the evidence itself states or measures the claim; indirect_support when it requires interpretation.",
                "Recommendations (claim_kind recommendation) should usually depend_on or be motivated by observation/inference claims via claim_dependency_links.",
                "output.summary_claim_refs and insight items must reference existing claim_id values.",
                "For RecommendationItem, rationale_claim_refs point to recommendation claims; dependency_claim_refs point to supporting observation/inference claims.",
                "If the task has no quantitative soil/lab metrics in evidence, avoid numeric literals in claim text (status contested or qualitative wording).",
            ],
        }
        return self.llm.json_response(
            system=(
                "You build a structured claim graph: claims, evidence links, claim dependencies, and a final projection. "
                "Ground every link in the supplied evidence IDs."
            ),
            user_payload=payload,
            schema_model=ClaimGraphDraft,
        )

    def evaluate(self, draft: dict[str, Any], evidence: list[EvidenceItem]) -> tuple[bool, list[str]]:
        missing: list[str] = []
        try:
            report = FinalReport.model_validate(draft)
        except ValidationError as e:
            return False, [f"schema_validation_failed: {e}"]

        if not report.summary.strip():
            missing.append("summary")
        if not report.key_findings:
            missing.append("key_findings")
        if not report.scientific_evidence:
            missing.append("scientific_evidence")
        if not report.market_context:
            missing.append("market_context")

        evidence_by_id = {e.id: e for e in evidence}
        for section_name, claim in claim_lists(report):
            if not claim.text.strip():
                missing.append(f"{section_name}:empty_claim_text")
                continue
            if not claim.evidence_ids:
                missing.append(f"{section_name}:claim_without_evidence_ids:{claim.text[:80]}")
                continue
            resolved_urls = []
            for eid in claim.evidence_ids:
                item = evidence_by_id.get(eid)
                if item is None:
                    missing.append(f"{section_name}:unknown_evidence_id:{eid}")
                    continue
                resolved_urls.append(item.url)
            if claim.evidence_urls and sorted(set(claim.evidence_urls)) != sorted(set(resolved_urls)):
                missing.append(f"{section_name}:evidence_url_mismatch:{claim.text[:80]}")
            if not resolved_urls:
                missing.append(f"{section_name}:claim_without_resolved_evidence:{claim.text[:80]}")
            paper_only = section_name == "scientific_evidence"
            if paper_only and not any(evidence_by_id[eid].source_type == "paper" for eid in claim.evidence_ids if eid in evidence_by_id):
                missing.append(f"{section_name}:requires_paper_evidence:{claim.text[:80]}")

        return (len(missing) == 0), missing

    def evaluate_claim_graph(
        self, draft: dict[str, Any], evidence: list[EvidenceItem], execution_context: ExecutionContext
    ) -> tuple[bool, list[str]]:
        try:
            graph_draft = ClaimGraphDraft.model_validate(draft)
        except ValidationError as e:
            return False, [f"claim_graph_schema_validation_failed: {e}"]

        records = evidence_items_to_records(evidence, execution_id=execution_context.execution_id)
        bundle = merge_claim_graph(graph_draft, [execution_context], records)
        errors = validate_claim_graph(bundle)
        return (len(errors) == 0), errors

    def gap_queries(self, task_prompt: str, input_vars: dict[str, Any], missing_requirements: list[str], evidence: list[EvidenceItem]) -> GapQueries:
        payload = {
            "task_prompt": task_prompt,
            "input_vars": input_vars,
            "missing_requirements": missing_requirements,
            "evidence_titles": [e.title for e in evidence[:15]],
            "evidence_venues": [e.venue for e in evidence[:15] if e.venue],
        }
        out = self.llm.json_response(
            system=(
                "Generate only the minimum incremental research queries needed to fill the missing requirements. "
                "Output only the JSON object matching the schema."
            ),
            user_payload=payload,
            schema_model=GapQueries,
        )
        return GapQueries.model_validate(out)

    def collect_evidence(self, plan: PlanOut, input_vars: InputVars) -> list[EvidenceItem]:
        evidence: list[EvidenceItem] = []

        # Seed URL ingestion first. This is what makes the provided examples directly findable.
        for url in input_vars.source_urls:
            try:
                evidence.extend(retrieve_scholarly_by_url(url))
            except Exception as e:
                print(f"[warn] seed URL retrieval failed for {url}: {e}", file=sys.stderr)

        # Web
        for q in plan.web_queries:
            try:
                evidence.extend(tavily_search(q, max_results=5))
            except Exception as e:
                print(f"[warn] tavily query failed: {q}: {e}", file=sys.stderr)

        # Scholarly
        for q in plan.paper_queries:
            try:
                evidence.extend(retrieve_scholarly_by_query(q))
            except Exception as e:
                print(f"[warn] paper query failed: {q}: {e}", file=sys.stderr)

        return dedupe_evidence(evidence)

    def run_claim_graph(self, task_prompt: str, input_vars: InputVars) -> dict[str, Any]:
        if not _CONTRACTS_ROOT.is_dir():
            raise RuntimeError(f"contracts_lib_example not found at {_CONTRACTS_ROOT}; cannot run claim-graph mode")

        run_tag = uuid.uuid4().hex[:12]
        execution_context = ExecutionContext(
            execution_id=f"exec-retrieval-{run_tag}",
            pipeline_kind="retrieval",
            pipeline_version="research-agent-prototype",
            run_at=datetime.now(timezone.utc),
            parameters=input_vars.model_dump(),
        )

        target_schema = ClaimGraphDraft.model_json_schema()
        plan = self.plan(task_prompt, input_vars.model_dump(), target_schema)
        evidence = self.collect_evidence(plan, input_vars)

        if not evidence:
            raise RuntimeError("No evidence retrieved; aborting")

        last_draft: dict[str, Any] | None = None
        for iteration in range(self.max_iterations):
            draft = self.draft_claim_graph(task_prompt, input_vars.model_dump(), evidence)
            ok, errors = self.evaluate_claim_graph(draft, evidence, execution_context)
            last_draft = draft
            if ok:
                graph_draft = ClaimGraphDraft.model_validate(draft)
                records = evidence_items_to_records(evidence, execution_id=execution_context.execution_id)
                bundle = merge_claim_graph(graph_draft, [execution_context], records)
                return {
                    "plan": plan.model_dump(),
                    "evidence": [e.model_dump() for e in evidence[: self.top_k_evidence]],
                    "claim_graph": bundle.model_dump(mode="json"),
                    "validation_errors": [],
                    "iterations": iteration + 1,
                }

            gap = self.gap_queries(task_prompt, input_vars.model_dump(), errors, evidence)
            if not gap.web_queries and not gap.paper_queries:
                break

            incr_plan = PlanOut(
                subquestions=plan.subquestions,
                web_queries=gap.web_queries,
                paper_queries=gap.paper_queries,
                evidence_requirements=plan.evidence_requirements,
            )
            new_evidence = self.collect_evidence(incr_plan, InputVars(topic=input_vars.topic, source_urls=[]))
            evidence = dedupe_evidence(evidence + new_evidence)
            time.sleep(0.5)

        graph_draft = ClaimGraphDraft.model_validate(last_draft) if last_draft else None
        records = evidence_items_to_records(evidence, execution_id=execution_context.execution_id)
        bundle_dump = None
        if graph_draft:
            bundle = merge_claim_graph(graph_draft, [execution_context], records)
            bundle_dump = bundle.model_dump(mode="json")
        return {
            "plan": plan.model_dump(),
            "evidence": [e.model_dump() for e in evidence[: self.top_k_evidence]],
            "claim_graph": bundle_dump,
            "validation_errors": validate_claim_graph(
                merge_claim_graph(ClaimGraphDraft.model_validate(last_draft), [execution_context], records)
            )
            if last_draft
            else ["no_draft"],
            "iterations": self.max_iterations,
            "warning": "Returned best-effort claim graph; deterministic validation still failing.",
        }

    def run(self, task_prompt: str, input_vars: InputVars) -> dict[str, Any]:
        target_schema = FinalReport.model_json_schema()
        plan = self.plan(task_prompt, input_vars.model_dump(), target_schema)
        evidence = self.collect_evidence(plan, input_vars)

        if not evidence:
            raise RuntimeError("No evidence retrieved; aborting")

        last_draft: dict[str, Any] | None = None
        for iteration in range(self.max_iterations):
            draft = self.draft(task_prompt, input_vars.model_dump(), evidence)
            ok, missing = self.evaluate(draft, evidence)
            last_draft = draft
            if ok:
                return {
                    "plan": plan.model_dump(),
                    "evidence": [e.model_dump() for e in evidence[: self.top_k_evidence]],
                    "final": draft,
                    "iterations": iteration + 1,
                }

            gap = self.gap_queries(task_prompt, input_vars.model_dump(), missing, evidence)
            if not gap.web_queries and not gap.paper_queries:
                break

            incr_plan = PlanOut(
                subquestions=plan.subquestions,
                web_queries=gap.web_queries,
                paper_queries=gap.paper_queries,
                evidence_requirements=plan.evidence_requirements,
            )
            new_evidence = self.collect_evidence(incr_plan, InputVars(topic=input_vars.topic, source_urls=[]))
            evidence = dedupe_evidence(evidence + new_evidence)
            time.sleep(0.5)

        return {
            "plan": plan.model_dump(),
            "evidence": [e.model_dump() for e in evidence[: self.top_k_evidence]],
            "final": last_draft,
            "iterations": self.max_iterations,
            "warning": "Returned best-effort draft; claim-level evidence linking may still be incomplete or weak.",
        }


# -----------------------------
# Demo config
# -----------------------------


def demo_payload() -> tuple[str, InputVars]:
    task_prompt = (
        "Produce a concise structured research brief on cereal metagenomics and soil/arable crop residue context. "
        "Use current web context plus scientific literature. Mention limits explicitly."
    )
    input_vars = InputVars(
        topic="cereal metagenomics and soil microbiome context",
        company="Example AgTech",
        region="EU",
        source_urls=[
            "https://www.mdpi.com/2076-2607/12/3/510",
            "https://www.science.org/doi/10.1126/science.aap9516",
            "https://research.wur.nl/en/publications/reference-values-for-arable-crop-residues-organic-matter-and-cn-r/",
        ],
    )
    return task_prompt, input_vars


# -----------------------------
# CLI
# -----------------------------


def load_task_file(path: str) -> tuple[str, InputVars]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["task_prompt"], InputVars.model_validate(data["input_vars"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="Run the built-in demo payload")
    parser.add_argument("--task-file", type=str, help="Path to JSON file with task_prompt and input_vars")
    parser.add_argument(
        "--claim-graph",
        action="store_true",
        help="Emit and validate ClaimGraphBundle (claims + links + projection) instead of FinalReport",
    )
    args = parser.parse_args()

    if not args.demo and not args.task_file:
        parser.error("Pass --demo or --task-file")

    if args.demo:
        task_prompt, input_vars = demo_payload()
    else:
        task_prompt, input_vars = load_task_file(args.task_file)

    agent = ResearchAgent(llm=LLMClient())
    result = agent.run_claim_graph(task_prompt, input_vars) if args.claim_graph else agent.run(task_prompt, input_vars)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())