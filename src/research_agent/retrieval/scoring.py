from __future__ import annotations

import re
from typing import Iterable

from research_agent.types import EvidenceItem


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


def assign_evidence_ids(items: list[EvidenceItem]) -> list[EvidenceItem]:
    assigned: list[EvidenceItem] = []
    for idx, item in enumerate(items, start=1):
        assigned.append(item.model_copy(update={"id": f"E{idx:03d}"}))
    return assigned


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
