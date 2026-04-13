"""Report rendering — terminal (rich), JSON, unified diff, and HTML.

Pure presentation layer. Takes a VisibilityReport and produces either
human-readable terminal output, a machine-readable JSON dict, a
coloured unified diff, or a self-contained HTML report.
"""

from __future__ import annotations

import difflib
import html as html_mod
import json
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .descriptions import METRIC_HELP_PLAIN
from .diff import SCORE_OK_THRESHOLD
from .types import GapKind, VisibilityReport


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


_SCORE_BANDS: list[tuple[float, str, str]] = [
    (SCORE_OK_THRESHOLD, "green", "#22c55e"),
    (0.50, "yellow", "#eab308"),
    (0.00, "red", "#ef4444"),
]


def _score_color(score: float) -> str:
    for threshold, name, _ in _SCORE_BANDS:
        if score >= threshold:
            return name
    return "red"


def _score_color_hex(score: float) -> str:
    for threshold, _, hex_val in _SCORE_BANDS:
        if score >= threshold:
            return hex_val
    return "#ef4444"


def _interpretation(report: VisibilityReport) -> str:
    """Return a human-readable interpretation paragraph based on gap_kind
    and detected frameworks."""
    rp = report.raw_presence
    frameworks = rp.frameworks_detected
    rp_pct = report.raw_presence_score * 100

    if report.gap_kind == GapKind.BLOCKED:
        return ""  # _status_warning already handles this
    if report.gap_kind == GapKind.NONE:
        return "AI crawlers see the same content as human users."

    if report.gap_kind == GapKind.EXTRACTION:
        if "nextjs-rsc" in frameworks:
            return (
                f"The content of this page is physically present in the raw "
                f"HTML bytes ({rp_pct:.1f}% sentence coverage), but it's "
                f"locked inside Next.js 13 React Server Components flight "
                f"data (self.__next_f). Standard content extractors cannot "
                f"unpack this format. LLM training pipelines that rely on "
                f"Common Crawl's pre-extracted WET files will miss this page "
                f"entirely. Pipelines that tokenize raw HTML bytes directly "
                f"(including script tag contents) will see the content, but "
                f"buried in framework plumbing."
            )
        if "nextjs-pages" in frameworks:
            return (
                f"The content is in the raw HTML bytes ({rp_pct:.1f}% "
                f"sentence coverage) inside a Next.js __NEXT_DATA__ payload, "
                f"but standard extractors cannot unpack it."
            )
        if frameworks:
            fw_names = ", ".join(frameworks)
            return (
                f"The content is in the raw HTML bytes ({rp_pct:.1f}% "
                f"sentence coverage) but locked inside framework-specific "
                f"data structures ({fw_names}). Standard content extractors "
                f"cannot unpack this format."
            )
        return (
            f"The content is in the raw HTML bytes ({rp_pct:.1f}% sentence "
            f"coverage) but wrapped in non-standard structures that "
            f"standard content extractors cannot unpack."
        )

    if report.gap_kind == GapKind.RENDERING:
        return (
            "The content is genuinely absent from the raw HTML and only "
            "appears after JavaScript execution. Any AI crawler that does "
            "not run JavaScript will not see this content."
        )

    # MIXED
    return (
        "Both extraction and rendering gaps are present. Some content is "
        "locked inside framework data structures in the raw HTML, and some "
        "content only appears after JavaScript execution."
    )


