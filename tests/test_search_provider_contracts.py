from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta

import pytest

from synapse.search import (
    CapabilitySupportStatus,
    CorrelationReference,
    FreshnessConstraint,
    FreshnessFacts,
    FreshnessKind,
    NormalizedSearchResultV1,
    PolicyReference,
    ProviderFactStatus,
    ProviderResultReference,
    ProviderResultRepetition,
    ProviderResultTimeliness,
    ProviderTimeoutContract,
    PublicationDateProvenance,
    RequesterReference,
    SafeSearchMode,
    SearchCapabilityReference,
    SearchDetailReference,
    SearchDiagnostic,
    SearchErrorCode,
    SearchFingerprint,
    SearchInvocationId,
    SearchOccurrence,
    SearchOutcomeCode,
    SearchProviderCapabilitiesV1,
    SearchProviderCapability,
    SearchProviderCapabilityFact,
    SearchProviderHealthStatus,
    SearchProviderHealthV1,
    SearchProviderInvocationV1,
    SearchProviderPort,
    SearchProviderReference,
    SearchProviderResultStatus,
    SearchProviderResultV1,
    SearchPurpose,
    SearchRequestId,
    SearchRequestOccurrence,
    SearchRequestV1,
    SearchResultId,
    SearchResultProvenance,
    SearchResultSetId,
    SearchResultSetProvenance,
    SearchResultSetV1,
    SearchRuntimeProviderHealth,
    SearchSourceReference,
    SearchValidationError,
    classify_provider_result_repetition,
    required_capabilities,
    unsupported_capability_diagnostic,
)

NOW = datetime(2026, 8, 12, 18, 0, tzinfo=UTC)
PROVIDER = SearchProviderReference("provider:neutral-search")


def request(**updates: object) -> SearchRequestV1:
    values: dict[str, object] = {
        "request_id": SearchRequestId("search-request:provider-1"),
        "requester": RequesterReference("principal:owner"),
        "query": "provider neutral query",
        "purpose": SearchPurpose("technical.research"),
        "correlation": CorrelationReference("correlation:provider-1"),
        "occurrence": SearchRequestOccurrence(NOW),
    }
    values.update(updates)
    return SearchRequestV1(**values)  # type: ignore[arg-type]


def invocation(
    search_request: SearchRequestV1 | None = None, **updates: object
) -> SearchProviderInvocationV1:
    value = search_request or request()
    values: dict[str, object] = {
        "invocation_id": SearchInvocationId("search-invocation:attempt-1"),
        "request": value,
        "request_id": value.request_id,
        "request_fingerprint": value.semantic_fingerprint,
        "provider": PROVIDER,
        "required_capabilities": required_capabilities(value),
        "correlation": value.correlation,
        "causation": (),
        "occurrence": SearchOccurrence(NOW),
        "timeout": ProviderTimeoutContract(30),
        "policy_reference": PolicyReference("policy:search-egress-future"),
    }
    values.update(updates)
    return SearchProviderInvocationV1(**values)  # type: ignore[arg-type]


def declaration(
    *facts: SearchProviderCapabilityFact,
    provider: SearchProviderReference = PROVIDER,
) -> SearchProviderCapabilitiesV1:
    supplied = facts or tuple(
        SearchProviderCapabilityFact(item, CapabilitySupportStatus.SUPPORTED)
        for item in SearchProviderCapability
    )
    return SearchProviderCapabilitiesV1(
        provider,
        SearchCapabilityReference("provider-type:web-search"),
        SearchDetailReference("manifest:neutral-v1"),
        tuple(supplied),
    )


