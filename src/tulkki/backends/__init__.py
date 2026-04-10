"""Backend factory.

Holds two registries (raw and rendering) and a single entry point per
side. Optional backends are imported lazily so that a default install
without `crawl4ai` / `firecrawl` / `hrequests` / `patchright` still works
end-to-end.
"""

from __future__ import annotations

from typing import Callable

from ..protocols import Fetcher
from .httpx_raw import HttpxRawFetcher
from .playwright_render import PlaywrightRenderer


def _make_httpx_raw() -> Fetcher:
    return HttpxRawFetcher()


def _make_playwright_render() -> Fetcher:
    return PlaywrightRenderer()


def _make_hrequests_raw() -> Fetcher:
    from .hrequests_raw import HrequestsRawFetcher

    return HrequestsRawFetcher()


def _make_patchright_render() -> Fetcher:
    from .patchright_render import PatchrightRenderer

    return PatchrightRenderer()


_RAW_REGISTRY: dict[str, Callable[[], Fetcher]] = {
    "httpx": _make_httpx_raw,
    "hrequests": _make_hrequests_raw,
}

_RENDER_REGISTRY: dict[str, Callable[[], Fetcher]] = {
    "playwright": _make_playwright_render,
    "patchright": _make_patchright_render,
}


def get_raw_fetcher(name: str = "httpx") -> Fetcher:
    try:
        factory = _RAW_REGISTRY[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown raw fetcher: {name!r}. "
            f"Available: {', '.join(sorted(_RAW_REGISTRY))}"
        ) from exc
    return factory()


def get_rendering_fetcher(name: str = "playwright") -> Fetcher:
    try:
        factory = _RENDER_REGISTRY[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown renderer: {name!r}. "
            f"Available: {', '.join(sorted(_RENDER_REGISTRY))}"
        ) from exc
    return factory()


__all__ = ["get_raw_fetcher", "get_rendering_fetcher"]
