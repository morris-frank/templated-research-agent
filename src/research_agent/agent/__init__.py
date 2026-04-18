"""LLM research loop, schemas, and claim-graph bridging from retrieval evidence.

Attributes are loaded lazily so ``import research_agent.agent.questionnaire`` does not
pull in ``research`` / ``llm`` until ``ResearchAgent`` (or other exports) is accessed.
"""

from __future__ import annotations

__all__ = ["ResearchAgent", "EvidenceItem", "FinalReport", "InputVars"]


def __getattr__(name: str):
    if name == "ResearchAgent":
        from research_agent.agent.research import ResearchAgent

        return ResearchAgent
    if name == "EvidenceItem":
        from research_agent.agent.schemas import EvidenceItem

        return EvidenceItem
    if name == "FinalReport":
        from research_agent.agent.schemas import FinalReport

        return FinalReport
    if name == "InputVars":
        from research_agent.agent.schemas import InputVars

        return InputVars
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
