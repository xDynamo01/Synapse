from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta

import pytest

from synapse.search import (
    DEFAULT_RESULT_LIMIT,
    MAX_RESULT_LIMIT,
    MIN_RESULT_LIMIT,
    SEARCH_CANONICAL_FORMAT_V1,
    SEARCH_REQUEST_FORMAT_V1,
    CausationReference,
    CorrelationReference,
    DomainConstraints,
    FreshnessConstraint,
    FreshnessKind,
    InvalidSearchIdentity,
    PolicyReference,
    RequesterReference,
    SafeSearchMode,
    SearchCapabilityReference,
    SearchDetailReference,
    SearchDiagnostic,
    SearchErrorCode,
    SearchFingerprint,
    SearchInvocationId,
    SearchOutcomeCode,
    SearchPurpose,
    SearchRequestId,
    SearchRequestOccurrence,
    SearchRequestV1,
    SearchValidationError,
    canonical_json,
)

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def request(**updates: object) -> SearchRequestV1:
    values: dict[str, object] = {
        "request_id": SearchRequestId("search-request:req-001"),
        "requester": RequesterReference("principal:local-owner"),
        "query": "distributed systems",
        "purpose": SearchPurpose("technical.research"),
        "correlation": CorrelationReference("correlation:conversation-1"),
        "occurrence": SearchRequestOccurrence(NOW),
    }
    values.update(updates)
    return SearchRequestV1(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("identity_type", "valid"),
    [
        (SearchRequestId, "search-request:opaque-1"),
        (SearchInvocationId, "search-invocation:opaque-1"),
        (RequesterReference, "principal:local-owner"),
        (PolicyReference, "policy:search-v1"),
        (CorrelationReference, "correlation:turn-1"),
        (CausationReference, "cause:message-1"),
        (SearchCapabilityReference, "capability:web-search"),
        (SearchDetailReference, "detail:provider-observation-1"),
    ],
)
def test_identities_are_canonical_hashable_and_deterministic(identity_type, valid) -> None:
    first = identity_type(valid)
    second = identity_type(valid)
    assert first == second
    assert hash(first) == hash(second)
    assert str(first) == first.canonical_value() == valid


@pytest.mark.parametrize(
    ("identity_type", "invalid"),
    [
        (SearchRequestId, ""),
        (SearchRequestId, "search-invocation:wrong-kind"),
        (SearchInvocationId, "search-invocation:"),
        (RequesterReference, "../principal"),
        (PolicyReference, "C:\\private\\policy"),
        (CorrelationReference, "contains whitespace"),
    ],
)
def test_identities_reject_empty_malformed_or_path_like_values(identity_type, invalid) -> None:
    with pytest.raises(InvalidSearchIdentity):
        identity_type(invalid)


def test_request_is_frozen_and_uses_canonical_defaults() -> None:
    value = request(query="  explicit query  ")
    assert value.query == "explicit query"
    assert value.result_limit == DEFAULT_RESULT_LIMIT == 10
    assert MIN_RESULT_LIMIT == 1 and MAX_RESULT_LIMIT == 50
    assert value.safe_search is SafeSearchMode.MODERATE
    assert value.categories == ()
    assert value.domains == DomainConstraints()
    assert value.format_version == SEARCH_REQUEST_FORMAT_V1
    with pytest.raises(FrozenInstanceError):
        value.query = "changed"  # type: ignore[misc]


def test_canonical_serialization_is_stable_ordered_and_versioned() -> None:
    value = request(
        categories=("technical", "news", "technical"),
        domains=DomainConstraints(
            include=("Example.COM.", "docs.example.com"), exclude=("ads.example.com",)
        ),
        causation=(CausationReference("cause:turn-1"),),
    )
    payload = json.loads(value.canonical_serialization())
    assert payload["canonical_format"] == SEARCH_CANONICAL_FORMAT_V1
    assert payload["request"]["categories"] == ["news", "technical"]
    assert payload["request"]["domains"]["include"] == ["docs.example.com", "example.com"]
    assert payload["semantic_fingerprint"].startswith("sha256:")
    assert value.canonical_serialization() == value.canonical_serialization()
    assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'


