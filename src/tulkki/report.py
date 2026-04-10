"""Report rendering — terminal (rich) and JSON.

Pure presentation layer. Takes a VisibilityReport and produces either
human-readable terminal output or a machine-readable JSON dict.
"""

from __future__ import annotations

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
