"""Trafilatura-backed extractor.

The default (and currently only) extractor for tulkki v0.1. Wraps
`trafilatura.extract` to produce a clean Markdown body, then derives
headings from the Markdown itself (rather than from the source HTML)
so that boilerplate-removed sections are correctly absent.
"""

from __future__ import annotations

import re

import trafilatura

from .types import ExtractedDoc, Heading

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

# CJK character ranges: Chinese, Japanese, Korean. Covers Unified
# Ideographs, Extension A, Hiragana, Katakana, and Hangul. CJK writing
# systems don't separate words with spaces, so each ideograph / kana /
# syllable block counts as one "word" for word_count purposes.
_CJK_CHAR_RE = re.compile(
    r"[\u3400-\u4dbf"   # CJK Extension A
    r"\u4e00-\u9fff"    # CJK Unified Ideographs
    r"\u3040-\u309f"    # Hiragana
    r"\u30a0-\u30ff"    # Katakana
    r"\uac00-\ud7af"    # Hangul Syllables
    r"]"
)


def _parse_headings(markdown: str) -> tuple[Heading, ...]:
    headings: list[Heading] = []
    in_code_block = False
    for line in markdown.splitlines():
        # Skip fenced code blocks so a "# include" inside C code doesn't count
        if line.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            if text:
                headings.append(Heading(level=level, text=text))
    return tuple(headings)


def _word_count(markdown: str) -> int:
    """Count words in markdown text, handling Latin and CJK scripts.

    Latin scripts are space-separated — we use str.split().
    CJK scripts (Chinese, Japanese, Korean) have no spaces between
    logical words, so each CJK character counts as one word. This
    approximates what a reader experiences — a 500-character Chinese
    article is the reading equivalent of a 500-word English one.
    """
    # Strip markdown syntax characters that would inflate the count
    stripped = re.sub(r"[#*_`>\[\]()!]", " ", markdown)
    # Count each CJK character as one word
    cjk_chars = _CJK_CHAR_RE.findall(stripped)
    # Strip CJK chars out, then count the remaining Latin words by spaces
    latin_only = _CJK_CHAR_RE.sub(" ", stripped)
    latin_words = latin_only.split()
    return len(cjk_chars) + len(latin_words)


class TrafilaturaExtractor:
    name = "trafilatura"

    def extract(self, html: str, url: str | None = None) -> ExtractedDoc:
        markdown = (
            trafilatura.extract(
                html,
                url=url,
                output_format="markdown",
                include_comments=False,
                include_tables=True,
                include_formatting=True,
                include_links=False,
                with_metadata=False,
                favor_recall=True,
            )
            or ""
        )

        title: str | None = None
        try:
            meta = trafilatura.extract_metadata(html)
            if meta is not None:
                title = meta.title
        except Exception:
            title = None

        return ExtractedDoc(
            title=title,
            markdown=markdown,
            headings=_parse_headings(markdown),
            word_count=_word_count(markdown),
        )
