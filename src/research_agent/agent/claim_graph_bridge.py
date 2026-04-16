from __future__ import annotations

from typing import Any

from research_agent.agent.schemas import EvidenceItem
from research_agent.contracts.core.claim_graph import EvidenceRecord, EvidenceSourceKind


def evidence_source_kind(item: EvidenceItem) -> EvidenceSourceKind:
    if item.source_type == "paper":
        return "paper"
    return "web"


def evidence_items_to_records(items: list[EvidenceItem], *, execution_id: str) -> list[EvidenceRecord]:
    """Map retrieval `EvidenceItem` rows into contract `EvidenceRecord` for claim-graph merge."""
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
                source_kind=evidence_source_kind(item),
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
