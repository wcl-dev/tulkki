"""tulkki CLI entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import typer
from rich.console import Console

# Force UTF-8 on stdout/stderr so the rich-rendered report doesn't crash on
# Windows consoles whose default codepage (cp950 / cp1252 / cp936) cannot
# encode the symbols we use. errors="replace" turns any leftover unencodable
# byte into '?' instead of raising.
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from .backends import get_raw_fetcher, get_rendering_fetcher
from .diff import compare
from .extractor import TrafilaturaExtractor
from .report import render_diff, render_json, render_raw_hits, render_terminal
from .types import VisibilityReport

app = typer.Typer(
    help="AI crawler visibility diagnostic for web pages.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _root() -> None:
    """tulkki — AI crawler visibility diagnostic for web pages.

    Compare what AI crawlers see (no JS) vs what humans see (post-JS) for
    any URL, and produce two markdown files plus a visibility score.
    """


def _slug(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.replace(":", "_") or "page"
    path = parsed.path.strip("/").replace("/", "_") or "index"
    slug = f"{host}_{path}"
    # Keep filenames sane
    return slug[:80].rstrip("._")


def _save_markdowns(
    report: VisibilityReport, out_dir: Path
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = _slug(report.url)
    ai_path = out_dir / f"{base}_ai.md"
    human_path = out_dir / f"{base}_human.md"
    ai_path.write_text(report.ai_doc.markdown, encoding="utf-8")
    human_path.write_text(report.human_doc.markdown, encoding="utf-8")
    return ai_path, human_path


@app.command()
def check(
    url: str = typer.Argument(..., help="The URL to diagnose."),
    out: Path = typer.Option(
        Path("./tulkki-out"),
        "--out",
        "-o",
        help="Directory to write the AI and human markdown files.",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Print machine-readable JSON instead of a report."
    ),
    no_render: bool = typer.Option(
        False,
        "--no-render",
        help="Skip the JS render side; only produce the AI crawler view.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Print only the visibility score (one line)."
    ),
    fail_below: Optional[float] = typer.Option(
        None,
        "--fail-below",
        help="Exit non-zero if visibility_score (0–100) is below this threshold.",
    ),
    raw_fetcher: str = typer.Option(
        "httpx",
        "--raw-fetcher",
        help="Backend for the AI crawler view (no JS).",
    ),
    renderer: str = typer.Option(
        "playwright",
        "--renderer",
        help="Backend for the human view (with JS).",
    ),
    no_save: bool = typer.Option(
        False, "--no-save", help="Don't write markdown files to disk."
    ),
    show_diff: bool = typer.Option(
        False,
        "--show-diff",
        help="Print a unified diff of the AI view vs the human view "
        "after the report.",
    ),
    fail_below_raw: Optional[float] = typer.Option(
        None,
        "--fail-below-raw",
        help="Exit non-zero if raw_presence_score (0–100) is below this "
        "threshold. Use alongside --fail-below to catch both extraction-gap "
        "and rendering-gap regressions in CI.",
    ),
    show_raw_hits: bool = typer.Option(
        False,
        "--show-raw-hits",
        help="Print up to 20 rendered sentences absent from the raw HTML "
        "bytes (the rendering-gap content).",
    ),
) -> None:
    """Diagnose how much of a page is invisible to AI crawlers."""

    # Status messages go to stderr so that --json / --quiet stdout stays
    # clean for pipes. The main report goes to stdout via out_console.
    err = Console(stderr=True)
    out_console = Console()
    extractor = TrafilaturaExtractor()

    raw = get_raw_fetcher(raw_fetcher)
    if not quiet and not json_output:
        err.print(f"[dim]-> raw fetch ({raw.name})...[/dim]", highlight=False)
    raw_result = raw.fetch(url)
    ai_doc = extractor.extract(raw_result.html, url=url)

    if no_render:
        # Build a degenerate "human" doc identical to the AI one so the
        # downstream code path stays uniform. The score will be 100 %.
        human_doc = ai_doc
        rendered_result = raw_result
    else:
        rend = get_rendering_fetcher(renderer)
        if not quiet and not json_output:
            err.print(
                f"[dim]-> rendered fetch ({rend.name})...[/dim]",
                highlight=False,
            )
        rendered_result = rend.fetch(url)
        human_doc = extractor.extract(rendered_result.html, url=url)

    report = compare(raw_result, rendered_result, ai_doc, human_doc)

    if not no_save:
        ai_path, human_path = _save_markdowns(report, out)
    else:
        ai_path = human_path = None

    if json_output:
        typer.echo(render_json(report))
    elif quiet:
        typer.echo(f"{report.visibility_score * 100:.1f}")
    else:
        render_terminal(report, console=out_console, no_render=no_render)
        if ai_path is not None and human_path is not None:
            out_console.print(
                f"[dim]Outputs saved:[/dim]\n"
                f"  {ai_path}    [dim]({report.ai_doc.word_count:,} words)[/dim]\n"
                f"  {human_path}  [dim]({report.human_doc.word_count:,} words)[/dim]\n"
            )
        if show_diff:
            render_diff(report, console=out_console)
        if show_raw_hits:
            render_raw_hits(report, console=out_console)

    exit_code = 0
    if fail_below is not None and report.visibility_score * 100 < fail_below:
        exit_code = 1
    if fail_below_raw is not None and report.raw_presence_score * 100 < fail_below_raw:
        exit_code = 1
    if exit_code:
        raise typer.Exit(code=exit_code)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
