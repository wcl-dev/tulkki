"""Unit tests for the raw-bytes presence analysis module."""

from __future__ import annotations

from pathlib import Path

import pytest

from tulkki.raw_presence import (
    FRAMEWORK_SIGNATURES,
    MIN_SENTENCE_CHARS,
    _normalize_haystack,
    _sentences,
    analyze,
)
from tulkki.types import ExtractedDoc, Heading

FIXTURES = Path(__file__).parent / "fixtures"


def _doc(
    markdown: str,
    headings: list[Heading] | None = None,
    word_count: int | None = None,
) -> ExtractedDoc:
    return ExtractedDoc(
        title="test",
        markdown=markdown,
        headings=tuple(headings or []),
        word_count=word_count if word_count is not None else len(markdown.split()),
    )


# Long enough sentences for testing (>= MIN_SENTENCE_CHARS)
SENT_WASH = (
    "Washington, D.C. is the capital city of the United States and ranks "
    "first in AI adoption among all fifty states."
)
SENT_MASS = (
    "Massachusetts ranks second in AI research output with over three "
    "hundred active laboratories and research centers."
)
SENT_CALI = (
    "California leads the nation in AI startup funding with billions of "
    "dollars invested annually in companies."
)


# --- Basic coverage ----------------------------------------------------------


def test_empty_raw_html_non_empty_rendered_returns_zero() -> None:
    doc = _doc(SENT_WASH, word_count=20)
    report = analyze("", doc)
    assert report.sentence_coverage == 0.0


def test_empty_rendered_returns_one() -> None:
    doc = _doc("", word_count=0)
    report = analyze("<html>lots of content here</html>", doc)
    assert report.sentence_coverage == 1.0
    assert report.heading_coverage == 1.0


def test_direct_substring_match() -> None:
    raw_html = f"<html><body><p>{SENT_WASH}</p><p>{SENT_MASS}</p></body></html>"
    md = f"{SENT_WASH}\n\n{SENT_MASS}"
    doc = _doc(md)
    report = analyze(raw_html, doc)
    assert report.sentence_coverage == 1.0
    assert report.sentences_checked == 2
    assert report.sentences_found_in_raw == 2
    assert report.missing_sentences == ()


# --- Normalization tests -----------------------------------------------------


def test_rsc_backslash_escape_match() -> None:
    """Content inside RSC flight data has backslash-escaped quotes.
    The normalizer must unescape them so rendered sentences match."""
    escaped = SENT_WASH.replace('"', '\\"')
    raw_html = f'<script>self.__next_f.push([1,"{escaped}"])</script>'
    doc = _doc(SENT_WASH)
    report = analyze(raw_html, doc)
    assert report.sentence_coverage == 1.0


def test_html_entity_match() -> None:
    """HTML entities like &#39; should match their plain-text equivalents."""
    raw_html = "<p>It&#39;s a beautiful day in Washington and the sun is shining brightly across the entire metropolitan area today.</p>"
    doc = _doc("It's a beautiful day in Washington and the sun is shining brightly across the entire metropolitan area today.")
    report = analyze(raw_html, doc)
    assert report.sentence_coverage == 1.0


def test_whitespace_collapsed_across_nodes() -> None:
    """Whitespace differences between raw HTML and rendered text should not
    prevent matching."""
    raw_html = "<p>Washington,\n    D.C.   is  the  capital  city  of the United States and ranks first in AI adoption among all fifty states.</p>"
    doc = _doc(SENT_WASH)
    report = analyze(raw_html, doc)
    assert report.sentence_coverage == 1.0


def test_case_insensitive() -> None:
    """Matching should be case-insensitive."""
    raw_html = "<p>WASHINGTON, D.C. IS THE CAPITAL CITY OF THE UNITED STATES AND RANKS FIRST IN AI ADOPTION AMONG ALL FIFTY STATES.</p>"
    doc = _doc(SENT_WASH)
    report = analyze(raw_html, doc)
    assert report.sentence_coverage == 1.0


# --- False positive protection -----------------------------------------------


def test_minified_js_noise_does_not_false_positive() -> None:
    """Raw HTML full of minified JS should not cause false positives.
    The sentence we're looking for is NOT in the raw HTML."""
    raw_html = (
        "<html><script>"
        "var a=function(){return!0};var b=function(x){return x+1};"
        "window.addEventListener('load',function(){console.log('ready')});"
        "</script></html>"
    )
    doc = _doc(SENT_WASH, word_count=20)
    report = analyze(raw_html, doc)
    assert report.sentence_coverage == 0.0
    assert len(report.missing_sentences) == 1


