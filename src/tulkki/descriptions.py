"""Metric descriptions shared between the terminal report, HTML report,
and the ``tulkki explain`` command.

Single source of truth — edit here, both outputs stay in sync.
"""

EXTRACTOR_VISIBILITY = (
    "What fraction of the human-visible content a standard extractor "
    "(trafilatura) can recover from the raw HTML — without running "
    "JavaScript.\n\n"
    "This represents what Common Crawl WET files, readability.js, "
    "and most content-extraction pipelines would actually see. If "
    "your page scores 100%, tools that strip HTML boilerplate can "
    "already read everything. If it scores 5%, they see almost "
    "nothing.\n\n"
    "This is the number that --fail-below checks."
)

RAW_HTML_COVERAGE = (
    "What fraction of the human-visible content can be found as "
    "literal text inside the raw HTML bytes — before any extraction "
    "or JavaScript.\n\n"
    "This is the upper bound of what any AI crawler could possibly "
    "see, including training pipelines that tokenize raw HTML "
    "directly (script tags included). A high number means the "
    "content IS in the bytes; a low number means it genuinely "
    "requires JavaScript to appear.\n\n"
    "This is the number that --fail-below-raw checks."
)

GAP_KIND = (
    "Gap kind classifies why content is missing. "
    "'NONE' = AI sees everything. "
    "'EXTRACTION' = content is in the HTML bytes but extractors can't "
    "unpack it (e.g. locked inside framework data structures). "
    "'RENDERING' = content only exists after JavaScript execution. "
    "'MIXED' = both problems are present. "
    "'BLOCKED' = HTTP error, scores are meaningless."
)

GAP_KIND_DETAILED = (
    "NONE — Both scores are high. AI crawlers see "
    "the same content as human users. No action needed.\n\n"
    "EXTRACTION — Content is physically present in "
    "the raw HTML bytes (high raw coverage) but standard extractors "
    "cannot unpack it (low extractor visibility). Typical cause: "
    "content locked inside framework data structures like Next.js "
    "RSC flight data. LLMs trained on raw HTML may see it; LLMs "
    "trained on Common Crawl WET will not.\n\n"
    "RENDERING — Content is genuinely absent from "
    "the raw HTML (low raw coverage) and only appears after "
    "JavaScript execution. This is classic client-side rendering. "
    "No AI crawler that skips JS will see it.\n\n"
    "MIXED — Both extraction and rendering gaps "
    "are present. Some content is locked in framework data "
    "structures, and some is truly client-rendered.\n\n"
    "BLOCKED — One or both HTTP fetches returned an "
    "error (403, 401, 5xx, timeout). Scores are meaningless."
)

CONTENT_DIFF = (
    "A line-by-line comparison of the AI-extracted markdown versus "
    "the human-extracted markdown.\n\n"
    "Green lines = content visible to humans but "
    "not to AI (the visibility gap).\n"
    "Red lines = content visible to AI but not humans "
    "(usually extraction noise — rare).\n\n"
    "The main report shows a condensed preview (first 15 lines). "
    "Use --show-diff to see the full diff."
)

FRAMEWORK_DETECTION = (
    "tulkki scans the raw HTML for signatures of common JavaScript "
    "frameworks (Next.js RSC, Next.js Pages, Nuxt, SvelteKit, "
    "Gatsby, Remix). When detected, the interpretation paragraph "
    "names the specific framework so you know exactly what kind of "
    "packaging is hiding the content."
)

CJK_SUPPORT = (
    "tulkki handles Chinese, Japanese, and Korean (CJK) pages. Word "
    "counts treat each ideograph, kana, or syllable block as one word "
    "(since CJK scripts don't use spaces between words). Sentence "
    "splitting recognises full-width punctuation (。！？；) and uses a "
    "shorter minimum length (15 characters) for CJK sentences than for "
    "Latin sentences (45 characters) — CJK is information-denser, so "
    "shorter strings carry real content rather than UI boilerplate."
)

# Plain-text versions for HTML report (no rich markup)
METRIC_HELP_PLAIN = {
    "raw_html_coverage": (
        "Raw HTML coverage measures what fraction of the human-visible "
        "content can be found as literal text inside the raw HTML bytes "
        "(before any JavaScript runs). This represents the upper bound of "
        "what any AI crawler could possibly see — including training "
        "pipelines that tokenize raw HTML directly."
    ),
    "extractor_visibility": (
        "Extractor visibility measures what fraction of the human-visible "
        "content is recovered by a standard boilerplate-stripping extractor "
        "(trafilatura). This represents what tools like Common Crawl's WET "
        "files, readability.js, and most content-extraction pipelines would "
        "actually see."
    ),
    "gap_kind": GAP_KIND,
    "cjk_support": CJK_SUPPORT,
}
