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

# Minimum sentence length. Two thresholds because CJK (Chinese, Japanese,
# Korean) is information-denser than Latin scripts — a 15-character Chinese
# sentence is a full thought, whereas a 15-character Latin fragment is
# usually boilerplate. We apply the CJK threshold when the sentence is
# more than half CJK characters.
MIN_SENTENCE_CHARS_LATIN = 45
MIN_SENTENCE_CHARS_CJK = 15
MAX_SENTENCES = 400  # cap work on very large pages
PROBE_CHARS = 60  # first N chars of a sentence are enough to be unique

# Sentence boundary patterns for Latin + CJK.
# Latin: period/exclamation/question + whitespace + capital/digit/quote.
# CJK: full-width period/exclamation/question/semicolon (。！？；) and
# their half-width equivalents, optionally followed by whitespace.
_SENT_SPLIT_LATIN = re.compile(
    r"(?<=[.!?])\s+"
    r"(?=[A-Z0-9\"'("
    r"\u3400-\u4dbf\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af"
    r"])"
)
_SENT_SPLIT_CJK = re.compile(r"(?<=[\u3002\uff01\uff1f\uff1b])")

# CJK character range (matches what extractor.py uses).
_CJK_CHAR_RE = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]"
)

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


_HAYSTACK_REPLACEMENTS = str.maketrans(
    {
        # JS/JSON string escapes are handled separately (multi-char)
        # Unicode punctuation → ASCII equivalents
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
    }
)

# Multi-char replacements applied in order via str.replace.
_HAYSTACK_MULTI: list[tuple[str, str]] = [
    ('\\"', '"'),
    ("\\'", "'"),
    ("\\/", "/"),
    ("\\n", " "),
    ("\\t", " "),
    ("&amp;", "&"),
    ("&quot;", '"'),
    ("&#39;", "'"),
    ("&apos;", "'"),
]


def _normalize_haystack(raw_html: str) -> str:
    """Prepare the raw HTML bytes for substring searching.

    Lowercase, unescape common JS/JSON string escapes and HTML entities,
    normalize Unicode punctuation, and collapse whitespace. This allows a
    rendered sentence like ``Washington, D.C. is the capital`` to match
    RSC flight data that stores it as ``\\"Washington, D.C. is the capital\\"``.
    """
    s = raw_html.lower()
    for old, new in _HAYSTACK_MULTI:
        s = s.replace(old, new)
    s = s.translate(_HAYSTACK_REPLACEMENTS)
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


def _is_cjk_dominant(s: str) -> bool:
    """Return True if more than half of the alphabetic characters are CJK."""
    if not s:
        return False
    cjk_count = len(_CJK_CHAR_RE.findall(s))
    # Count "meaningful" characters: letters + CJK, ignore digits and punctuation
    alpha_count = sum(1 for c in s if c.isalpha() or _CJK_CHAR_RE.match(c))
    if alpha_count == 0:
        return False
    return cjk_count / alpha_count > 0.5


def _min_sentence_chars(s: str) -> int:
    """Pick the right minimum length for the script in the sentence."""
    return MIN_SENTENCE_CHARS_CJK if _is_cjk_dominant(s) else MIN_SENTENCE_CHARS_LATIN


def _sentences(markdown: str) -> list[str]:
    """Split rendered markdown into sentences suitable for presence-checking.

    Strips markdown syntax, then splits on both Latin sentence boundaries
    (.!? followed by capital/digit/quote) and CJK sentence boundaries
    (。！？；、 with optional whitespace).

    Drops fragments shorter than the script-appropriate minimum length:
    - Latin text: 45 characters (filters out "OK.", "Learn more", nav items)
    - CJK text: 15 characters (CJK is information-denser)

    This lets tulkki handle Chinese, Japanese, and Korean pages without
    either over-counting boilerplate or dropping legitimate short sentences.
    """
    text = re.sub(r"[#*_`>\[\]()!]", " ", markdown)
    text = re.sub(r"\s+", " ", text).strip()

    # Run Latin split first, then CJK split on each result. This handles
    # mixed-script pages (e.g. a Chinese paragraph followed by an English
    # one) without losing either boundary.
    latin_split = _SENT_SPLIT_LATIN.split(text)
    sentences: list[str] = []
    for chunk in latin_split:
        for subchunk in _SENT_SPLIT_CJK.split(chunk):
            subchunk = subchunk.strip()
            if subchunk and len(subchunk) >= _min_sentence_chars(subchunk):
                sentences.append(subchunk)
    return sentences[:MAX_SENTENCES]


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
