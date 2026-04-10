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
    # Strip markdown syntax characters that would inflate the count
    stripped = re.sub(r"[#*_`>\[\]()!]", " ", markdown)
    return len(stripped.split())


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