def no_results(invocation_value: SearchProviderInvocationV1 | None = None) -> SearchProviderResultV1:
    attempt = invocation_value or invocation()
    result_set = SearchResultSetV1(
        result_set_id=SearchResultSetId("search-result-set:provider-empty"),
        request_id=attempt.request_id,
        request_fingerprint=attempt.request_fingerprint,
        provider=attempt.provider,
        provider_invocation=attempt.invocation_id,
        outcome=SearchOutcomeCode.NO_RESULTS,
        results=(),
        search_occurrence=attempt.occurrence,
        provenance=SearchResultSetProvenance(
            request_id=attempt.request_id,
            request_fingerprint=attempt.request_fingerprint,
            provider=attempt.provider,
            provider_invocation=attempt.invocation_id,
            search_occurrence=attempt.occurrence,
        ),
    )
    return SearchProviderResultV1(
        invocation_id=attempt.invocation_id,
        request_id=attempt.request_id,
        request_fingerprint=attempt.request_fingerprint,
        provider=attempt.provider,
        required_capabilities=attempt.required_capabilities,
        correlation=attempt.correlation,
        status=SearchProviderResultStatus.NO_RESULTS,
        observed_at=NOW + timedelta(seconds=1),
        result_set=result_set,
    )


def successful_results() -> SearchProviderResultV1:
    attempt = invocation()
    result_id = SearchResultId("search-result:provider-1")
    provider_result = ProviderResultReference("provider-result:item-1")
    source_url = "https://example.com/item"
    provenance = SearchResultProvenance(
        request_id=attempt.request_id,
        request_fingerprint=attempt.request_fingerprint,
        provider=attempt.provider,
        provider_invocation=attempt.invocation_id,
        result_id=result_id,
        provider_result_reference=provider_result,
        source_url=source_url,
        search_occurrence=attempt.occurrence,
        provider_position=1,
    )
    freshness = FreshnessFacts.from_observation(
        attempt.request.freshness,
        publication_date=None,
        provider_reported_date=None,
        search_occurrence=attempt.occurrence,
    )
    normalized = NormalizedSearchResultV1(
        result_id=result_id,
        source_url=source_url,
        title="Provider-neutral result",
        provider_snippet="Observed snippet.",
        source=SearchSourceReference("source:example.com"),
        provider=attempt.provider,
        provider_result_reference=provider_result,
        provider_position=1,
        normalized_rank=1,
        search_occurrence=attempt.occurrence,
        freshness=freshness,
        provenance=provenance,
        publication_date_provenance=PublicationDateProvenance.UNKNOWN,
    )
    result_set = SearchResultSetV1(
        result_set_id=SearchResultSetId("search-result-set:provider-results"),
        request_id=attempt.request_id,
        request_fingerprint=attempt.request_fingerprint,
        provider=attempt.provider,
        provider_invocation=attempt.invocation_id,
        outcome=SearchOutcomeCode.RESULTS,
        results=(normalized,),
        search_occurrence=attempt.occurrence,
        provenance=SearchResultSetProvenance(
            request_id=attempt.request_id,
            request_fingerprint=attempt.request_fingerprint,
            provider=attempt.provider,
            provider_invocation=attempt.invocation_id,
            search_occurrence=attempt.occurrence,
        ),
    )
    return SearchProviderResultV1(
        invocation_id=attempt.invocation_id,
        request_id=attempt.request_id,
        request_fingerprint=attempt.request_fingerprint,
        provider=attempt.provider,
        required_capabilities=attempt.required_capabilities,
        correlation=attempt.correlation,
        status=SearchProviderResultStatus.RESULTS,
        observed_at=NOW,
        result_set=result_set,
    )


def failure(
    status: SearchProviderResultStatus, code: SearchErrorCode
) -> SearchProviderResultV1:
    attempt = invocation()
    return SearchProviderResultV1(
        invocation_id=attempt.invocation_id,
        request_id=attempt.request_id,
        request_fingerprint=attempt.request_fingerprint,
        provider=attempt.provider,
        required_capabilities=attempt.required_capabilities,
        correlation=attempt.correlation,
        status=status,
        observed_at=NOW,
        diagnostic=SearchDiagnostic(code, "Safe provider observation.", NOW, request_id=attempt.request_id),
    )


