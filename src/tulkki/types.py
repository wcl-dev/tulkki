"""Core data structures shared across modules.

These dataclasses are the contract between fetchers, extractors, the diff
engine, and the report renderer. Nothing here imports any backend-specific
package, so the layer is safe to depend on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class FetchResult:
    """Result of fetching a URL via either the raw or rendering side."""

    url: str
    html: str
    status_code: int
    bytes_size: int
    fetched_at: datetime
    elapsed_ms: int
    backend: str


@dataclass(frozen=True)
class Heading:
    level: int
    text: str


@dataclass(frozen=True)
class ExtractedDoc:
    """Output of running an extractor over fetched HTML."""

    title: str | None
    markdown: str
    headings: tuple[Heading, ...]
    word_count: int

    @property
    def heading_set(self) -> frozenset[tuple[int, str]]:
        return frozenset((h.level, h.text) for h in self.headings)


@dataclass(frozen=True)
class VisibilityReport:
    """The full diagnostic — what tulkki ultimately produces."""

    url: str
    fetched_at: datetime
    raw_bytes: int
    rendered_bytes: int
    ai_doc: ExtractedDoc
    human_doc: ExtractedDoc
    raw_backend: str
    render_backend: str
    raw_status: int
    render_status: int
    visibility_score: float
    missing_headings: tuple[Heading, ...]
    elapsed_raw_ms: int
    elapsed_render_ms: int
