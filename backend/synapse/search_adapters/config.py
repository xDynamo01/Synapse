"""Typed, non-secret SearXNG adapter configuration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from synapse.search import SearchProviderReference, SearchValidationError

_CATEGORY = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
_SEARXNG_CATEGORY = re.compile(r"^[a-z][a-z0-9 _-]{0,63}$")
_PATH = re.compile(r"^/[A-Za-z0-9/_-]*$")


@dataclass(frozen=True, slots=True, order=True)
class SearXNGCategoryMapping:
    search_category: str
    searxng_category: str

    def __post_init__(self) -> None:
        if _CATEGORY.fullmatch(self.search_category) is None:
            raise SearchValidationError("Search category mapping key is invalid")
        if _SEARXNG_CATEGORY.fullmatch(self.searxng_category) is None:
            raise SearchValidationError("SearXNG category mapping value is invalid")


@dataclass(frozen=True, slots=True)
class SearXNGAdapterConfig:
    provider: SearchProviderReference
    base_url: str
    endpoint_path: str = "/search"
    expected_format: str = "json"
    category_mappings: tuple[SearXNGCategoryMapping, ...] = ()

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise SearchValidationError("SearXNG base URL must be an origin-only HTTP(S) URL")
        try:
            port = parsed.port
        except ValueError as error:
            raise SearchValidationError("SearXNG base URL port is invalid") from error
        if port is not None and not 1 <= port <= 65535:
            raise SearchValidationError("SearXNG base URL port is invalid")
        if _PATH.fullmatch(self.endpoint_path) is None or "//" in self.endpoint_path:
            raise SearchValidationError("SearXNG endpoint path must be a safe relative path")
        if self.expected_format != "json":
            raise SearchValidationError("SearXNG adapter supports only JSON responses")
        mappings = tuple(sorted(self.category_mappings))
        if len({item.search_category for item in mappings}) != len(mappings):
            raise SearchValidationError("SearXNG Search category mappings must be unique")
        if len({item.searxng_category for item in mappings}) != len(mappings):
            raise SearchValidationError("SearXNG category targets must be unique")
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
        object.__setattr__(self, "category_mappings", mappings)

    def category_for(self, search_category: str) -> str | None:
        return next(
            (
                item.searxng_category
                for item in self.category_mappings
                if item.search_category == search_category
            ),
            None,
        )
