"""CLI-layer integration tests using typer's CliRunner.

These tests monkeypatch the backend factories so no network calls are made.
They verify that CLI flags, output formats, and exit codes work as expected.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from tulkki.cli import app
from tulkki.types import FetchResult

runner = CliRunner()

# --- Fake fetcher that returns canned HTML ------------------------------------

# A simple HTML page where trafilatura can extract content.
_ARTICLE_HTML = """
<html>
<head><title>Test Article</title></head>
<body>
<article>
  <h1>The Visibility Gap</h1>
  <p>Washington, D.C. is the capital city of the United States and ranks
  first in AI adoption among all fifty states according to recent surveys
  conducted across multiple industries and government agencies.</p>
  <h2>Why JavaScript matters</h2>
  <p>Massachusetts ranks second in AI research output with over three
  hundred active laboratories and research centers dedicated to artificial
  intelligence and machine learning development across universities.</p>
  <h2>How crawlers cope</h2>
  <p>California leads the nation in AI startup funding with billions of
  dollars invested annually in companies developing next generation
  artificial intelligence technologies and practical applications.</p>
</article>
</body>
</html>
"""

# An empty SPA shell — rendered version would have content, raw does not.
_EMPTY_SPA_HTML = """
<html>
<head><title>My App</title></head>
<body><div id="root"></div><script src="/bundle.js"></script></body>
</html>
"""


def _make_fetch_result(html: str, backend: str = "test") -> FetchResult:
    return FetchResult(
        url="https://example.com/test",
        html=html,
        status_code=200,
        bytes_size=len(html.encode("utf-8")),
        fetched_at=datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc),
        elapsed_ms=100,
        backend=backend,
    )


class _FakeFetcher:
    """A fetcher that always returns the same canned HTML."""

    def __init__(self, html: str, name: str = "test") -> None:
        self.name = name
        self._html = html

    def fetch(self, url: str) -> FetchResult:
        return _make_fetch_result(self._html, backend=self.name)


def _patch_fetchers(raw_html: str = _ARTICLE_HTML, rendered_html: str | None = None):
    """Return a context manager that patches both fetcher factories."""
    if rendered_html is None:
        rendered_html = raw_html

    raw_fetcher = _FakeFetcher(raw_html, name="fake-raw")
    render_fetcher = _FakeFetcher(rendered_html, name="fake-render")

    return (
        patch("tulkki.cli.get_raw_fetcher", return_value=raw_fetcher),
        patch("tulkki.cli.get_rendering_fetcher", return_value=render_fetcher),
    )


# --- Tests --------------------------------------------------------------------


def test_cli_check_renders_terminal_report() -> None:
    """Basic smoke test: tulkki check prints a terminal report."""
    p1, p2 = _patch_fetchers()
    with p1, p2:
        result = runner.invoke(app, ["check", "https://example.com", "--no-save"])
    assert result.exit_code == 0
    assert "Extracted" in result.output
    assert "Rendered" in result.output
    assert "Extractor visibility:" in result.output


def test_cli_json_output_has_new_fields() -> None:
    """--json output must include v0.2 fields alongside v0.1 fields."""
    p1, p2 = _patch_fetchers()
    with p1, p2:
        result = runner.invoke(
            app, ["check", "https://example.com", "--json", "--no-save"]
        )
    assert result.exit_code == 0
    data = json.loads(result.output)
    # v0.1 fields still present
    assert "visibility_score" in data
    assert "missing_headings" in data
    assert "raw" in data
    assert "rendered" in data
    # v0.2 fields
    assert "raw_presence_score" in data
    assert "gap_kind" in data
    assert "raw_presence" in data
    assert "interpretation" in data
    assert "frameworks_detected" in data["raw_presence"]


def test_cli_quiet_format_unchanged() -> None:
    """--quiet must print a single float (visibility_score) for backward
    compatibility with pipe consumers."""
    p1, p2 = _patch_fetchers()
    with p1, p2:
        result = runner.invoke(
            app, ["check", "https://example.com", "--quiet", "--no-save"]
        )
    assert result.exit_code == 0
    line = result.output.strip()
    # Must be a single number, parseable as float
    score = float(line)
    assert 0 <= score <= 100


def test_cli_no_render_hides_raw_presence() -> None:
    """--no-render should hide raw-bytes presence to avoid misleading 100%."""
    p1, p2 = _patch_fetchers()
    with p1, p2:
        result = runner.invoke(
            app, ["check", "https://example.com", "--no-render", "--no-save"]
        )
    assert result.exit_code == 0
    assert "Raw-bytes presence" not in result.output
    assert "Raw HTML coverage:" not in result.output
    assert "Gap kind:" not in result.output
    # Extractor visibility should still appear
    assert "Extractor visibility:" in result.output


def test_cli_fail_below_checks_visibility_score_only() -> None:
    """--fail-below should check visibility_score, not raw_presence_score.
    With identical raw/rendered HTML, visibility_score = 100%."""
    p1, p2 = _patch_fetchers()
    with p1, p2:
        # Threshold 50 should pass (score is 100%)
        result = runner.invoke(
            app,
            ["check", "https://example.com", "--fail-below", "50", "--no-save", "--quiet"],
        )
    assert result.exit_code == 0


def test_cli_fail_below_raw_checks_raw_presence_score() -> None:
    """--fail-below-raw exits 1 when raw_presence_score is below threshold.
    With an empty SPA as raw and article as rendered, raw_presence will be
    very low."""
    p1, p2 = _patch_fetchers(raw_html=_EMPTY_SPA_HTML, rendered_html=_ARTICLE_HTML)
    with p1, p2:
        result = runner.invoke(
            app,
            [
                "check", "https://example.com",
                "--fail-below-raw", "90",
                "--no-save", "--quiet",
            ],
        )
    assert result.exit_code == 1


def test_cli_show_raw_hits_prints_missing_sentences() -> None:
    """--show-raw-hits should print rendering-gap sentences when raw HTML
    differs from rendered content."""
    p1, p2 = _patch_fetchers(raw_html=_EMPTY_SPA_HTML, rendered_html=_ARTICLE_HTML)
    with p1, p2:
        result = runner.invoke(
            app,
            ["check", "https://example.com", "--show-raw-hits", "--no-save"],
        )
    assert result.exit_code == 0
    assert "Rendering-gap sentences" in result.output


def test_cli_show_diff_still_works() -> None:
    """--show-diff should still work alongside the new features."""
    p1, p2 = _patch_fetchers(raw_html=_EMPTY_SPA_HTML, rendered_html=_ARTICLE_HTML)
    with p1, p2:
        result = runner.invoke(
            app,
            ["check", "https://example.com", "--show-diff", "--no-save"],
        )
    assert result.exit_code == 0
    assert "Content diff" in result.output
