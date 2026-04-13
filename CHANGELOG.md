# Changelog

All notable changes to tulkki will be documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-04-10

### Added

- **Three-view model.** tulkki now analyses three perspectives of a URL
  instead of two: raw HTML bytes (new), extracted (trafilatura from no-JS
  HTML), and rendered (trafilatura from post-JS DOM). This separates two
  different AI-visibility failure modes that v0.1 conflated.
- **New score: `raw_presence_score`.** Measures what fraction of the
  human-visible content can be found as literal text inside the raw HTML
  bytes via sentence-level substring search. Represents the upper bound
  of visibility for AI crawlers that tokenize raw HTML directly.
- **Gap classification (`gap_kind`).** Five-way classification derived from
  the two scores plus HTTP status: `NONE`, `EXTRACTION`, `RENDERING`,
  `MIXED`, `BLOCKED`. The terminal report and HTML report both surface this
  with an interpretation paragraph.
- **Framework detection.** Substring-based detection of seven common
  JavaScript framework signatures (Next.js RSC, Next.js Pages, Nuxt,
  SvelteKit, Gatsby, Remix, React Helmet). Detected frameworks appear in
  the report and feed into the interpretation text.
- **`--html` flag.** Emits a self-contained HTML report with inline CSS —
  can be opened in any browser, shared via email, or attached to a GitHub
  issue. Dark-themed with scores, views comparison, raw-bytes presence
  table, full content diff, and inline metric explanations.
- **`--show-diff` flag (promoted to default preview).** The terminal report
  now automatically includes a 15-line condensed content diff whenever
  visibility is below 100%. The full diff remains available via
  `--show-diff`.
- **`--show-raw-hits` flag.** Prints up to 20 rendered sentences that are
  absent from the raw HTML bytes — the true rendering-gap content.
- **`--fail-below-raw` flag.** CI threshold for `raw_presence_score`,
  complementing `--fail-below` for `visibility_score`.
- **`tulkki explain` subcommand.** Plain-English explanation of every metric
  in a tulkki report — no documentation lookup required.
- **Test suite.** First CLI-layer tests via `typer.testing.CliRunner`,
  bringing the total from 11 tests in v0.1 to 49 in v0.2. Added
  `tests/fixtures/` with three HTML samples (Next.js RSC, plain article,
  pure CSR SPA) for regression coverage.

### Changed

- **Terminal report layout.** Two-row scores block (Raw HTML coverage /
  Extractor visibility) replaces the single score line. Added Framework
  row to the metadata table, a "Raw-bytes presence" block, and a Gap kind
  + interpretation section.
- **`_missing_headings` deduplication.** Repeated headings on the human
  side are deduplicated before comparison, so pages that legitimately
  repeat section titles (e.g. the OpenAI Codex "Anecdotes from our teams"
  pattern) no longer report duplicates as missing.
- **httpx error handling.** Network failures (DNS, TLS, timeouts) now
  produce a degenerate `FetchResult` with `status_code=0` and trigger the
  existing blocked-fetch warning, instead of crashing with a traceback.
- **Advanced backends clear errors.** `--raw-fetcher hrequests` and
  `--renderer patchright` now raise `NotImplementedError` with a clear
  message instead of an opaque `ModuleNotFoundError`.
- **File-naming collision fix.** `_slug()` now appends an 8-char SHA-1
  hash so URLs with the same host+path (different queries, fragments, or
  tails beyond 80 chars) don't overwrite each other's outputs.

### Fixed

- Score color bands (`_score_color` / `_score_color_hex`) consolidated into
  a single `_SCORE_BANDS` table — thresholds no longer diverge between
  terminal and HTML rendering.
- Metric descriptions consolidated in `descriptions.py` as a single source
  of truth for the `explain` subcommand and HTML report help text.
- Unicode punctuation normalization (curly quotes, em-dashes) added to the
  raw-bytes haystack so trafilatura's output matches raw HTML reliably.
- Condensed diff's "N more lines" counter now reflects actual skipped
  content (previously off by 2).

### Known limitations

- CJK (Chinese, Japanese, Korean) word counting and sentence splitting are
  inaccurate — scheduled for v0.2.1.
- Default User-Agent may be blocked by Cloudflare on some sites; a
  `--as-bot gptbot` flag is scheduled for v0.2.1.
- `raw_presence_score` can undercount on list-heavy pages due to heuristic
  sentence splitting. Gap classification intentionally de-prioritizes this
  score when `visibility_score` is high to avoid false positives.

## [0.1.0] — 2026-04-08

### Added

- Initial release.
- `tulkki check URL` — fetch no-JS and post-JS views, extract with
  trafilatura, compare, output a single `visibility_score` plus a list of
  sections missing from the AI view.
- `--json`, `--quiet`, `--fail-below`, `--no-render`, `--no-save` flags.
- Protocol-based fetcher and extractor architecture (`protocols.py`).
- Default stack: httpx + Playwright Chromium + trafilatura + rich + typer.
- 11 unit tests covering scoring, heading extraction, and word counting.