def test_provider_port_is_consumer_owned_typed_and_runtime_checkable() -> None:
    class Stub:
        def invoke(self, invocation: SearchProviderInvocationV1) -> SearchProviderResultV1:
            return no_results(invocation)

    assert isinstance(Stub(), SearchProviderPort)
    assert Stub().invoke(invocation()).status is SearchProviderResultStatus.NO_RESULTS


def test_request_and_invocation_have_distinct_identities_and_are_immutable() -> None:
    value = invocation()
    assert str(value.request_id).startswith("search-request:")
    assert str(value.invocation_id).startswith("search-invocation:")
    assert value.request_id != value.invocation_id
    with pytest.raises(FrozenInstanceError):
        value.provider = SearchProviderReference("provider:other")  # type: ignore[misc]


def test_invocation_preserves_request_fingerprint_and_rejects_wrong_correspondence() -> None:
    value = request()
    assert invocation(value).request_fingerprint == value.semantic_fingerprint
    with pytest.raises(SearchValidationError, match="identity mismatch"):
        invocation(value, request_id=SearchRequestId("search-request:wrong"))
    with pytest.raises(SearchValidationError, match="fingerprint mismatch"):
        invocation(value, request_fingerprint=SearchFingerprint("sha256:" + "3" * 64))


def test_capability_requirements_are_derived_without_ignoring_constraints() -> None:
    value = request(
        language="pt-BR",
        categories=("news",),
        freshness=FreshnessConstraint(FreshnessKind.WINDOW, window_seconds=3600),
        safe_search=SafeSearchMode.STRICT,
    )
    required = set(required_capabilities(value))
    assert {
        SearchProviderCapability.BASIC_WEB_SEARCH,
        SearchProviderCapability.LANGUAGE_FILTERING,
        SearchProviderCapability.CATEGORY_FILTERING,
        SearchProviderCapability.FRESHNESS_CONSTRAINTS,
        SearchProviderCapability.SAFE_SEARCH,
        SearchProviderCapability.RESULT_LIMIT,
    }.issubset(required)


def test_capability_declaration_is_closed_sorted_and_deterministic() -> None:
    value = declaration()
    assert value.support_for(SearchProviderCapability.BASIC_WEB_SEARCH) is CapabilitySupportStatus.SUPPORTED
    assert value.semantic_fingerprint == declaration().semantic_fingerprint
    assert json.loads(value.canonical_serialization())["capabilities"]["format_version"] == "search-provider-capabilities-v1"
    with pytest.raises(SearchValidationError, match="duplicates"):
        declaration(
            SearchProviderCapabilityFact(SearchProviderCapability.BASIC_WEB_SEARCH, CapabilitySupportStatus.SUPPORTED),
            SearchProviderCapabilityFact(SearchProviderCapability.BASIC_WEB_SEARCH, CapabilitySupportStatus.DEGRADED),
        )


def test_unsupported_or_unknown_required_capability_produces_factual_result() -> None:
    attempt = invocation()
    capabilities = declaration(
        SearchProviderCapabilityFact(SearchProviderCapability.BASIC_WEB_SEARCH, CapabilitySupportStatus.SUPPORTED),
        SearchProviderCapabilityFact(SearchProviderCapability.RESULT_LIMIT, CapabilitySupportStatus.UNSUPPORTED),
        SearchProviderCapabilityFact(SearchProviderCapability.SAFE_SEARCH, CapabilitySupportStatus.UNKNOWN),
    )
    result = unsupported_capability_diagnostic(attempt, capabilities, observed_at=NOW)
    assert result is not None
    assert result.status is SearchProviderResultStatus.UNSUPPORTED_CAPABILITY
    assert result.diagnostic is not None
    assert result.diagnostic.code is SearchErrorCode.UNSUPPORTED_CAPABILITY


def test_fully_supported_invocation_needs_no_capability_diagnostic() -> None:
    assert unsupported_capability_diagnostic(invocation(), declaration(), observed_at=NOW) is None