def render_terminal(
    report: VisibilityReport,
    console: Console | None = None,
    no_render: bool = False,
) -> None:
    console = console or Console()

    console.print()
    console.rule(f"[bold]tulkki[/bold] check  [dim]{report.url}[/dim]")
    console.print()

    # --- Metadata block ------------------------------------------------------
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
    if report.raw_presence.frameworks_detected:
        fw = ", ".join(report.raw_presence.frameworks_detected)
        meta.add_row("Framework", fw)
    console.print(meta)

    # --- HTTP warning --------------------------------------------------------
    warning = _status_warning(report.raw_status, report.render_status)
    if warning:
        console.print()
        console.print(f"[bold red]\\[!] {warning}[/bold red]")
        console.print(
            "[dim]The scores below are meaningless when a fetch "
            "is blocked. Try a different network, a real bot User-Agent, "
            "or report the block to the site owner.[/dim]"
        )

    # --- Views table ---------------------------------------------------------
    console.print()
    views = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    views.add_column("View")
    views.add_column("Title", overflow="ellipsis", max_width=40)
    views.add_column("Words", justify="right")
    views.add_column("Headings", justify="right")
    views.add_row(
        "Extracted",
        report.ai_doc.title or "—",
        f"{report.ai_doc.word_count:,}",
        f"{len(report.ai_doc.headings)}",
    )
    views.add_row(
        "Rendered",
        report.human_doc.title or "—",
        f"{report.human_doc.word_count:,}",
        f"{len(report.human_doc.headings)}",
    )
    console.print(views)

    # --- Raw-bytes presence block (hidden in --no-render mode) ----------------
    if not no_render:
        rp = report.raw_presence
        console.print()
        console.print(
            "[bold]Raw-bytes presence[/bold]  "
            "[dim](substring search of raw HTML):[/dim]"
        )
        console.print(
            f"  Sentences:  "
            f"{rp.sentences_found_in_raw}/{rp.sentences_checked}  "
            f"[dim]({rp.sentence_coverage * 100:.1f}%)[/dim]"
        )
        console.print(
            f"  Headings:   "
            f"{rp.headings_found_in_raw}/{rp.headings_checked}  "
            f"[dim]({rp.heading_coverage * 100:.1f}%)[/dim]"
        )

    # --- Scores block --------------------------------------------------------
    console.print()

    if not no_render:
        # Raw HTML coverage line
        rp_pct = report.raw_presence_score * 100
        rp_color = _score_color(report.raw_presence_score)
        rp_icon = "[ok]" if report.raw_presence_score >= SCORE_OK_THRESHOLD else "[!]"
        rp_line = Text()
        rp_line.append("Raw HTML coverage:     ", style="bold")
        rp_line.append(f"{rp_pct:.1f}%  {rp_icon}", style=f"bold {rp_color}")
        rp_line.append(
            "  (AI crawlers tokenizing raw HTML bytes)", style="dim"
        )
        console.print(rp_line)

    # Extractor visibility line (= visibility_score, always shown)
    vis_pct = report.visibility_score * 100
    vis_color = _score_color(report.visibility_score)
    vis_icon = "[ok]" if report.visibility_score >= SCORE_OK_THRESHOLD else "[!]"
    vis_line = Text()
    vis_line.append("Extractor visibility:  ", style="bold")
    vis_line.append(f"{vis_pct:.1f}%  {vis_icon}", style=f"bold {vis_color}")
    vis_line.append(
        "  (trafilatura / Common Crawl WET / readability.js)", style="dim"
    )
    console.print(vis_line)

    # --- Gap kind + interpretation -------------------------------------------
    if not no_render and report.gap_kind != GapKind.BLOCKED:
        console.print()
        kind_color = "green" if report.gap_kind == GapKind.NONE else "yellow"
        console.print(
            f"[bold]Gap kind:[/bold] [{kind_color}]{report.gap_kind.value.upper()}[/{kind_color}]"
        )
        interp = _interpretation(report)
        if interp:
            console.print(f"[dim]{interp}[/dim]")

    # --- Missing headings ----------------------------------------------------
    if report.missing_headings:
        console.print()
        console.print("[bold]Sections AI cannot see:[/bold]")
        for h in report.missing_headings:
            console.print(f"  [red]x[/red] {h.text}  [dim](h{h.level})[/dim]")
    elif report.human_doc.word_count > 0 and not report.missing_headings:
        console.print()
        console.print("[green]All headings are visible to AI crawlers.[/green]")

    # --- Missing from raw HTML (rendering-gap headings) ----------------------
    if not no_render and report.raw_presence.missing_headings:
        console.print()
        console.print(
            "[bold]Sections missing from raw HTML "
            "(truly client-rendered):[/bold]"
        )
        for h in report.raw_presence.missing_headings:
            console.print(f"  [red]x[/red] {h.text}  [dim](h{h.level})[/dim]")

    # --- Condensed diff (always shown when there IS a diff) ------------------
    if report.visibility_score < 0.99:
        _render_condensed_diff(report, console)

    console.print()


