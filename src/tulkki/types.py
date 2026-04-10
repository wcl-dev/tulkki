"""Core data structures shared across modules.

These dataclasses are the contract between fetchers, extractors, the diff
engine, and the report renderer. Nothing here imports any backend-specific
package, so the layer is safe to depend on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class GapKind(str, Enum):
    """Classification of the visibility gap between AI and human views.

    Derived from the two scores (raw_presence_score, visibility_score):
    - NONE: both scores high — AI crawlers see everything.
    - EXTRACTION: raw bytes contain the content but extractors miss it
      (e.g. Next.js RSC flight data locked inside <script> tags).
    - RENDERING: content only exists after JS execution (true CSR).
    - MIXED: both extraction and rendering gaps are material.
    - BLOCKED: HTTP error on either side; scores are meaningless.
    """

    NONE = "none"
    EXTRACTION = "extraction"
    RENDERING = "rendering"
    MIXED = "mixed"
    BLOCKED = "blocked"


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
class RawPresenceReport:
    """Substring-based presence check of rendered content against raw HTML.

    Measures how much of the human-visible content is physically present
    in the raw HTML bytes (before any extraction or JS rendering).
    """

    sentence_coverage: float  # 0..1, primary signal = raw_presence_score
    sentences_checked: int
    sentences_found_in_raw: int
    heading_coverage: float  # 0..1, secondary signal for interpretation
    headings_checked: int
    headings_found_in_raw: int
    missing_sentences: tuple[str, ...]  # up to 20 samples of rendering-gap content
    missing_headings: tuple[Heading, ...]
    frameworks_detected: tuple[str, ...]  # e.g. ("nextjs-rsc",)


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
    # v0.2: raw bytes presence analysis
    raw_presence: RawPresenceReport
    raw_presence_score: float  # == raw_presence.sentence_coverage
    gap_kind: GapKind
