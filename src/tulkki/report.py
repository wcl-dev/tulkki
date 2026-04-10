"""Report rendering — terminal (rich), JSON, and unified diff.

Pure presentation layer. Takes a VisibilityReport and produces either
human-readable terminal output, a machine-readable JSON dict, or a
coloured unified diff of the AI view vs the human view.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .types import FetchResult, VisibilityReport


def _status_warning(raw_status: int, render_status: int) -> str | None:
    """Return a human warning if either fetch came back with a non-2xx
    status. A 403 / 401 / 429 means a CDN (often Cloudflare) is blocking
    our default User-Agent, in which case the AI-side content is the
    block page itself and the visibility score is meaningless."""

    def _label(status: int, side: str) -> str | None:
        if status == 0:
            return f"{side} fetch never returned a status code (timeout / network error)."
        if status >= 500:
            return f"{side} fetch returned HTTP {status} (server error)."
        if status == 403:
            return (
                f"{side} fetch returned HTTP 403 — this site is blocking our "
                "default User-Agent (Cloudflare or similar). The AI view shows "
                "the block page, not the real content."
            )
        if status == 401:
            return f"{side} fetch returned HTTP 401 — page requires authentication."
        if status == 429:
            return f"{side} fetch returned HTTP 429 — rate limited by the site."
        if status >= 400:
            return f"{side} fetch returned HTTP {status}."
        return None

    parts = [
        msg
        for msg in (_label(raw_status, "AI"), _label(render_status, "Human"))
        if msg is not None
    ]
    if not parts:
        return None
    return " ".join(parts)


def _format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.2f} MB"


def _score_color(score: float) -> str:
    if score >= 0.85:
        return "green"
    if score >= 0.5:
        return "yellow"
    return "red"


def render_terminal(report: VisibilityReport, console: Console | None = None) -> None:
    console = console or Console()

    console.print()
    console.rule(f"[bold]tulkki[/bold] check  [dim]{report.url}[/dim]")
    console.print()

    meta = Table(show_header=False, box=None, padding=(0, 2))
    meta.add_column(style="dim")
    meta.add_column()
    meta.add_row("URL", report.url)
    meta.add_row("Fetched at", report.fetched_at.isoformat(timespec="seconds"))
    meta.add_row(
        "Raw HTML",
        f"{_format_bytes(report.raw_bytes)}  "
        f"[dim]({report.raw_backend}, HTTP {report.raw_status}, "
        f"{report.elapsed_raw_ms} ms)[/dim]",
    )
    meta.add_row(
        "Rendered HTML",
        f"{_format_bytes(report.rendered_bytes)}  "
        f"[dim]({report.render_backend}, HTTP {report.render_status}, "
        f"{report.elapsed_render_ms} ms)[/dim]",
    )
    console.print(meta)

    warning = _status_warning(report.raw_status, report.render_status)
    if warning:
        console.print()
        console.print(f"[bold red]\\[!] {warning}[/bold red]")
        console.print(
            "[dim]The visibility score below is meaningless when a fetch "
            "is blocked. Try a different network, a real bot User-Agent, "
            "or report the block to the site owner.[/dim]"
        )

    console.print()
    views = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    views.add_column("View")
    views.add_column("Title", overflow="ellipsis", max_width=40)
    views.add_column("Words", justify="right")
    views.add_column("Headings", justify="right")
    views.add_row(
        "AI crawler",
        report.ai_doc.title or "—",
        f"{report.ai_doc.word_count:,}",
        f"{len(report.ai_doc.headings)}",
    )
    views.add_row(
        "Human",
        report.human_doc.title or "—",
        f"{report.human_doc.word_count:,}",
        f"{len(report.human_doc.headings)}",
    )
    console.print(views)

    console.print()
    score_pct = report.visibility_score * 100
    score_color = _score_color(report.visibility_score)
    icon = "[ok]" if report.visibility_score >= 0.85 else "[!]"
    score_line = Text()
    score_line.append("Visibility score:  ", style="bold")
    score_line.append(f"{score_pct:.1f}%  {icon}", style=f"bold {score_color}")
    console.print(score_line)

    if report.missing_headings:
        console.print()
        console.print("[bold]Sections AI cannot see:[/bold]")
        for h in report.missing_headings:
            console.print(f"  [red]x[/red] {h.text}  [dim](h{h.level})[/dim]")
    elif report.human_doc.word_count > 0:
        console.print()
        console.print("[green]All headings are visible to AI crawlers.[/green]")

    console.print()


def to_dict(report: VisibilityReport) -> dict[str, Any]:
    """Produce a JSON-serializable dict (drops the heavy markdown bodies)."""
    return {
        "url": report.url,
        "fetched_at": report.fetched_at.isoformat(),
        "raw": {
            "backend": report.raw_backend,
            "status": report.raw_status,
            "bytes": report.raw_bytes,
            "elapsed_ms": report.elapsed_raw_ms,
            "title": report.ai_doc.title,
            "word_count": report.ai_doc.word_count,
            "heading_count": len(report.ai_doc.headings),
        },
        "rendered": {
            "backend": report.render_backend,
            "status": report.render_status,
            "bytes": report.rendered_bytes,
            "elapsed_ms": report.elapsed_render_ms,
            "title": report.human_doc.title,
            "word_count": report.human_doc.word_count,
            "heading_count": len(report.human_doc.headings),
        },
        "visibility_score": round(report.visibility_score, 4),
        "warning": _status_warning(report.raw_status, report.render_status),
        "missing_headings": [
            {"level": h.level, "text": h.text} for h in report.missing_headings
        ],
    }


def render_json(report: VisibilityReport) -> str:
    return json.dumps(to_dict(report), indent=2, ensure_ascii=False)


def render_diff(report: VisibilityReport, console: Console | None = None) -> None:
    """Print a coloured unified diff of the AI view vs the human view.

    Green lines are present in the human view but not in the AI view
    (= what AI crawlers miss). Red lines are present in the AI view but
    not in the human view (usually trafilatura extraction noise, rare).
    This gives users a direct answer to "what exactly is the AI missing?"
    without forcing them to open both markdown files in an external diff
    viewer.
    """
    console = console or Console()

    ai_lines = report.ai_doc.markdown.splitlines()
    human_lines = report.human_doc.markdown.splitlines()

    diff_lines = list(
        difflib.unified_diff(
            ai_lines,
            human_lines,
            fromfile="ai_view.md",
            tofile="human_view.md",
            lineterm="",
            n=2,
        )
    )

    console.print()
    console.rule("[bold]Content diff[/bold]  [dim](AI view → Human view)[/dim]")
    console.print()

    if not diff_lines:
        console.print(
            "[dim]No textual difference between the AI and human views.[/dim]"
        )
        console.print()
        return

    for line in diff_lines:
        if line.startswith("+++") or line.startswith("---"):
            console.print(f"[bold]{line}[/bold]", highlight=False)
        elif line.startswith("@@"):
            console.print(f"[cyan]{line}[/cyan]", highlight=False)
        elif line.startswith("+"):
            console.print(f"[green]{line}[/green]", highlight=False)
        elif line.startswith("-"):
            console.print(f"[red]{line}[/red]", highlight=False)
        else:
            console.print(f"[dim]{line}[/dim]", highlight=False)

    console.print()
    console.print(
        "[dim]Legend: [green]green[/green] = visible to humans but not AI "
        "(the visibility gap). [red]red[/red] = visible to AI but not "
        "humans (usually extraction noise).[/dim]"
    )
    console.print()
