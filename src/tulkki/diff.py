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

from .raw_presence import analyze as _analyze_raw_presence
from .types import ExtractedDoc, FetchResult, GapKind, Heading, VisibilityReport

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
    """Return the headings the human sees but the AI does not.

    The human side is deduplicated on `(level, text)` so that a page which
    legitimately repeats the same heading (e.g. "Anecdotes from our teams"
    appearing four times on the OpenAI Codex page) is not reported as
    "missing" for any of the duplicates when the AI sees at least one.
    This keeps `_missing_headings` consistent with `_heading_coverage`,
    which also works on the deduplicated set.
    """
    ai_set = ai_doc.heading_set
    seen: set[tuple[int, str]] = set()
    missing: list[Heading] = []
    for h in human_doc.headings:
        key = (h.level, h.text)
        if key in ai_set or key in seen:
            continue
        seen.add(key)
        missing.append(h)
    return tuple(missing)


MATERIAL_THRESHOLD = 0.15  # a gap >= 15% is considered material


def _classify_gap(
    raw_presence_score: float,
    visibility_score: float,
    raw_status: int,
    render_status: int,
) -> GapKind:
    """Classify the nature of the visibility gap.

    Uses the two scores and HTTP statuses to determine whether content
    loss is due to extraction failure (content in bytes but extractors
    miss it), rendering failure (content only exists post-JS), both, or
    neither.
    """
    if raw_status >= 400 or render_status >= 400 or raw_status == 0:
        return GapKind.BLOCKED
    raw_ok = raw_presence_score >= (1 - MATERIAL_THRESHOLD)
    ext_ok = visibility_score >= (1 - MATERIAL_THRESHOLD)
    # If the extractor already recovers most content, there is no
    # actionable visibility gap — regardless of raw_presence_score
    # (which may be low due to sentence-splitting artifacts on pages
    # with lists, tables, or non-standard punctuation).
    if ext_ok:
        return GapKind.NONE
    if raw_ok:
        return GapKind.EXTRACTION
    # Both scores below threshold. Distinguish: if raw bytes contain
    # notably more than what the extractor sees, it's a mix of both
    # extraction failure and rendering failure. If they're roughly
    # equal (both very low), it's pure rendering failure.
    if raw_presence_score > visibility_score + 0.20:
        return GapKind.MIXED
    return GapKind.RENDERING


def compare(
    raw_fetch: FetchResult,
    rendered_fetch: FetchResult,
    ai_doc: ExtractedDoc,
    human_doc: ExtractedDoc,
) -> VisibilityReport:
    vis_score = _visibility_score(ai_doc, human_doc)
    raw_presence = _analyze_raw_presence(raw_fetch.html, human_doc)
    rp_score = raw_presence.sentence_coverage
    gap_kind = _classify_gap(
        rp_score, vis_score,
        raw_fetch.status_code, rendered_fetch.status_code,
    )

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
        visibility_score=vis_score,
        missing_headings=_missing_headings(ai_doc, human_doc),
        elapsed_raw_ms=raw_fetch.elapsed_ms,
        elapsed_render_ms=rendered_fetch.elapsed_ms,
        raw_presence=raw_presence,
        raw_presence_score=rp_score,
        gap_kind=gap_kind,
    )
