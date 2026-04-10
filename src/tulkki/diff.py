"""Visibility scoring + missing-section detection.

Pure functions, no I/O. Takes two FetchResults and two ExtractedDocs
(one pair from the raw/AI side, one from the rendered/human side) and
produces a VisibilityReport.

The v0.1 score blends two signals so that a page where AI sees the words
but not the heading structure (common in JS-hydrated docs sites) does not
falsely score 100 %:

    score = 0.7 * word_coverage + 0.3 * heading_coverage

Word coverage dominates because text is what LLMs ultimately consume,
but structure loss still moves the needle.
"""

from __future__ import annotations

from .types import ExtractedDoc, FetchResult, Heading, VisibilityReport

WORD_WEIGHT = 0.7
HEADING_WEIGHT = 0.3


def _word_coverage(ai_words: int, human_words: int) -> float:
    if human_words == 0:
        return 1.0 if ai_words == 0 else 0.0
    return min(1.0, ai_words / human_words)


def _heading_coverage(ai_doc: ExtractedDoc, human_doc: ExtractedDoc) -> float:
    if not human_doc.headings:
        return 1.0
    # Compare on the deduplicated set of (level, text) tuples on both
    # sides. A page that legitimately repeats the same section heading
    # (e.g. "Anecdotes from our teams" appearing 4 times) should not be
    # penalised for having only 2 unique headings.
    human_unique = human_doc.heading_set
    if not human_unique:
        return 1.0
    matched = len(ai_doc.heading_set & human_unique)
    return matched / len(human_unique)


def _visibility_score(ai_doc: ExtractedDoc, human_doc: ExtractedDoc) -> float:
    word_cov = _word_coverage(ai_doc.word_count, human_doc.word_count)
    head_cov = _heading_coverage(ai_doc, human_doc)
    # If the human side has no headings at all, structural signal is moot —
    # fall back to pure word coverage rather than rewarding the page for
    # an absence of structure.
    if not human_doc.headings:
        return word_cov
    return WORD_WEIGHT * word_cov + HEADING_WEIGHT * head_cov


def _missing_headings(
    ai_doc: ExtractedDoc, human_doc: ExtractedDoc
) -> tuple[Heading, ...]:
    ai_set = ai_doc.heading_set
    return tuple(h for h in human_doc.headings if (h.level, h.text) not in ai_set)


def compare(
    raw_fetch: FetchResult,
    rendered_fetch: FetchResult,
    ai_doc: ExtractedDoc,
    human_doc: ExtractedDoc,
) -> VisibilityReport:
    return VisibilityReport(
        url=rendered_fetch.url,
        fetched_at=rendered_fetch.fetched_at,
        raw_bytes=raw_fetch.bytes_size,
        rendered_bytes=rendered_fetch.bytes_size,
        ai_doc=ai_doc,
        human_doc=human_doc,
        raw_backend=raw_fetch.backend,
        render_backend=rendered_fetch.backend,
        raw_status=raw_fetch.status_code,
        render_status=rendered_fetch.status_code,
        visibility_score=_visibility_score(ai_doc, human_doc),
        missing_headings=_missing_headings(ai_doc, human_doc),
        elapsed_raw_ms=raw_fetch.elapsed_ms,
        elapsed_render_ms=rendered_fetch.elapsed_ms,
    )