def test_valid_no_results_is_success_and_not_provider_failure() -> None:
    value = no_results()
    value.validate_correspondence(invocation())
    assert value.status is SearchProviderResultStatus.NO_RESULTS
    assert value.result_set is not None and value.result_set.results == ()
    assert value.diagnostic is None


def test_success_with_results_requires_corresponding_normalized_result_set() -> None:
    value = successful_results()
    value.validate_correspondence(invocation())
    assert value.status is SearchProviderResultStatus.RESULTS
    assert value.result_set is not None and len(value.result_set.results) == 1


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (SearchProviderResultStatus.PROVIDER_UNAVAILABLE, SearchErrorCode.PROVIDER_UNAVAILABLE),
        (SearchProviderResultStatus.MALFORMED_RESPONSE, SearchErrorCode.PROVIDER_RESPONSE_MALFORMED),
        (SearchProviderResultStatus.POLICY_BLOCKED, SearchErrorCode.POLICY_BLOCKED),
    ],
)
def test_provider_failures_are_factual_envelopes_with_safe_diagnostics(status, code) -> None:
    value = failure(status, code)
    assert value.result_set is None
    assert value.diagnostic is not None and value.diagnostic.code is code


def test_timeout_preserves_unknown_completion_and_is_not_termination_proof() -> None:
    value = failure(SearchProviderResultStatus.TIMEOUT, SearchErrorCode.PROVIDER_TIMEOUT)
    assert value.completion_after_timeout is None
    with pytest.raises(SearchValidationError, match="cannot claim"):
        replace(value, completion_after_timeout=False)


def test_wrong_request_provider_fingerprint_correlation_and_capabilities_are_rejected() -> None:
    attempt = invocation()
    base = no_results(attempt)
    mutations = (
        replace(base, request_id=SearchRequestId("search-request:wrong"), result_set=None, status=SearchProviderResultStatus.PROVIDER_UNAVAILABLE, diagnostic=SearchDiagnostic(SearchErrorCode.PROVIDER_UNAVAILABLE, "Safe.", NOW)),
        replace(base, provider=SearchProviderReference("provider:wrong"), result_set=None, status=SearchProviderResultStatus.PROVIDER_UNAVAILABLE, diagnostic=SearchDiagnostic(SearchErrorCode.PROVIDER_UNAVAILABLE, "Safe.", NOW)),
        replace(base, request_fingerprint=SearchFingerprint("sha256:" + "4" * 64), result_set=None, status=SearchProviderResultStatus.PROVIDER_UNAVAILABLE, diagnostic=SearchDiagnostic(SearchErrorCode.PROVIDER_UNAVAILABLE, "Safe.", NOW)),
        replace(base, correlation=CorrelationReference("correlation:wrong")),
        replace(base, required_capabilities=(SearchProviderCapability.BASIC_WEB_SEARCH,)),
    )
    for value in mutations:
        with pytest.raises(SearchValidationError, match="correspond"):
            value.validate_correspondence(attempt)


def test_stale_and_late_provider_results_are_detected_without_discarding_facts() -> None:
    attempt = invocation()
    stale = replace(no_results(attempt), observed_at=NOW - timedelta(seconds=1))
    with pytest.raises(SearchValidationError, match="stale"):
        stale.validate_correspondence(attempt)
    late = replace(no_results(attempt), observed_at=NOW + timedelta(seconds=31))
    assert late.timeliness_for(attempt) is ProviderResultTimeliness.LATE
    assert no_results(attempt).timeliness_for(attempt) is ProviderResultTimeliness.ON_TIME


