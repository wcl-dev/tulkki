"""Protocol definitions for swappable backends.

A `Fetcher` is anything that can take a URL and return a `FetchResult`.
The same protocol is used for both the raw side (no JS, AI crawler view)
and the rendering side (post-JS, human view); the CLI layer wires up
two distinct instances. An `Extractor` turns HTML into an `ExtractedDoc`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import ExtractedDoc, FetchResult


@runtime_checkable
class Fetcher(Protocol):
    """Fetches a URL and returns the resulting HTML + metadata."""

    name: str

    def fetch(self, url: str) -> FetchResult: ...


@runtime_checkable
class Extractor(Protocol):
    """Turns raw HTML into a clean ExtractedDoc."""

    name: str

    def extract(self, html: str, url: str | None = None) -> ExtractedDoc: ...