def to_dict(report: VisibilityReport) -> dict[str, Any]:
    """Produce a JSON-serializable dict (drops the heavy markdown bodies).

    New fields in v0.2 (all additive, no removals):
    - raw_presence_score, gap_kind, raw_presence, interpretation
    """
    rp = report.raw_presence
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
        "raw_presence_score": round(report.raw_presence_score, 4),
        "gap_kind": report.gap_kind.value,
        "raw_presence": {
            "sentence_coverage": round(rp.sentence_coverage, 4),
            "sentences_checked": rp.sentences_checked,
            "sentences_found_in_raw": rp.sentences_found_in_raw,
            "heading_coverage": round(rp.heading_coverage, 4),
            "headings_checked": rp.headings_checked,
            "headings_found_in_raw": rp.headings_found_in_raw,
            "missing_headings": [
                {"level": h.level, "text": h.text}
                for h in rp.missing_headings
            ],
            "frameworks_detected": list(rp.frameworks_detected),
        },
        "interpretation": _interpretation(report),
        "warning": _status_warning(report.raw_status, report.render_status),
        "missing_headings": [
            {"level": h.level, "text": h.text} for h in report.missing_headings
        ],
    }


def render_json(report: VisibilityReport) -> str:
    return json.dumps(to_dict(report), indent=2, ensure_ascii=False)


def _get_diff_lines(report: VisibilityReport) -> list[str]:
    """Compute the unified diff lines between AI and human views."""
    return list(
        difflib.unified_diff(
            report.ai_doc.markdown.splitlines(),
            report.human_doc.markdown.splitlines(),
            fromfile="ai_view.md",
            tofile="human_view.md",
            lineterm="",
            n=2,
        )
    )


def _print_diff_line(line: str, console: Console) -> None:
    """Print a single diff line with appropriate coloring."""
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


def _render_condensed_diff(
    report: VisibilityReport, console: Console, max_lines: int = 15
) -> None:
    """Print a short preview of the content diff inside the main report."""
    diff_lines = _get_diff_lines(report)
    if not diff_lines:
        return

    console.print()
    console.print(
        "[bold]Content diff preview[/bold]  "
        "[dim](AI view vs Human view):[/dim]"
    )

    shown = 0
    total_printable = 0
    for line in diff_lines:
        # Skip the --- / +++ header in condensed mode
        if line.startswith("---") or line.startswith("+++"):
            continue
        total_printable += 1
        if shown < max_lines:
            _print_diff_line(line, console)
            shown += 1

    remaining = total_printable - shown
    if remaining > 0:
        console.print(
            f"  [dim]... {remaining} more lines. "
            f"Run with --show-diff to see the full diff.[/dim]"
        )


def render_diff(report: VisibilityReport, console: Console | None = None) -> None:
    """Print the full coloured unified diff of the AI view vs the human view.

    Green lines are present in the human view but not in the AI view
    (= what AI crawlers miss). Red lines are present in the AI view but
    not in the human view (usually trafilatura extraction noise, rare).
    """
    console = console or Console()
    diff_lines = _get_diff_lines(report)

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
        _print_diff_line(line, console)

    console.print()
    console.print(
        "[dim]Legend: [green]green[/green] = visible to humans but not AI "
        "(the visibility gap). [red]red[/red] = visible to AI but not "
        "humans (usually extraction noise).[/dim]"
    )
    console.print()


def render_raw_hits(
    report: VisibilityReport, console: Console | None = None
) -> None:
    """Print rendered sentences that are absent from the raw HTML bytes.

    These are the "rendering gap" contents — text that genuinely only
    exists after JavaScript execution. Up to 20 samples are shown.
    """
    console = console or Console()
    missing = report.raw_presence.missing_sentences

    console.print()
    console.rule(
        "[bold]Rendering-gap sentences[/bold]  "
        "[dim](absent from raw HTML bytes)[/dim]"
    )
    console.print()

    if not missing:
        console.print(
            "[dim]All rendered sentences were found in the raw HTML bytes.[/dim]"
        )
        console.print()
        return

    for i, s in enumerate(missing, 1):
        # Truncate long sentences for readability
        display = s[:120] + "..." if len(s) > 120 else s
        console.print(f"  [red]{i}.[/red] {display}", highlight=False)

    total_missing = report.raw_presence.sentences_checked - report.raw_presence.sentences_found_in_raw
    if total_missing > len(missing):
        console.print(
            f"\n  [dim]... and {total_missing - len(missing)} more "
            f"(showing first {len(missing)} of {total_missing})[/dim]"
        )

    console.print()


# --- HTML report -------------------------------------------------------------

