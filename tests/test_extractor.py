"""Unit tests for the trafilatura-backed extractor."""

from __future__ import annotations

from tulkki.extractor import TrafilaturaExtractor, _parse_headings, _word_count
from tulkki.types import Heading


def test_parse_markdown_headings_levels() -> None:
    md = "# One\n\nbody\n\n## Two\n\n### Three\n\nfooter"
    assert _parse_headings(md) == (
        Heading(1, "One"),
        Heading(2, "Two"),
        Heading(3, "Three"),
    )


def test_parse_headings_ignores_fenced_code_blocks() -> None:
    md = (
        "# Real heading\n\n"
        "```python\n"
        "# This is a Python comment, not a heading\n"
        "def f(): pass\n"
        "```\n\n"
        "## Another real heading"
    )
    headings = _parse_headings(md)
    assert headings == (Heading(1, "Real heading"), Heading(2, "Another real heading"))


def test_word_count_strips_markdown_syntax() -> None:
    md = "# Title\n\nThis is **bold** and *italic* and [link](http://x)."
    # 8 content words: This is bold and italic and link x
    assert _word_count(md) >= 8
    # And it should not count the syntax characters as words
    assert _word_count("***") == 0


def test_word_count_chinese_counts_each_character() -> None:
    """Chinese text has no spaces, so each ideograph counts as one word.
    A ten-character sentence should count as 10."""
    md = "今天天氣真的很好"  # 8 characters
    assert _word_count(md) == 8


def test_word_count_japanese_counts_each_kana_and_kanji() -> None:
    """Hiragana, katakana, and kanji each count individually."""
    md = "私はカタカナです"  # 8 chars: mix of hiragana, kanji, katakana
    assert _word_count(md) == 8


def test_word_count_korean_counts_each_syllable_block() -> None:
    md = "안녕하세요"  # 5 Hangul syllable blocks
    assert _word_count(md) == 5


def test_word_count_mixed_scripts() -> None:
    """Mixed CJK + Latin: CJK chars counted individually, Latin by spaces."""
    md = "I love 台灣 very much"
    # Latin: "I love very much" = 4 words; CJK: 台灣 = 2 chars; total = 6
    assert _word_count(md) == 6


def test_extract_smoke_on_realistic_html() -> None:
    """Use a realistic-length article so trafilatura's main-content
    detection actually engages and emits Markdown headings."""
    paragraphs = "\n".join(
        f"<p>This is paragraph {i} of the test article body. "
        f"It contains enough words to trip the boilerplate filter "
        f"that trafilatura applies to short snippets, which would "
        f"otherwise discard the content entirely.</p>"
        for i in range(8)
    )
    html = f"""
    <html>
      <head><title>Test article</title></head>
      <body>
        <nav>Site nav | Home | About</nav>
        <article>
          <h1>The Visibility Gap in Modern Web Apps</h1>
          {paragraphs}
          <h2>Why JavaScript matters</h2>
          {paragraphs}
          <h2>How crawlers cope</h2>
          {paragraphs}
        </article>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    """
    doc = TrafilaturaExtractor().extract(html, url="https://example.com/sample")
    assert doc.markdown.strip() != ""
    # Should pick up at least the two h2 headings; the h1 sometimes
    # gets promoted to the title and stripped from the body, which is
    # fine — we're testing that level detection works at all.
    assert len(doc.headings) >= 2
    assert doc.word_count > 100