def test_duplicate_identical_result_is_idempotent_but_contradiction_is_explicit() -> None:
    first = no_results()
    assert classify_provider_result_repetition(None, first) is ProviderResultRepetition.FIRST_OBSERVATION
    assert classify_provider_result_repetition(first, first) is ProviderResultRepetition.IDENTICAL_REPEAT
    repeated_later = replace(first, observed_at=first.observed_at + timedelta(seconds=1))
    assert classify_provider_result_repetition(first, repeated_later) is ProviderResultRepetition.IDENTICAL_REPEAT
    contradictory = failure(
        SearchProviderResultStatus.PROVIDER_UNAVAILABLE,
        SearchErrorCode.PROVIDER_UNAVAILABLE,
    )
    assert classify_provider_result_repetition(first, contradictory) is ProviderResultRepetition.CONTRADICTORY_REPEAT


def test_retry_requires_new_invocation_but_keeps_request_semantics() -> None:
    first = invocation()
    retry = invocation(
        first.request,
        invocation_id=SearchInvocationId("search-invocation:attempt-2"),
        retry_of=first.invocation_id,
    )
    assert retry.invocation_id != first.invocation_id
    assert retry.request_fingerprint == first.request_fingerprint
    assert retry.semantic_fingerprint == first.semantic_fingerprint
    with pytest.raises(SearchValidationError, match="new provider invocation"):
        replace(first, retry_of=first.invocation_id)


def test_provider_health_unconfigured_configured_degraded_and_available_are_factual() -> None:
    unconfigured = SearchProviderHealthV1(
        PROVIDER,
        SearchProviderHealthStatus.UNCONFIGURED,
        NOW,
        ProviderFactStatus.NO,
        ProviderFactStatus.NO,
    )
    configured = SearchProviderHealthV1(
        PROVIDER,
        SearchProviderHealthStatus.CONFIGURED,
        NOW,
        ProviderFactStatus.YES,
        ProviderFactStatus.YES,
    )
    degraded = replace(configured, status=SearchProviderHealthStatus.DEGRADED, reachable=ProviderFactStatus.NO)
    available = replace(
        configured,
        status=SearchProviderHealthStatus.AVAILABLE,
        reachable=ProviderFactStatus.YES,
        response_format_supported=ProviderFactStatus.YES,
        authorization_available=ProviderFactStatus.YES,
        network_egress_available=ProviderFactStatus.YES,
    )
    assert {unconfigured.status, configured.status, degraded.status, available.status} == {
        SearchProviderHealthStatus.UNCONFIGURED,
        SearchProviderHealthStatus.CONFIGURED,
        SearchProviderHealthStatus.DEGRADED,
        SearchProviderHealthStatus.AVAILABLE,
    }


def test_adapter_existence_does_not_imply_provider_available() -> None:
    health = SearchProviderHealthV1(
        PROVIDER,
        SearchProviderHealthStatus.CONFIGURED,
        NOW,
        ProviderFactStatus.YES,
        ProviderFactStatus.YES,
        adapter_reference=SearchDetailReference("adapter:exists"),
    )
    assert health.status is not SearchProviderHealthStatus.AVAILABLE
    with pytest.raises(SearchValidationError, match="explicit positive"):
        replace(health, status=SearchProviderHealthStatus.AVAILABLE)


def test_runtime_health_can_represent_zero_composed_providers() -> None:
    health = SearchRuntimeProviderHealth(True, 0, ())
    assert health.provider_contracts_available
    assert health.composed_provider_count == 0


def test_occurrence_does_not_change_semantic_fingerprints() -> None:
    first = invocation()
    second = replace(first, occurrence=SearchOccurrence(NOW + timedelta(minutes=1)))
    assert first.semantic_fingerprint == second.semantic_fingerprint
    first_result = no_results(first)
    second_result = replace(first_result, observed_at=NOW + timedelta(minutes=2))
    assert first_result.semantic_fingerprint == second_result.semantic_fingerprint


def test_no_provider_transport_network_authorization_or_searxng_fields_exist() -> None:
    names = {item.name for item in fields(SearchProviderInvocationV1)}
    assert {
        "endpoint",
        "base_url",
        "api_key",
        "headers",
        "http_client",
        "searxng_engines",
        "network_authorization",
        "retry_executor",
        "raw_transport_settings",
    }.isdisjoint(names)
