from __future__ import annotations

import pytest

from research_agent.agent.questionnaire import compute_coverage
from research_agent.contracts.core.questionnaire import QuestionAnswer, SkippedQuestion


def test_coverage_ratio_answered_over_applicable() -> None:
    skipped = [
        SkippedQuestion(question_id="na", applicable=False, skip_reason="not_applicable:x"),
    ]
    responses = [
        QuestionAnswer(question_id="a", status="answered", answer_markdown="x"),
        QuestionAnswer(question_id="b", status="insufficient_evidence", answer_markdown=""),
        QuestionAnswer(question_id="c", status="partial", answer_markdown="y"),
    ]
    cov = compute_coverage(4, skipped, responses)
    assert cov.total == 4
    assert cov.not_applicable == 1
    assert cov.applicable == 3
    assert cov.answered == 2  # answered + partial
    assert cov.insufficient_evidence == 1
    assert cov.coverage_ratio == pytest.approx(2 / 3)


def test_coverage_zero_applicable() -> None:
    skipped = [
        SkippedQuestion(question_id="q1", applicable=False, skip_reason="x"),
        SkippedQuestion(question_id="q2", applicable=False, skip_reason="y"),
    ]
    cov = compute_coverage(2, skipped, [])
    assert cov.applicable == 0
    assert cov.coverage_ratio == 0.0