def test_occurrence_and_coordination_metadata_do_not_change_semantic_fingerprint() -> None:
    first = request(
        causation=(CausationReference("cause:first"),),
        occurrence=SearchRequestOccurrence(NOW),
    )
    second = replace(
        first,
        request_id=SearchRequestId("search-request:req-002"),
        correlation=CorrelationReference("correlation:conversation-2"),
        causation=(CausationReference("cause:second"),),
        occurrence=SearchRequestOccurrence(NOW + timedelta(hours=1)),
    )
    assert first.semantic_fingerprint == second.semantic_fingerprint
    assert first.canonical_serialization() != second.canonical_serialization()


@pytest.mark.parametrize(
    "change",
    [
        lambda value: replace(value, query="different query"),
        lambda value: replace(value, language="pt-BR"),
        lambda value: replace(value, locale="pt-BR"),
        lambda value: replace(value, result_limit=20),
        lambda value: replace(
            value,
            freshness=FreshnessConstraint(FreshnessKind.WINDOW, window_seconds=3600),
        ),
        lambda value: replace(value, categories=("news",)),
        lambda value: replace(value, domains=DomainConstraints(include=("example.com",))),
        lambda value: replace(value, safe_search=SafeSearchMode.STRICT),
        lambda value: replace(value, purpose=SearchPurpose("fact.check")),
        lambda value: replace(value, policy_reference=PolicyReference("policy:strict")),
        lambda value: replace(value, requester=RequesterReference("principal:another")),
    ],
)
def test_semantic_fields_change_fingerprint(
    change: Callable[[SearchRequestV1], SearchRequestV1],
) -> None:
    baseline = request()
    assert change(baseline).semantic_fingerprint != baseline.semantic_fingerprint


@pytest.mark.parametrize("query", ["", " ", "\t\r\n", None])
def test_query_must_be_explicit_and_is_not_semantically_rewritten(query) -> None:
    with pytest.raises(SearchValidationError, match="query"):
        request(query=query)
    assert request(query="exact   phrase").query == "exact   phrase"


@pytest.mark.parametrize("field_name", ["language", "locale"])
def test_language_and_locale_are_distinct_optional_normalized_tags(field_name: str) -> None:
    value = request(**{field_name: "PT-br"})
    assert getattr(value, field_name) == "pt-br"
    assert getattr(value, "locale" if field_name == "language" else "language") is None
    with pytest.raises(SearchValidationError, match=field_name):
        request(**{field_name: "pt_BR"})


@pytest.mark.parametrize("limit", [0, -1, 51, True, None])
def test_result_limit_is_bounded_and_never_unlimited(limit) -> None:
    with pytest.raises(SearchValidationError, match="result limit"):
        request(result_limit=limit)


def test_freshness_models_none_window_absolute_and_range_without_publication_date() -> None:
    assert FreshnessConstraint().kind is FreshnessKind.NONE
    assert FreshnessConstraint(FreshnessKind.WINDOW, window_seconds=3600).window_seconds == 3600
    assert FreshnessConstraint(FreshnessKind.AFTER, after=NOW).after == NOW
    assert FreshnessConstraint(FreshnessKind.BEFORE, before=NOW).before == NOW
    interval = FreshnessConstraint(
        FreshnessKind.RANGE, after=NOW, before=NOW + timedelta(days=1)
    )
    assert interval.after < interval.before  # type: ignore[operator]
    assert "publication" not in {item.name for item in fields(FreshnessConstraint)}


@pytest.mark.parametrize(
    "constraint",
    [
        lambda: FreshnessConstraint(FreshnessKind.WINDOW, window_seconds=0),
        lambda: FreshnessConstraint(FreshnessKind.NONE, after=NOW),
        lambda: FreshnessConstraint(FreshnessKind.AFTER),
        lambda: FreshnessConstraint(FreshnessKind.RANGE, after=NOW, before=NOW),
        lambda: FreshnessConstraint(FreshnessKind.AFTER, after=datetime(2026, 1, 1)),
    ],
)
def test_invalid_freshness_fails_closed(constraint) -> None:
    with pytest.raises(SearchValidationError, match="freshness"):
        constraint()


def test_categories_are_extensible_provider_neutral_and_empty_means_no_constraint() -> None:
    assert request().categories == ()
    assert request(categories=("technical", "academic.papers", "technical")).categories == (
        "academic.papers",
        "technical",
    )
    for invalid in ("", "SearXNG:news", "contains space", "-leading"):
        with pytest.raises(SearchValidationError, match="category"):
            request(categories=(invalid,))


