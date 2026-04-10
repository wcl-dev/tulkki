"""Raw-bytes presence analysis.

Checks how much of the rendered (human-visible) content is physically
present as substrings in the raw HTML bytes, before any extraction or
JS rendering. This separates two failure modes:

- Extraction gap: content IS in the raw bytes but standard extractors
  (trafilatura, readability.js, Common Crawl WET) cannot unpack it
  (e.g. Next.js 13 RSC flight data inside <script> tags).

- Rendering gap: content is NOT in the raw bytes at all and only
  appears after JS execution (true client-side rendering).
"""

from __future__ import annotations

import re

from .types import ExtractedDoc, Heading, RawPresenceReport

# --- Configuration -----------------------------------------------------------

MIN_SENTENCE_CHARS = 45  # shorter fragments ("OK.", "Learn more") cause false positives
MAX_SENTENCES = 400  # cap work on very large pages
PROBE_CHARS = 60  # first N chars of a sentence are enough to be unique

# Sentence boundary: period/exclamation/question followed by whitespace then
# an uppercase letter, digit, or opening quote. Not perfect, but good enough
# for the purpose of splitting rendered content into searchable chunks.
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")

# Known framework signatures detected by substring search on raw HTML.
FRAMEWORK_SIGNATURES: dict[str, str] = {
    "nextjs-rsc": "self.__next_f",
    "nextjs-pages": "__NEXT_DATA__",
    "nuxt": "window.__NUXT__",
    "sveltekit": "__sveltekit",
    "gatsby": "window.___gatsby",
    "remix": "__remixContext",
    "react-helmet": "data-react-helmet",
}


# --- Normalization -----------------------------------------------------------


def _normalize_haystack(raw_html: str) -> str:
    """Prepare the raw HTML bytes for substring searching.

    Lowercase, unescape common JS/JSON string escapes and HTML entities,
    collapse whitespace. This allows a rendered sentence like
    ``Washington, D.C. is the capital`` to match RSC flight data that
    stores it as ``\\"Washington, D.C. is the capital\\"``.
    """
    s = raw_html.lower()
    # JS/JSON string escapes
    s = s.replace('\\"', '"').replace("\\'", "'").replace("\\/", "/")
    s = s.replace("\\n", " ").replace("\\t", " ")
    # Common HTML entities that appear in free text
    s = s.replace("&amp;", "&").replace("&quot;", '"')
    s = s.replace("&#39;", "'").replace("&apos;", "'")
    # Normalize Unicode punctuation to ASCII equivalents so that
    # trafilatura's output (which may use curly quotes) matches the
    # raw HTML (which typically uses straight quotes or escapes).
    s = s.replace("\u2018", "'").replace("\u2019", "'")  # ' '
    s = s.replace("\u201c", '"').replace("\u201d", '"')  # " "
    s = s.replace("\u2013", "-").replace("\u2014", "-")  # – —
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s)
    return s


def _normalize_needle(sentence: str) -> str:
    """Normalize a rendered sentence for matching against the haystack."""
    s = sentence.lower()
    s = s.replace("\u2018", "'").replace("\u2019", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", s).strip()


# --- Sentence extraction -----------------------------------------------------


def _sentences(markdown: str) -> list[str]:
    """Split rendered markdown into sentences suitable for presence-checking.

    Strips markdown syntax, splits on sentence boundaries, and drops
    fragments shorter than MIN_SENTENCE_CHARS to avoid false positives
    from boilerplate like "OK.", "Learn more", or nav items.
    """
    text = re.sub(r"[#*_`>\[\]()!]", " ", markdown)
    text = re.sub(r"\s+", " ", text).strip()
    raw = _SENT_SPLIT.split(text)
    return [s for s in raw if len(s) >= MIN_SENTENCE_CHARS][:MAX_SENTENCES]


# --- Heading deduplication ---------------------------------------------------


def _dedupe_headings(headings: tuple[Heading, ...]) -> list[Heading]:
    """Return unique headings preserving first-seen order."""
    seen: set[tuple[int, str]] = set()
    result: list[Heading] = []
    for h in headings:
        key = (h.level, h.text.strip().lower())
        if key not in seen and h.text.strip():
            seen.add(key)
            result.append(h)
    return result


# --- Main entry point --------------------------------------------------------


def analyze(raw_html: str, rendered_doc: ExtractedDoc) -> RawPresenceReport:
    """Analyze how much of the rendered content exists in the raw HTML bytes.

    Parameters
    ----------
    raw_html:
        The raw HTML string as returned by the no-JS fetcher.
    rendered_doc:
        The ExtractedDoc produced from the post-JS (rendered) HTML.

    Returns
    -------
    RawPresenceReport with sentence coverage, heading coverage, lists of
    missing items, and detected framework signatures.
    """
    # Edge case: empty raw HTML
    if not raw_html.strip():
        has_content = rendered_doc.word_count > 0
        has_headings = len(rendered_doc.headings) > 0
        return RawPresenceReport(
            sentence_coverage=0.0 if has_content else 1.0,
            sentences_checked=0,
            sentences_found_in_raw=0,
            heading_coverage=0.0 if has_headings else 1.0,
            headings_checked=0,
            headings_found_in_raw=0,
            missing_sentences=(),
            missing_headings=rendered_doc.headings if has_headings else (),
            frameworks_detected=(),
        )

    haystack = _normalize_haystack(raw_html)

    # --- Sentence coverage ---------------------------------------------------
    sentences = _sentences(rendered_doc.markdown)
    found = 0
    missing_sent: list[str] = []
    for s in sentences:
        needle = _normalize_needle(s)
        # Use only the first PROBE_CHARS characters as the search probe.
        # Long enough to be virtually unique in the document, short enough
        # to survive text being split across HTML node boundaries.
        probe = needle[:PROBE_CHARS]
        if probe and probe in haystack:
            found += 1
        else:
            if len(missing_sent) < 20:
                missing_sent.append(s)

    n_sent = len(sentences)
    sentence_cov = 1.0 if n_sent == 0 else found / n_sent

    # --- Heading coverage ----------------------------------------------------
    unique_headings = _dedupe_headings(rendered_doc.headings)
    h_found = 0
    missing_h: list[Heading] = []
    for h in unique_headings:
        if h.text.strip().lower() in haystack:
            h_found += 1
        else:
            missing_h.append(h)
    head_cov = 1.0 if not unique_headings else h_found / len(unique_headings)

    # --- Framework detection -------------------------------------------------
    frameworks = tuple(
        name
        for name, marker in sorted(FRAMEWORK_SIGNATURES.items())
        if marker.lower() in haystack
    )

    return RawPresenceReport(
        sentence_coverage=sentence_cov,
        sentences_checked=n_sent,
        sentences_found_in_raw=found,
        heading_coverage=head_cov,
        headings_checked=len(unique_headings),
        headings_found_in_raw=h_found,
        missing_sentences=tuple(missing_sent),
        missing_headings=tuple(missing_h),
        frameworks_detected=frameworks,
    )
