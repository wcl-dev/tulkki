# tulkki

**An AI crawler visibility diagnostic for web pages.** A local CLI that
fetches a URL twice — once without JavaScript (what AI crawlers see) and
once with JavaScript (what humans see) — then tells you which sections
are invisible to AI, with a score and two side-by-side Markdown files
you can commit to git.

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

Google quietly cut Googlebot's HTML budget from 15 MB to 2 MB in
February 2026. None of the major LLM crawlers (GPTBot, ClaudeBot,
PerplexityBot, Google-Extended) execute JavaScript. If your important
content lives behind hydration, your page is invisible to the search
engines that are increasingly answering questions before users ever
click.

Existing tools in this space all do one of two things:

- **Score-only hosted checkers** ([amivisibleonai](https://www.amivisibleonai.com/),
  [llmrefs](https://llmrefs.com/tools/ai-crawl-checker), and ~6 others)
  give you a number and recommendations. They do not show you the
  actual content AI crawlers see, do not compare it to the rendered
  view, and you cannot run them in a script.
- **General URL→Markdown converters** ([crawl4ai](https://github.com/unclecode/crawl4ai),
  [firecrawl](https://github.com/firecrawl/firecrawl),
  [trafilatura](https://github.com/adbar/trafilatura)) give you a
  Markdown body but do not diff anything.

tulkki is the only tool that produces **both** Markdown views and a
diff. It is built for developers and content engineers, runs locally
with no API keys, and outputs files you can:

- Commit to a git repository
- `diff` against a previous version to see how a change affected AI
  visibility
- Attach to a pull request so reviewers can see "this PR drops AI
  visibility from 80 % to 50 %"
- Run inside GitHub Actions / any continuous-integration pipeline,
  using `--quiet --fail-below 80` to gate merges

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

## Architecture

tulkki is built on a small Protocol-based core so the heavy lifting can
be delegated to existing tools as backends:

| Layer | Default | Optional backends |
|---|---|---|
| Raw fetch (AI view) | `httpx` | `hrequests` |
| JS render (human view) | `playwright` | `patchright` |
| Combined backend | — | `crawl4ai`, `firecrawl` |
| Content extraction | `trafilatura` | — |

The default install gives you a working tool with no extra setup.
Advanced users can install extras (`pipx install "tulkki[crawl4ai]"`)
and switch backends with `--raw-fetcher`, `--renderer`, or `--backend`.

## License

MIT