def test_short_fragments_dropped() -> None:
    """Fragments shorter than MIN_SENTENCE_CHARS should not be checked."""
    raw_html = "<p>OK. Learn more. Yes.</p>"
    doc = _doc("OK. Learn more. Yes.", word_count=5)
    report = analyze(raw_html, doc)
    # All fragments are too short -> sentences_checked == 0 -> coverage 1.0
    assert report.sentences_checked == 0
    assert report.sentence_coverage == 1.0


# --- Heading tests -----------------------------------------------------------


def test_heading_dedup_before_comparison() -> None:
    """Repeated headings should be deduplicated before checking presence."""
    raw_html = "<html><body>introduction section overview</body></html>"
    headings = [
        Heading(1, "Introduction"),
        Heading(2, "Section"),
        Heading(2, "Section"),
        Heading(2, "Section"),
        Heading(3, "Overview"),
    ]
    doc = _doc("body text", headings=headings, word_count=2)
    report = analyze(raw_html, doc)
    # 3 unique headings, all present (case-insensitive)
    assert report.headings_checked == 3
    assert report.headings_found_in_raw == 3
    assert report.heading_coverage == 1.0
    assert report.missing_headings == ()


def test_heading_missing_from_raw() -> None:
    """Headings not in raw HTML should be reported as missing."""
    raw_html = "<html><body>introduction</body></html>"
    headings = [
        Heading(1, "Introduction"),
        Heading(2, "Completely Absent Section"),
    ]
    doc = _doc("body text", headings=headings, word_count=2)
    report = analyze(raw_html, doc)
    assert report.headings_checked == 2
    assert report.headings_found_in_raw == 1
    assert report.heading_coverage == 0.5
    assert len(report.missing_headings) == 1
    assert report.missing_headings[0].text == "Completely Absent Section"


# --- Framework detection -----------------------------------------------------


def test_framework_detection_nextjs_rsc() -> None:
    raw_html = '<script>self.__next_f.push([1,"data"])</script>'
    doc = _doc("", word_count=0)
    report = analyze(raw_html, doc)
    assert "nextjs-rsc" in report.frameworks_detected


def test_framework_detection_nuxt() -> None:
    raw_html = "<script>window.__NUXT__={data:{}}</script>"
    doc = _doc("", word_count=0)
    report = analyze(raw_html, doc)
    assert "nuxt" in report.frameworks_detected


def test_framework_detection_none() -> None:
    raw_html = "<html><body><p>Plain old HTML</p></body></html>"
    doc = _doc("", word_count=0)
    report = analyze(raw_html, doc)
    assert report.frameworks_detected == ()


def test_multiple_frameworks_detected() -> None:
    raw_html = (
        '<script>self.__next_f.push([1,"x"])</script>'
        '<div data-react-helmet="true"></div>'
    )
    doc = _doc("", word_count=0)
    report = analyze(raw_html, doc)
    assert "nextjs-rsc" in report.frameworks_detected
    assert "react-helmet" in report.frameworks_detected


# --- Fixture-based tests -----------------------------------------------------


def test_nextjs_rsc_fixture_sentences_found_in_raw() -> None:
    """The Next.js RSC fixture has content locked in self.__next_f script
    tags. analyze() should find those sentences in the raw bytes."""
    raw_html = (FIXTURES / "nextjs_rsc_sample.html").read_text(encoding="utf-8")
    # Build a rendered doc that contains the sentences from the fixture
    md = f"{SENT_WASH}\n\n{SENT_MASS}\n\n{SENT_CALI}"
    doc = _doc(md)
    report = analyze(raw_html, doc)
    assert report.sentence_coverage > 0.9
    assert "nextjs-rsc" in report.frameworks_detected


def test_plain_article_fixture_full_coverage() -> None:
    """The plain article fixture has all content in visible HTML tags.
    analyze() should find everything."""
    raw_html = (FIXTURES / "plain_article.html").read_text(encoding="utf-8")
    doc = _doc(
        f"{SENT_WASH}\n\n{SENT_MASS}\n\n{SENT_CALI}",
        headings=[
            Heading(1, "The Visibility Gap in Modern Web Apps"),
            Heading(2, "Why JavaScript matters"),
            Heading(2, "How crawlers cope"),
        ],
    )
    report = analyze(raw_html, doc)
    assert report.sentence_coverage == 1.0
    assert report.heading_coverage == 1.0
    assert report.frameworks_detected == ()


def test_csr_spa_fixture_nothing_found() -> None:
    """The CSR SPA fixture has no content at all — just an empty div
    and a script src. Nothing from the rendered view should be found."""
    raw_html = (FIXTURES / "csr_spa.html").read_text(encoding="utf-8")
    doc = _doc(SENT_WASH, word_count=20)
    report = analyze(raw_html, doc)
    assert report.sentence_coverage == 0.0
    assert report.frameworks_detected == ()
