# tulkki

*See your site through an AI crawler's eyes.*

A local CLI that fetches a URL three ways — as raw HTML bytes, as the content a standard extractor recovers, and as a rendered browser DOM — and tells you which AI crawlers will see your content, which won't, and why.

```
$ tulkki check https://www.anthropic.com/economic-index

─────── tulkki check  https://www.anthropic.com/economic-index ───────

  URL             https://www.anthropic.com/economic-index
  Raw HTML        2.65 MB  (httpx, HTTP 200, 2166 ms)
  Rendered HTML   14.07 MB  (playwright, HTTP 200, 15696 ms)
  Framework       nextjs-rsc

  View          Title                              Words   Headings
  Extracted     Anthropic Economic Index              53          0
  Rendered      Anthropic Economic Index             689          4

  Raw-bytes presence  (substring search of raw HTML):
    Sentences:   8/20  (40.0%)
    Headings:    1/4   (25.0%)

  Raw HTML coverage:    40.0%  [!]   (AI crawlers tokenizing raw HTML bytes)
  Extractor visibility: 5.4%   [!]   (trafilatura / Common Crawl WET / readability.js)

  Gap kind: MIXED
  Both extraction and rendering gaps are present. Some content is locked
  inside framework data structures in the raw HTML, and some content
  only appears after JavaScript execution.
```

## Why tulkki

AI visibility is **not one thing** — it's three different thresholds:

1. **Is the content physically in the raw HTML bytes?** (What any pipeline tokenizing HTML directly would see.)
2. **Can a standard extractor recover it?** (What Common Crawl WET files, readability.js, and most content pipelines actually see.)
3. **Is the rendered DOM the only place it lives?** (What browsers — and AI crawlers that execute JavaScript — see.)

Different AI systems use different pipelines. A page can be 100% visible to one, 5% visible to another, and invisible to a third — **on the same URL**. Without a tool that measures all three layers, you can't give actionable advice, and you can't tell whether the problem is your framework, your rendering strategy, or your robots.txt.

Most existing tools answer the wrong question:

- **SEO checkers** (Screaming Frog, Ahrefs) assume Googlebot renders JS, so they measure search rank, not AI visibility.
- **Content extractors** (trafilatura, readability.js, Mercury) extract once and give you one result — they don't tell you what's missing or why.
- **Headless-browser scripts** give you raw bytes but no diagnosis.
- **"AI-ready" score widgets** give a single number with no explanation.

tulkki fills the gap: a small, auditable, reproducible CLI that runs locally (no API keys), outputs a two-score diagnosis with a classification, and produces a shareable HTML report you can attach to a PR or hand to a client.

## Install