_HTML_CSS = """\
  :root { --bg: #0f172a; --card: #1e293b; --border: #334155;
           --text: #e2e8f0; --muted: #94a3b8; --green: #22c55e;
           --red: #ef4444; --yellow: #eab308; --cyan: #06b6d4; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, -apple-system, sans-serif;
          background: var(--bg); color: var(--text); padding: 2rem;
          max-width: 960px; margin: 0 auto; line-height: 1.6; }
  h1 { font-size: 1.1rem; color: var(--muted); margin-bottom: 0.5rem; }
  h2 { font-size: 1rem; margin: 1.5rem 0 0.75rem; color: var(--cyan); }
  h3 { font-size: 0.9rem; margin: 1rem 0 0.5rem; }
  .url { font-size: 0.85rem; color: var(--cyan); word-break: break-all; }
  .card { background: var(--card); border: 1px solid var(--border);
           border-radius: 8px; padding: 1.25rem; margin: 1rem 0; }
  .scores { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
  .score-box { text-align: center; padding: 1rem; border-radius: 6px;
                background: var(--bg); }
  .score-box .number { font-size: 2rem; font-weight: 700; }
  .score-box .label { font-size: 0.75rem; color: var(--muted); margin-top: 0.25rem; }
  .help { font-size: 0.75rem; color: var(--muted); margin-top: 0.5rem;
           border-left: 2px solid var(--border); padding-left: 0.75rem; }
  .tag { display: inline-block; background: var(--border); color: var(--text);
          padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.8rem;
          margin: 0.5rem 0; }
  .gap-kind { font-size: 1.1rem; font-weight: 600; }
  .interp { color: var(--muted); font-size: 0.85rem; margin-top: 0.5rem; }
  .warning { background: #451a1a; border: 1px solid var(--red);
              border-radius: 6px; padding: 0.75rem; margin: 1rem 0;
              font-size: 0.85rem; color: var(--red); }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th, td { padding: 0.5rem 0.75rem; text-align: left;
            border-bottom: 1px solid var(--border); }
  th { color: var(--muted); font-weight: 600; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  .muted { color: var(--muted); }
  .missing { list-style: none; padding: 0; }
  .missing li::before { content: "\\2717 "; color: var(--red); }
  .missing li { margin: 0.25rem 0; font-size: 0.85rem; }
  .diff { background: var(--bg); border-radius: 6px; padding: 1rem;
           font-family: 'SF Mono', Consolas, monospace; font-size: 0.75rem;
           overflow-x: auto; max-height: 600px; overflow-y: auto; }
  .diff-add { color: var(--green); }
  .diff-del { color: var(--red); }
  .diff-hunk { color: var(--cyan); margin-top: 0.5rem; }
  .diff-meta { color: var(--muted); font-weight: 600; }
  .diff-ctx { color: var(--muted); }
  .meta { font-size: 0.8rem; color: var(--muted); }
  footer { margin-top: 2rem; padding-top: 1rem;
            border-top: 1px solid var(--border);
            font-size: 0.75rem; color: var(--muted); }"""


def render_html(report: VisibilityReport) -> str:
    """Produce a self-contained HTML report with inline CSS.

    The output is a single HTML file that can be opened in any browser,
    shared via email, attached to a GitHub issue, or embedded in a blog
    post. No external dependencies — all styles are inline.
    """
    e = html_mod.escape
    rp = report.raw_presence
    vis_pct = report.visibility_score * 100
    rp_pct = report.raw_presence_score * 100
    interp = _interpretation(report)
    warning = _status_warning(report.raw_status, report.render_status)

    # Build diff HTML
    diff_lines = _get_diff_lines(report)
    diff_html_lines: list[str] = []
    for line in diff_lines:
        escaped = e(line)
        if line.startswith("+++") or line.startswith("---"):
            diff_html_lines.append(f'<div class="diff-meta">{escaped}</div>')
        elif line.startswith("@@"):
            diff_html_lines.append(f'<div class="diff-hunk">{escaped}</div>')
        elif line.startswith("+"):
            diff_html_lines.append(f'<div class="diff-add">{escaped}</div>')
        elif line.startswith("-"):
            diff_html_lines.append(f'<div class="diff-del">{escaped}</div>')
        else:
            diff_html_lines.append(f'<div class="diff-ctx">{escaped}</div>')
    diff_block = "\n".join(diff_html_lines) if diff_html_lines else (
        '<p class="muted">No difference between AI and human views.</p>'
    )

    # Missing headings
    missing_h_html = ""
    if report.missing_headings:
        items = "".join(
            f"<li>{e(h.text)} <span class='muted'>(h{h.level})</span></li>"
            for h in report.missing_headings
        )
        missing_h_html = (
            f'<h3>Sections AI cannot see</h3><ul class="missing">{items}</ul>'
        )

    # Framework tag
    fw_html = ""
    if rp.frameworks_detected:
        fw_html = f'<div class="tag">Framework: {e(", ".join(rp.frameworks_detected))}</div>'

    # Warning
    warning_html = ""
    if warning:
        warning_html = f'<div class="warning">{e(warning)}</div>'

    gap_color = "#22c55e" if report.gap_kind == GapKind.NONE else "#eab308"

    css = _HTML_CSS  # defined above as a plain string (no f-string escaping)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>tulkki report — {e(report.url)}</title>
