"""Unit tests for the diff/scoring engine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tulkki.diff import compare
from tulkki.types import ExtractedDoc, FetchResult, Heading


def _doc(words: int, headings: list[Heading] | None = None) -> ExtractedDoc:
    return ExtractedDoc(
        title="t",
        markdown="# t\n\nbody " * words,
        headings=tuple(headings or []),
        word_count=words,
    )


def _fetch(html: str = "<html></html>", backend: str = "test") -> FetchResult:
    return FetchResult(
        url="https://example.com",
        html=html,
        status_code=200,
        bytes_size=len(html.encode("utf-8")),
        fetched_at=datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc),
        elapsed_ms=10,
        backend=backend,
    )


def test_identical_docs_score_one() -> None:
    doc = _doc(100, [Heading(1, "Hello"), Heading(2, "World")])
    report = compare(_fetch(), _fetch(), doc, doc)
    assert report.visibility_score == 1.0
    assert report.missing_headings == ()


def test_pure_word_loss_no_headings() -> None:
    ai = _doc(50)
    human = _doc(100)
    report = compare(_fetch(), _fetch(), ai, human)
    # No headings on the human side -> falls back to pure word coverage
    assert report.visibility_score == pytest.approx(0.5)


def test_structural_blindness_anthropic_pattern() -> None:
    """Anthropic-docs case: AI sees the words but none of the headings.

    word coverage = min(1.0, 375/337) = 1.0
    heading coverage = 0/5 = 0.0
    score = 0.7 * 1.0 + 0.3 * 0.0 = 0.7
    """
    ai = _doc(375)  # AI sees more words but no headings
    human = _doc(
        337,
        [
            Heading(1, "Intro"),
            Heading(2, "Setup"),
            Heading(2, "Capabilities"),
            Heading(2, "Examples"),
            Heading(2, "Support"),
        ],
    )
    report = compare(_fetch(), _fetch(), ai, human)
    assert report.visibility_score == pytest.approx(0.7)
    assert len(report.missing_headings) == 5


def test_partial_heading_match() -> None:
    """Half the headings present should mean ~85% (0.7*1 + 0.3*0.5)."""
    common = [Heading(2, "A"), Heading(2, "B")]
    ai = _doc(100, common)
    human = _doc(100, common + [Heading(2, "C"), Heading(2, "D")])
    report = compare(_fetch(), _fetch(), ai, human)
    assert report.visibility_score == pytest.approx(0.85)
    missing_texts = {h.text for h in report.missing_headings}
    assert missing_texts == {"C", "D"}


def test_zero_human_words_means_zero_score_unless_ai_also_empty() -> None:
    empty_human = _doc(0)
    empty_ai = _doc(0)
    nonempty_ai = _doc(50)
    assert compare(_fetch(), _fetch(), empty_ai, empty_human).visibility_score == 1.0
    assert (
        compare(_fetch(), _fetch(), nonempty_ai, empty_human).visibility_score == 0.0
    )


def test_score_clamps_at_one_when_ai_overshoots() -> None:
    """If raw HTML extracts more words than rendered, score caps at 1.0,
    not >1.0. Real-world case: Next.js docs where raw ships extra
    boilerplate text the rendered DOM strips."""
    ai = _doc(500)
    human = _doc(300)
    report = compare(_fetch(), _fetch(), ai, human)
    assert report.visibility_score == pytest.approx(1.0)


def test_repeated_headings_do_not_penalise_score() -> None:
    """Real-world case from the OpenAI Codex page: a page legitimately
    repeats the same h3 heading ('Anecdotes from our teams') 4 times for
    different sections. Both views see the same 5 list items / 2 unique
    headings, and the score should be 100 % — not 82 %, which is what an
    earlier version of the algorithm produced by dividing matched-unique
    by total-list-length."""
    headings = [
        Heading(1, "How OpenAI uses Codex"),
        Heading(3, "Anecdotes from our teams"),
        Heading(3, "Anecdotes from our teams"),
        Heading(3, "Anecdotes from our teams"),
        Heading(3, "Anecdotes from our teams"),
    ]
    ai = _doc(1468, headings)
    human = _doc(1468, headings)
    report = compare(_fetch(), _fetch(), ai, human)
    assert report.visibility_score == pytest.approx(1.0)
    assert report.missing_headings == ()


def test_missing_headings_are_deduplicated() -> None:
    """A heading that repeats on the human side must only appear once in
    `missing_headings`, and only if the AI side does not see it at all.
    This keeps the report consistent with `_heading_coverage`, which also
    operates on the deduplicated set."""
    human_headings = [
        Heading(1, "Main"),
        Heading(2, "Repeated"),
        Heading(2, "Repeated"),
        Heading(2, "Repeated"),
        Heading(2, "Unique"),
    ]
    # AI sees only the h1
    ai = _doc(100, [Heading(1, "Main")])
    human = _doc(100, human_headings)
    report = compare(_fetch(), _fetch(), ai, human)

    # Two unique headings are missing, not four
    assert len(report.missing_headings) == 2
    missing_texts = [h.text for h in report.missing_headings]
    assert missing_texts == ["Repeated", "Unique"]
