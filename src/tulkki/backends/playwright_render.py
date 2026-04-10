"""Playwright-based rendering fetcher — the default 'human view'.

Spins up a headless Chromium, waits for the DOM to be parsed plus a
short hydration window, then returns the post-JS DOM as HTML.

We do NOT use 'networkidle' here. Most modern news / commerce sites
keep ads, analytics and tracking pixels firing indefinitely, so the
network never becomes idle and Playwright would hang until the goto
timeout. 'domcontentloaded' fires as soon as the HTML parser is done,
which is the correct moment for our purpose; the explicit settle delay
afterwards gives client-side JS a chance to hydrate the visible content.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from ..types import FetchResult

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class PlaywrightRenderer:
    name = "playwright"

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_ms: int = 30_000,
        settle_ms: int = 2_500,
    ) -> None:
        self._user_agent = user_agent
        self._timeout_ms = timeout_ms
        self._settle_ms = settle_ms

    def fetch(self, url: str) -> FetchResult:
        started = time.perf_counter()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            html = ""
            final_url = url
            status = 0
            try:
                context = browser.new_context(user_agent=self._user_agent)
                page = context.new_page()
                try:
                    response = page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self._timeout_ms,
                    )
                    if response is not None:
                        status = response.status
                except PlaywrightError:
                    # Even if goto times out (slow analytics, hung tracker),
                    # the DOM is usually populated. Keep going and grab
                    # whatever we have.
                    pass

                # Give client-side JS a moment to hydrate the visible
                # content before we snapshot the DOM.
                try:
                    page.wait_for_timeout(self._settle_ms)
                except PlaywrightError:
                    pass

                try:
                    html = page.content()
                    final_url = page.url
                except PlaywrightError:
                    pass
            finally:
                browser.close()

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return FetchResult(
            url=final_url,
            html=html,
            status_code=status,
            bytes_size=len(html.encode("utf-8")),
            fetched_at=datetime.now(timezone.utc),
            elapsed_ms=elapsed_ms,
            backend=self.name,
        )