<style>
{css}
</style>
</head>
<body>

<h1>tulkki visibility report</h1>
<div class="url">{e(report.url)}</div>

{warning_html}

<div class="card">
  <div class="meta">
    Fetched at {e(report.fetched_at.isoformat(timespec='seconds'))} &middot;
    Raw {e(_format_bytes(report.raw_bytes))} ({e(report.raw_backend)}, HTTP {report.raw_status}) &middot;
    Rendered {e(_format_bytes(report.rendered_bytes))} ({e(report.render_backend)}, HTTP {report.render_status})
  </div>
  {fw_html}
</div>

<div class="scores">
  <div class="score-box card">
    <div class="number" style="color: {_score_color_hex(report.raw_presence_score)}">{rp_pct:.1f}%</div>
    <div class="label">Raw HTML coverage</div>
    <div class="help">{e(METRIC_HELP_PLAIN['raw_html_coverage'])}</div>
  </div>
  <div class="score-box card">
    <div class="number" style="color: {_score_color_hex(report.visibility_score)}">{vis_pct:.1f}%</div>
    <div class="label">Extractor visibility</div>
    <div class="help">{e(METRIC_HELP_PLAIN['extractor_visibility'])}</div>
  </div>
</div>

<div class="card">
  <div class="gap-kind" style="color: {gap_color}">{report.gap_kind.value.upper()}</div>
  <div class="interp">{e(interp)}</div>
  <div class="help" style="margin-top: 0.75rem">{e(METRIC_HELP_PLAIN['gap_kind'])}</div>
</div>

<h2>Views comparison</h2>
<div class="card">
  <table>
    <tr><th>View</th><th>Title</th><th class="num">Words</th><th class="num">Headings</th></tr>
    <tr>
      <td>Extracted (AI)</td>
      <td>{e(report.ai_doc.title or '—')}</td>
      <td class="num">{report.ai_doc.word_count:,}</td>
      <td class="num">{len(report.ai_doc.headings)}</td>
    </tr>
    <tr>
      <td>Rendered (Human)</td>
      <td>{e(report.human_doc.title or '—')}</td>
      <td class="num">{report.human_doc.word_count:,}</td>
      <td class="num">{len(report.human_doc.headings)}</td>
    </tr>
  </table>
</div>

<h2>Raw-bytes presence</h2>
<div class="card">
  <table>
    <tr><th></th><th class="num">Found</th><th class="num">Total</th><th class="num">Coverage</th></tr>
    <tr>
      <td>Sentences</td>
      <td class="num">{rp.sentences_found_in_raw}</td>
      <td class="num">{rp.sentences_checked}</td>
      <td class="num">{rp.sentence_coverage * 100:.1f}%</td>
    </tr>
    <tr>
      <td>Headings</td>
      <td class="num">{rp.headings_found_in_raw}</td>
      <td class="num">{rp.headings_checked}</td>
      <td class="num">{rp.heading_coverage * 100:.1f}%</td>
    </tr>
  </table>
</div>

{missing_h_html}

<h2>Content diff</h2>
<div class="card">
  <div class="diff">{diff_block}</div>
  <div class="help" style="margin-top: 0.75rem">
    <span style="color: var(--green)">Green</span> = visible to humans but not AI.
    <span style="color: var(--red)">Red</span> = visible to AI but not humans.
  </div>
</div>

<footer>
  Generated by <strong>tulkki {e(report.fetched_at.strftime('%Y-%m-%d %H:%M UTC'))}</strong>
  &middot; <a href="https://github.com/wcl-dev/tulkki" style="color: var(--cyan)">github.com/wcl-dev/tulkki</a>
</footer>

</body>
</html>"""