def test_domain_constraints_canonicalize_include_exclude_and_reject_conflicts() -> None:
    constraints = DomainConstraints(
        include=("Example.COM.", "docs.example.com", "example.com"),
        exclude=("ads.example.com",),
    )
    assert constraints.include == ("docs.example.com", "example.com")
    assert constraints.exclude == ("ads.example.com",)
    with pytest.raises(SearchValidationError, match="both included and excluded"):
        DomainConstraints(include=("example.com",), exclude=("EXAMPLE.COM.",))
    for invalid in ("", "localhost", "https://example.com", "bad_domain.example"):
        with pytest.raises(SearchValidationError, match="domain"):
            DomainConstraints(include=(invalid,))


def test_safe_search_and_purpose_are_provider_neutral_and_explicit() -> None:
    assert {item.value for item in SafeSearchMode} == {"off", "moderate", "strict"}
    assert request(safe_search=SafeSearchMode.STRICT).safe_search is SafeSearchMode.STRICT
    with pytest.raises(SearchValidationError, match="safe-search"):
        request(safe_search=2)
    with pytest.raises(SearchValidationError, match="purpose"):
        SearchPurpose("SearXNG engine")


@pytest.mark.parametrize(
    "updates",
    [
        {"request_id": None},
        {"requester": None},
        {"correlation": None},
        {"purpose": None},
        {"occurrence": None},
        {"policy_reference": "policy:not-typed"},
        {"causation": ("cause:not-typed",)},
    ],
)
def test_missing_or_malformed_required_references_fail_before_operations(updates) -> None:
    with pytest.raises(SearchValidationError):
        request(**updates)


def test_error_taxonomy_is_closed_and_no_results_is_a_valid_outcome() -> None:
    assert {item.value for item in SearchErrorCode} == {
        "query_invalid",
        "unsupported_capability",
        "policy_blocked",
        "provider_unconfigured",
        "provider_unavailable",
        "provider_timeout",
        "provider_response_malformed",
        "retrieval_unavailable",
        "retrieval_failed",
        "unsupported_content",
        "extraction_failed",
        "cache_stale",
        "cache_invalid",
        "cache_incompatible",
        "cache_entry_unavailable",
        "cache_version_mismatch",
        "persistence_unavailable",
        "persistence_conflict",
        "persistence_corrupt",
        "persistence_version_mismatch",
        "persistence_record_not_found",
        "provenance_incomplete",
        "url_malformed",
        "url_scheme_unsupported",
        "url_normalization_unsafe",
        "duplicate_grouping_inconsistent",
        "ranking_inconsistent",
        "invocation_invalid",
        "capability_declaration_invalid",
        "correspondence_mismatch",
        "provider_result_contradictory",
        "payload_too_large",
        "artifact_malformed",
        "extraction_request_invalid",
        "lineage_incomplete",
    }
    assert {item.value for item in SearchOutcomeCode} == {"results", "no_results"}
    assert "no_results" not in {item.value for item in SearchErrorCode}


def test_diagnostic_is_factual_safe_and_contains_no_raw_payload() -> None:
    diagnostic = SearchDiagnostic(
        SearchErrorCode.PROVIDER_TIMEOUT,
        "Provider did not respond within the admitted boundary.",
        NOW,
        request_id=SearchRequestId("search-request:req-001"),
        capability_reference=SearchCapabilityReference("capability:web-search"),
        detail_reference=SearchDetailReference("detail:attempt-1"),
    )
    assert diagnostic.occurred_at == NOW
    assert not hasattr(diagnostic, "raw_provider_payload")
    with pytest.raises(SearchValidationError, match="single line"):
        replace(diagnostic, safe_message="unsafe\npayload")


def test_fingerprint_validation_is_strict() -> None:
    with pytest.raises(InvalidSearchIdentity):
        SearchFingerprint("sha256:ABC")


def test_request_has_no_provider_transport_or_agent_fields() -> None:
    names = {item.name for item in fields(SearchRequestV1)}
    forbidden = {
        "prompt",
        "chain_of_thought",
        "reasoning_instructions",
        "research_plan",
        "agent_id",
        "provider",
        "searxng_endpoint",
        "engines",
        "http_headers",
        "credentials",
        "timeout",
        "retry_count",
        "browser_instructions",
    }
    assert forbidden.isdisjoint(names)
