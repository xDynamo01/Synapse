"""Provider-neutral immutable SearchRequestV1 domain contract."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from .canonical import SEARCH_CANONICAL_FORMAT_V1, canonical_json, semantic_fingerprint
from .errors import SearchValidationError
from .identities import (
    CausationReference,
    CorrelationReference,
    PolicyReference,
    RequesterReference,
    SearchFingerprint,
    SearchRequestId,
)

SEARCH_REQUEST_FORMAT_V1 = "search-request-v1"
DEFAULT_RESULT_LIMIT = 10
MIN_RESULT_LIMIT = 1
MAX_RESULT_LIMIT = 50

_LANGUAGE_TAG = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")
_CATEGORY = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
_PURPOSE = re.compile(r"^[a-z][a-z0-9._:-]{0,95}$")
_DOMAIN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class FreshnessKind(StrEnum):
    NONE = "none"
    WINDOW = "window"
    AFTER = "after"
    BEFORE = "before"
    RANGE = "range"


class SafeSearchMode(StrEnum):
    OFF = "off"
    MODERATE = "moderate"
    STRICT = "strict"


def _aware_utc(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise SearchValidationError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class FreshnessConstraint:
    kind: FreshnessKind = FreshnessKind.NONE
    window_seconds: int | None = None
    after: datetime | None = None
    before: datetime | None = None

    def __post_init__(self) -> None:
        after = _aware_utc(self.after, "freshness after")
        before = _aware_utc(self.before, "freshness before")
        object.__setattr__(self, "after", after)
        object.__setattr__(self, "before", before)
        if isinstance(self.window_seconds, bool):
            raise SearchValidationError("freshness window must be a positive integer")
        valid = {
            FreshnessKind.NONE: self.window_seconds is None and after is None and before is None,
            FreshnessKind.WINDOW: (
                isinstance(self.window_seconds, int)
                and self.window_seconds > 0
                and after is None
                and before is None
            ),
            FreshnessKind.AFTER: self.window_seconds is None and after is not None and before is None,
            FreshnessKind.BEFORE: self.window_seconds is None and after is None and before is not None,
            FreshnessKind.RANGE: (
                self.window_seconds is None
                and after is not None
                and before is not None
                and after < before
            ),
        }
        if not valid[self.kind]:
            raise SearchValidationError("freshness fields do not match freshness kind")


def _canonical_domain(value: str) -> str:
    if not isinstance(value, str):
        raise SearchValidationError("domain constraint must be a string")
    domain = value.strip().lower().removesuffix(".")
    labels = domain.split(".")
    if (
        not domain
        or len(domain) > 253
        or len(labels) < 2
        or any(not _DOMAIN_LABEL.fullmatch(label) for label in labels)
    ):
        raise SearchValidationError("domain constraint must be a canonical host name")
    return domain


@dataclass(frozen=True, slots=True)
class DomainConstraints:
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        included = tuple(sorted({_canonical_domain(item) for item in self.include}))
        excluded = tuple(sorted({_canonical_domain(item) for item in self.exclude}))
        if set(included).intersection(excluded):
            raise SearchValidationError("a domain cannot be both included and excluded")
        object.__setattr__(self, "include", included)
        object.__setattr__(self, "exclude", excluded)


@dataclass(frozen=True, slots=True, order=True)
class SearchPurpose:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _PURPOSE.fullmatch(self.value):
            raise SearchValidationError("purpose must be an explicit provider-neutral reference")

    def canonical_value(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SearchRequestOccurrence:
    occurred_at: datetime

    def __post_init__(self) -> None:
        normalized = _aware_utc(self.occurred_at, "request occurrence")
        assert normalized is not None
        object.__setattr__(self, "occurred_at", normalized)


@dataclass(frozen=True, slots=True)
class SearchRequestV1:
    request_id: SearchRequestId
    requester: RequesterReference
    query: str
    purpose: SearchPurpose
    correlation: CorrelationReference
    occurrence: SearchRequestOccurrence
    language: str | None = None
    locale: str | None = None
    result_limit: int = DEFAULT_RESULT_LIMIT
    freshness: FreshnessConstraint = field(default_factory=FreshnessConstraint)
    categories: tuple[str, ...] = ()
    domains: DomainConstraints = field(default_factory=DomainConstraints)
    safe_search: SafeSearchMode = SafeSearchMode.MODERATE
    policy_reference: PolicyReference | None = None
    causation: tuple[CausationReference, ...] = ()
    format_version: str = SEARCH_REQUEST_FORMAT_V1

    def __post_init__(self) -> None:
        required_identities = (
            (self.request_id, SearchRequestId, "request identity"),
            (self.requester, RequesterReference, "requester reference"),
            (self.correlation, CorrelationReference, "correlation reference"),
        )
        for value, expected_type, label in required_identities:
            if not isinstance(value, expected_type):
                raise SearchValidationError(f"{label} is required")
        if not isinstance(self.purpose, SearchPurpose):
            raise SearchValidationError("purpose is required")
        if not isinstance(self.occurrence, SearchRequestOccurrence):
            raise SearchValidationError("request occurrence is required")
        if not isinstance(self.freshness, FreshnessConstraint):
            raise SearchValidationError("freshness constraint is invalid")
        if not isinstance(self.domains, DomainConstraints):
            raise SearchValidationError("domain constraints are invalid")
        if not isinstance(self.safe_search, SafeSearchMode):
            raise SearchValidationError("safe-search mode is invalid")
        if self.policy_reference is not None and not isinstance(
            self.policy_reference, PolicyReference
        ):
            raise SearchValidationError("policy reference is invalid")
        query = self.query.strip() if isinstance(self.query, str) else ""
        if not query:
            raise SearchValidationError("query must contain explicit non-whitespace content")
        object.__setattr__(self, "query", query)
        object.__setattr__(self, "language", self._tag(self.language, "language"))
        object.__setattr__(self, "locale", self._tag(self.locale, "locale"))
        if (
            isinstance(self.result_limit, bool)
            or not isinstance(self.result_limit, int)
            or not MIN_RESULT_LIMIT <= self.result_limit <= MAX_RESULT_LIMIT
        ):
            raise SearchValidationError(
                f"result limit must be between {MIN_RESULT_LIMIT} and {MAX_RESULT_LIMIT}"
            )
        categories = tuple(sorted(set(self.categories)))
        if any(not isinstance(item, str) or not _CATEGORY.fullmatch(item) for item in categories):
            raise SearchValidationError("category must be a provider-neutral canonical reference")
        object.__setattr__(self, "categories", categories)
        if not isinstance(self.causation, tuple) or any(
            not isinstance(item, CausationReference) for item in self.causation
        ):
            raise SearchValidationError("causation references are invalid")
        if len(set(self.causation)) != len(self.causation):
            raise SearchValidationError("causation references must be unique")
        if self.format_version != SEARCH_REQUEST_FORMAT_V1:
            raise SearchValidationError("unsupported Search request format")

    @staticmethod
    def _tag(value: str | None, field_name: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not _LANGUAGE_TAG.fullmatch(value):
            raise SearchValidationError(f"{field_name} must be a valid language tag")
        return value.lower()

    def semantic_content(self) -> dict[str, object]:
        """Exclude request/coordination/occurrence identity from semantic equivalence."""

        return {
            "canonical_format": SEARCH_CANONICAL_FORMAT_V1,
            "request_format": self.format_version,
            "requester": self.requester,
            "query": self.query,
            "language": self.language,
            "locale": self.locale,
            "result_limit": self.result_limit,
            "freshness": self.freshness,
            "categories": self.categories,
            "domains": self.domains,
            "safe_search": self.safe_search,
            "policy_reference": self.policy_reference,
            "purpose": self.purpose,
        }

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())

    def canonical_serialization(self) -> str:
        return canonical_json(
            {
                "canonical_format": SEARCH_CANONICAL_FORMAT_V1,
                "request": self,
                "semantic_fingerprint": self.semantic_fingerprint,
            }
        )
