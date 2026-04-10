# tulkki

**An AI crawler visibility diagnostic for web pages.** A local CLI that
fetches a URL twice — once without JavaScript (what many crawlers see) and
once with JavaScript (what humans see) — then tells you which sections
differ, with a score and two side-by-side Markdown files you can commit to
git.

```
$ tulkki check https://docs.anthropic.com/en/docs/intro

  URL              https://platform.claude.com/docs/en/intro
  Raw HTML         314.0 KB  (httpx, 917 ms)
  Rendered HTML    301.1 KB  (playwright, 4327 ms)

  View          Title              Words    Headings
  AI crawler    Intro to Claude      375           0
  Human         Intro to Claude      337           5

Visibility score:  70.0%  [!]

Sections AI cannot see:
  x Intro to Claude  (h1)
  x Recommended path for new developers  (h2)
  x Develop with Claude  (h2)
  x Key capabilities  (h2)
  x Support  (h2)

Outputs saved:
  ./tulkki-out/platform.claude.com_docs_en_intro_ai.md     (375 words)
  ./tulkki-out/platform.claude.com_docs_en_intro_human.md  (337 words)
```

## Why tulkki

Major LLM and search crawlers (e.g. GPTBot, ClaudeBot, PerplexityBot,
Google-Extended) **do not execute JavaScript**. Crawl budgets and bot
behavior also change over time. If your important copy lives only after
hydration or client-side rendering, automated fetches may not match what
users see in a browser.

Other tools tend to fall into two buckets:

- **Hosted score checkers** (e.g. [amivisibleonai](https://www.amivisibleonai.com/),
  [llmrefs](https://llmrefs.com/tools/ai-crawl-checker)) give a number and
  tips but do not ship two comparable Markdown bodies you can diff or
  commit.
- **URL→Markdown libraries** ([crawl4ai](https://github.com/unclecode/crawl4ai),
  [firecrawl](https://github.com/firecrawl/firecrawl),
  [trafilatura](https://github.com/adbar/trafilatura)) turn a page into
  Markdown but do not build the **no-JS vs post-JS** pair or a visibility
  score out of the box.

tulkki is aimed at developers and content engineers: it runs **locally**
with **no API keys**, outputs **AI-view and human-view Markdown**, optional
unified diff, and CI-friendly flags so you can:

- Commit outputs to git
- `diff` runs to see how a deploy changed crawler-visible content
- Attach artifacts to a pull request (e.g. “visibility dropped from 80 % to 50 %”)
- Gate merges with `--quiet --fail-below 80` (and `--fail-below-raw` when needed)

## Install

```sh
pipx install tulkki
playwright install chromium
```

## Usage

```sh
# Default: print a report and save two Markdown files to ./tulkki-out/
tulkki check https://example.com

# Machine-readable JSON
tulkki check https://example.com --json

# One-line score, for shell pipelines
tulkki check https://example.com --quiet
# -> 78.7

# Gate a CI job: exit non-zero if visibility drops below 80 %
tulkki check https://example.com --quiet --fail-below 80

# Skip the JS render side (debugging the AI view in isolation)
tulkki check https://example.com --no-render
```

## How the score works

```
score = 0.7 * word_coverage + 0.3 * heading_coverage
```

where `word_coverage` is `min(1.0, ai_words / human_words)` and
`heading_coverage` is the fraction of human-view headings that also
appear in the AI view, matched on `(level, text)`. The blend means a
page can score below 100 % even when AI sees the same word count as
humans, if the heading structure was lost to JavaScript hydration.

## Architecture (v0.1)

tulkki uses a small Protocol-based core so fetchers and extractors can be
swapped in code. **In this release, only the defaults below are wired end-to-end.**

| Layer | Implementation |
| --- | --- |
| Raw HTML (no JS, “AI crawler” view) | [httpx](https://www.python-httpx.org/) — `--raw-fetcher httpx` |
| Rendered HTML (post-JS, “human” view) | [Playwright](https://playwright.dev/python/) — `--renderer playwright` |
| Main content extraction | [trafilatura](https://github.com/adbar/trafilatura) |

The CLI exposes `--raw-fetcher` and `--renderer` so alternative backends can
be added without changing the command surface.

**Roadmap (not implemented yet):** optional raw fetchers (`hrequests`),
renderers (`patchright`), and combined stacks (`crawl4ai`, `firecrawl`) are
hinted at in `pyproject.toml` optional dependency groups for future work;
choosing those names today will raise until those backends are implemented.
There is **no** single `--backend` switch — the two sides are configured
independently.

Run `tulkki explain` for metric definitions, or `tulkki check URL --html` for a
self-contained HTML report.

## License

MIT
