"""httpx-based raw fetcher — the default 'AI crawler view'.

This is intentionally a plain HTTP GET with a recognisable AI bot user
agent. We do NOT execute JavaScript here — that's the whole point of the
'AI crawler view'. Most LLM crawlers (GPTBot, ClaudeBot, PerplexityBot,
Google-Extended) operate the same way.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

from ..types import FetchResult

# A neutral, identifiable AI-bot-like user agent. We don't impersonate any
# specific bot to avoid sites blocking us via UA rules; the goal is to
# produce a fetch that resembles what JS-less crawlers experience.
DEFAULT_UA = (
    "Mozilla/5.0 (compatible; tulkki/0.1; "
    "+https://github.com/tulkki) AI-visibility-diagnostic"
)


class HttpxRawFetcher:
    name = "httpx"

    def __init__(self, user_agent: str = DEFAULT_UA, timeout: float = 30.0) -> None:
        self._user_agent = user_agent
        self._timeout = timeout

    def fetch(self, url: str) -> FetchResult:
        started = time.perf_counter()
        with httpx.Client(
            follow_redirects=True,
            timeout=self._timeout,
            headers={"User-Agent": self._user_agent, "Accept": "text/html,*/*"},
        ) as client:
            resp = client.get(url)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        return FetchResult(
            url=str(resp.url),
            html=resp.text,
            status_code=resp.status_code,
            bytes_size=len(resp.content),
            fetched_at=datetime.now(timezone.utc),
            elapsed_ms=elapsed_ms,
            backend=self.name,
        )