tulkki is not yet on PyPI. Install from source with [uv](https://docs.astral.sh/uv/):

```sh
git clone https://github.com/wcl-dev/tulkki
cd tulkki
uv sync
uv run playwright install chromium
uv run tulkki check https://example.com
```

Playwright's Chromium is ~108 MB and only needs installing once per machine. A PyPI release is planned once the API stabilises.

## Usage

### Basic

```sh
# Terminal report + two markdown files (AI view + human view) to ./tulkki-out/
tulkki check https://example.com

# Add a self-contained HTML report
tulkki check https://example.com --html

# See the full line-by-line content diff (AI view vs rendered view)
tulkki check https://example.com --show-diff

# List sentences only the human can see (the true rendering gap)
tulkki check https://example.com --show-raw-hits
```

### CI / automation

```sh
# One number to stdout — the extractor visibility score
tulkki check https://example.com --quiet
# -> 5.4

# Exit 1 if extractor visibility drops below 80%
tulkki check https://example.com --quiet --fail-below 80

# Also fail if raw HTML coverage drops below 60%
tulkki check https://example.com --quiet \
  --fail-below 80 --fail-below-raw 60

# Machine-readable JSON for pipelines
tulkki check https://example.com --json
```

### Learning the tool

```sh
# Plain-English explanation of every metric in the report
tulkki explain

# Skip the JS render side (useful when debugging the AI view alone)
tulkki check https://example.com --no-render
```

## What the scores mean

tulkki reports **two scores** and a **gap classification**. Run `tulkki explain` for the full breakdown; the short version:

### Extractor visibility (`visibility_score`)

What fraction of the human-visible content a standard boilerplate-stripping extractor (trafilatura) recovers from the raw HTML, without running JavaScript. Represents the view of Common Crawl WET files, readability.js, and most AI training pipelines that rely on pre-extracted text.

This is the number `--fail-below` checks. Formula: `0.7 × word_coverage + 0.3 × heading_coverage`.

### Raw HTML coverage (`raw_presence_score`)

What fraction of the human-visible content can be found as literal text inside the raw HTML bytes, via sentence-level substring search — before any extraction or JavaScript. Represents the upper bound of what any AI crawler could possibly see, including pipelines that tokenize raw HTML bytes (script tags included).

This is the number `--fail-below-raw` checks.

### Gap kind

Five classifications derived from the two scores:

| Gap kind | Meaning | Action |
|---|---|---|
| **NONE** | Both scores high. | No action needed. |
| **EXTRACTION** | Content is in the raw HTML but extractors can't unpack it. | Usually framework-specific (Next.js RSC, Nuxt, etc.). A smarter extractor would recover it; WET-based pipelines won't. |
| **RENDERING** | Content only exists after JavaScript. | Classic client-side rendering. No JS-less crawler will see it. Add SSR, prerendering, or `<noscript>` fallbacks. |
| **MIXED** | Both gaps are present. | Some content is framework-locked, some is genuinely client-rendered. Check the diff to see which is which. |
| **BLOCKED** | HTTP error (403, 401, 5xx, 0). | Scores are meaningless. Often a Cloudflare block on unknown User-Agents. |

### Framework detection

When the raw HTML contains known framework signatures (`self.__next_f` for Next.js 13 RSC, `__NEXT_DATA__` for Next.js Pages, `window.__NUXT__`, `__remixContext`, `data-react-helmet`, `__sveltekit`, `window.___gatsby`), tulkki names them in the report so you can see exactly what kind of packaging is hiding the content.

## Architecture

```
┌─────────────┐   trafilatura   ┌─────────────┐
│  httpx      │────────────────▶│  Extracted  │◀── visibility_score
│  (raw HTML) │                 │  view       │    (boilerplate extractor)
│      │                                            
│      │ substring search
│      ▼                                            
│   raw_presence_score                              
│      ▲                                            
│      │                                            
│  ┌───┴──────┐  trafilatura  ┌─────────────┐      
│  │ Playwright│──────────────▶│  Rendered  │◀── ground truth (human)
│  │ (post-JS) │                │  view      │      
│  └───────────┘                └─────────────┘      
```

Everything is Protocol-based so fetchers and extractors can be swapped. Default stack:

| Layer | Implementation |
|---|---|
| Raw HTML (no JS) | [httpx](https://www.python-httpx.org/) |
| Rendered HTML (post-JS) | [Playwright](https://playwright.dev/python/) Chromium |
| Content extraction | [trafilatura](https://github.com/adbar/trafilatura) |
| Terminal rendering | [rich](https://github.com/Textualize/rich) |
| CLI | [typer](https://typer.tiangolo.com/) |

The `--raw-fetcher` and `--renderer` flags accept alternative backends. Additional backends (`hrequests`, `patchright`, `crawl4ai`, `firecrawl`) are declared in `pyproject.toml` as optional extras but not yet implemented — selecting them raises a clear `NotImplementedError`.

## Known limitations

1. **CJK not yet supported.** The word-count and sentence-splitting logic assumes Latin punctuation and space-separated words. Chinese/Japanese/Korean content will score inaccurately. Planned for v0.2.1.
2. **Default User-Agent is tulkki-specific.** Sites with strict bot protection (Cloudflare) may return 403 to tulkki but not to GPTBot/ClaudeBot, which are typically whitelisted. A `--as-bot gptbot` flag is planned for v0.2.1.
3. **Not suitable for homepages or list pages.** trafilatura needs a main content body to extract; homepages, news front pages, and category listings will produce low-signal results. Use tulkki on individual article, product, or documentation pages.
4. **`raw_presence_score` sentence-splitting is heuristic.** On pages with heavy list content, non-standard punctuation, or embedded numeric data, the score may underestimate actual presence. The `gap_kind` classification intentionally de-prioritizes `raw_presence_score` when `visibility_score` is high, so this doesn't produce false positives.

## Roadmap

| Version | Focus |
|---|---|
| v0.1 | Two-view diagnostic (completed) |
| **v0.2 (current)** | Three-view model, gap classification, framework detection, HTML report, `explain` command |
| v0.2.1 | CJK support, `--as-bot` flag, README improvements |
| v0.3 | `tulkki scan` batch mode for sitemaps and URL lists — statistical reports across many pages |
| v0.4 | Historical tracking, CI regression alerts |
| v0.5 | Multi-extractor comparison (trafilatura vs readability-lxml vs Mercury) |

## Development

```sh
git clone https://github.com/wcl-dev/tulkki
cd tulkki
uv sync
uv run playwright install chromium
uv run pytest tests/    # 49 tests
```

To add a new backend, implement the `Fetcher` or `Extractor` protocol from `src/tulkki/protocols.py` and register it in `src/tulkki/backends/__init__.py`.

## License

MIT
