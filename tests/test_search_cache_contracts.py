from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from tests.test_search_contracts import request
from tests.test_search_results import PROVIDER, result_set
from tests.test_search_retrieval_contracts import (
    artifact,
    extracted,
    extraction_request,
    retrieval_request,
)

from synapse.search import (
    CACHE_ENTRY_FORMAT_V1,
    CachedObservationVersion,
    CacheEntryId,
    CacheNamespace,
    CachePolicyReference,
    CacheReadStatus,
    CacheRecordRepetition,
    CacheTTLPolicy,
    CacheValidatorReference,
    DomainConstraints,
    ExtractionCacheEntryV1,
    ExtractorReference,
    FreshnessConstraint,
    FreshnessKind,
    PayloadCustody,
    RetrievalCacheEntryV1,
    SafeSearchMode,
    SearchCacheEntryV1,
    SearchCachePolicyV1,
    SearchFingerprint,
    SearchOutcomeCode,
    SearchProviderReference,
    SearchRequestOccurrence,
    SearchResultSetV1,
    StaleUsagePolicy,
    assess_extraction_cache,
    assess_retrieval_cache,
    assess_search_cache,
    classify_cache_record_repetition,
    extraction_cache_key,
    retrieval_cache_key,
    search_cache_key,
)

NOW = datetime(2026, 8, 12, 23, 0, tzinfo=UTC)
POLICY_REFERENCE = CachePolicyReference("cache-policy:search-runtime-v1")


def policy(**updates: object) -> SearchCachePolicyV1:
    values: dict[str, object] = {
        "policy_reference": POLICY_REFERENCE,
        "search_ttl": CacheTTLPolicy(60),
        "retrieval_ttl": CacheTTLPolicy(120),
        "extraction_ttl": CacheTTLPolicy(300),
    }
    values.update(updates)
    return SearchCachePolicyV1(**values)  # type: ignore[arg-type]


def search_entry(**updates: object) -> SearchCacheEntryV1:
    current_policy = policy()
    values: dict[str, object] = {
        "entry_id": CacheEntryId("cache-entry:search-1"),
        "key": search_cache_key(request(), PROVIDER),
        "result_set": result_set(),
        "policy_reference": current_policy.policy_reference,
        "policy_fingerprint": current_policy.semantic_fingerprint,
        "cached_observation_version": CachedObservationVersion(
            "observation-version:sha256-"
            + result_set().semantic_fingerprint.value.removeprefix("sha256:")
        ),
        "written_at": NOW,
        "expires_at": NOW + timedelta(seconds=60),
    }
    values.update(updates)
    if "result_set" in updates and "cached_observation_version" not in updates:
        updated_result_set = cast(SearchResultSetV1, values["result_set"])
        values["cached_observation_version"] = CachedObservationVersion(
            "observation-version:sha256-"
            + updated_result_set.semantic_fingerprint.value.removeprefix("sha256:")
        )
    return SearchCacheEntryV1(**values)  # type: ignore[arg-type]


def retrieval_entry(**updates: object) -> RetrievalCacheEntryV1:
    current_policy = policy()
    values: dict[str, object] = {
        "entry_id": CacheEntryId("cache-entry:retrieval-1"),
        "key": retrieval_cache_key(retrieval_request()),
        "artifact": artifact(),
        "policy_reference": current_policy.policy_reference,
        "policy_fingerprint": current_policy.semantic_fingerprint,
        "cached_observation_version": CachedObservationVersion(
            "observation-version:sha256-"
            + artifact().semantic_fingerprint.value.removeprefix("sha256:")
        ),
        "written_at": NOW,
        "expires_at": NOW + timedelta(seconds=120),
        "payload_custody": PayloadCustody.TRANSIENT_REFERENCE,
    }
    values.update(updates)
    return RetrievalCacheEntryV1(**values)  # type: ignore[arg-type]


def extraction_key(*, checksum=None, extractor_version: str = "text-extraction-adapter-v1"):
    source = artifact(checksum=checksum) if checksum is not None else artifact()
    return extraction_cache_key(
        source,
        extraction_request(),
        ExtractorReference("extractor:text-extraction-v1"),
        extractor_version,
        SearchFingerprint("sha256:" + "e" * 64),
    )


def extraction_entry(**updates: object) -> ExtractionCacheEntryV1:
    current_policy = policy()
    source = artifact()
    assert source.checksum is not None
    values: dict[str, object] = {
        "entry_id": CacheEntryId("cache-entry:extraction-1"),
        "key": extraction_key(),
        "extracted_content": extracted(),
        "artifact_checksum": source.checksum,
        "policy_reference": current_policy.policy_reference,
        "policy_fingerprint": current_policy.semantic_fingerprint,
        "cached_observation_version": CachedObservationVersion(
            "observation-version:sha256-"
            + extracted().semantic_fingerprint.value.removeprefix("sha256:")
        ),
        "written_at": NOW,
        "expires_at": NOW + timedelta(seconds=300),
        "payload_custody": PayloadCustody.TRANSIENT_REFERENCE,
    }
    values.update(updates)
    return ExtractionCacheEntryV1(**values)  # type: ignore[arg-type]


def test_three_namespaces_and_entry_types_are_never_interchangeable() -> None:
    assert search_entry().key.namespace is CacheNamespace.SEARCH
    assert retrieval_entry().key.namespace is CacheNamespace.RETRIEVAL
    assert extraction_entry().key.namespace is CacheNamespace.EXTRACTION
    with pytest.raises(Exception, match="namespace|correspondence"):
        search_entry(key=retrieval_entry().key)


def test_search_key_excludes_occurrence_and_identity_but_separates_semantics() -> None:
    original = request()
    later = replace(
        original,
        request_id=replace(original.request_id, value="search-request:cache-later"),
        occurrence=SearchRequestOccurrence(NOW + timedelta(days=1)),
    )
    assert search_cache_key(original, PROVIDER) == search_cache_key(later, PROVIDER)
    variants = (
        replace(original, language="pt-br"),
        replace(original, locale="pt-br"),
        replace(original, categories=("news",)),
        replace(original, domains=DomainConstraints(include=("example.com",))),
        replace(original, safe_search=SafeSearchMode.STRICT),
        replace(original, result_limit=original.result_limit + 1),
        replace(original, freshness=FreshnessConstraint(FreshnessKind.WINDOW, 60)),
    )
    assert all(search_cache_key(item, PROVIDER) != search_cache_key(original, PROVIDER) for item in variants)


def test_provider_scope_prevents_cross_provider_cache_reuse() -> None:
    other = SearchProviderReference("provider:other")
    assert search_cache_key(request(), PROVIDER) != search_cache_key(request(), other)
    assessed = assess_search_cache(search_entry(), request(), other, policy(), NOW + timedelta(seconds=5))
    assert assessed.status is CacheReadStatus.INVALID
    assert "cache-semantic-key-incompatible" in assessed.reasons


def test_retrieval_key_tracks_url_policy_types_and_limits_not_occurrence() -> None:
    original = retrieval_request()
    later = replace(original, occurrence=replace(original.occurrence, occurred_at=NOW))
    assert retrieval_cache_key(original) == retrieval_cache_key(later)
    assert retrieval_cache_key(original) != retrieval_cache_key(replace(original, maximum_bytes=999))
    assert retrieval_cache_key(original) != retrieval_cache_key(replace(original, accepted_content_types=("text/plain",)))
    assert retrieval_cache_key(original) != retrieval_cache_key(replace(original, source_url="https://other.example/a"))


def test_extraction_key_invalidates_checksum_extractor_and_output_policy() -> None:
    original = extraction_key()
    original_checksum = artifact().checksum
    assert original_checksum is not None
    changed_checksum = replace(original_checksum, value="sha256:" + "9" * 64)
    assert extraction_key(checksum=changed_checksum) != original
    assert extraction_key(extractor_version="text-extraction-adapter-v2") != original
    other_policy = extraction_cache_key(
        artifact(), extraction_request(), ExtractorReference("extractor:text-extraction-v1"),
        "text-extraction-adapter-v1", SearchFingerprint("sha256:" + "d" * 64)
    )
    assert other_policy != original


@pytest.mark.parametrize("seconds", [0, -1, 2_592_001, True])
def test_ttl_is_finite_bounded_and_explicit(seconds) -> None:
    with pytest.raises(Exception, match="TTL"):
        CacheTTLPolicy(seconds)
    assert policy().search_ttl != policy().retrieval_ttl != policy().extraction_ttl


def test_fresh_hit_preserves_original_and_separates_read_occurrence_and_age() -> None:
    entry = search_entry()
    read_at = NOW + timedelta(seconds=30)
    assessment = assess_search_cache(entry, request(), PROVIDER, policy(), read_at)
    assert assessment.status is CacheReadStatus.HIT_FRESH
    assert assessment.usable
    assert assessment.age_seconds == 30
    assert assessment.read_at == read_at
    assert assessment.cache_written_at == NOW
    assert assessment.original_observation_at == entry.result_set.search_occurrence.occurred_at
    assert assessment.original_observation_at != assessment.read_at


def test_expiry_is_stale_and_policy_never_silently_promotes_to_fresh() -> None:
    read_at = NOW + timedelta(seconds=60)
    fresh_only = assess_search_cache(search_entry(), request(), PROVIDER, policy(), read_at)
    assert fresh_only.status is CacheReadStatus.HIT_STALE
    assert not fresh_only.usable and fresh_only.revalidation_required
    stale_policy = policy(search_stale_usage=StaleUsagePolicy.STALE_ALLOWED)
    stale_entry = search_entry(
        policy_fingerprint=stale_policy.semantic_fingerprint,
        expires_at=NOW + timedelta(seconds=60),
    )
    allowed = assess_search_cache(stale_entry, request(), PROVIDER, stale_policy, read_at)
    assert allowed.status is CacheReadStatus.HIT_STALE
    assert allowed.usable and not allowed.revalidation_required


def test_miss_backend_unavailable_invalid_schema_policy_and_ttl_are_distinct() -> None:
    miss = assess_search_cache(None, request(), PROVIDER, policy(), NOW)
    unavailable = assess_search_cache(None, request(), PROVIDER, policy(), NOW, backend_available=False)
    assert miss.status is CacheReadStatus.MISS
    assert unavailable.status is CacheReadStatus.UNAVAILABLE
    incompatible_policy = replace(policy(), search_ttl=CacheTTLPolicy(61))
    invalid = assess_search_cache(search_entry(), request(), PROVIDER, incompatible_policy, NOW)
    assert invalid.status is CacheReadStatus.INVALID
    assert "cache-policy-mismatch" in invalid.reasons
    with pytest.raises(Exception, match="unsupported"):
        search_entry(format_version="search-cache-entry-v2")


def test_request_freshness_and_cache_freshness_are_separate() -> None:
    stricter = replace(request(), freshness=FreshnessConstraint(FreshnessKind.WINDOW, 60))
    assessment = assess_search_cache(search_entry(), stricter, PROVIDER, policy(), NOW + timedelta(seconds=1))
    assert assessment.status is CacheReadStatus.INVALID
    assert assessment.revalidation_required
    assert search_entry().expires_at > NOW


def test_no_results_requires_explicit_negative_cache_policy() -> None:
    no_results = result_set(results=(), outcome=SearchOutcomeCode.NO_RESULTS)
    entry = search_entry(result_set=no_results)
    denied = assess_search_cache(entry, request(), PROVIDER, policy(), NOW + timedelta(seconds=1))
    assert denied.status is CacheReadStatus.INVALID
    admitted_policy = policy(cache_no_results=True)
    admitted_entry = search_entry(policy_fingerprint=admitted_policy.semantic_fingerprint, result_set=no_results)
    assert assess_search_cache(admitted_entry, request(), PROVIDER, admitted_policy, NOW + timedelta(seconds=1)).status is CacheReadStatus.HIT_FRESH


def test_result_set_contract_prevents_provider_error_becoming_cached_success() -> None:
    with pytest.raises(Exception, match="successful Search outcome"):
        result_set(outcome="provider_unavailable")  # type: ignore[arg-type]


def test_missing_retrieval_reference_invalidates_metadata_only_hit() -> None:
    entry = retrieval_entry()
    available = assess_retrieval_cache(entry, retrieval_request(), policy(), NOW + timedelta(seconds=1), reference_available=True)
    missing = assess_retrieval_cache(entry, retrieval_request(), policy(), NOW + timedelta(seconds=1), reference_available=False)
    assert available.status is CacheReadStatus.HIT_FRESH
    assert missing.status is CacheReadStatus.INVALID
    assert "cache-content-reference-unavailable" in missing.reasons


def test_retrieval_validators_are_opaque_and_only_mark_revalidation_possible() -> None:
    entry = retrieval_entry(validator_references=(CacheValidatorReference("validator:etag-opaque"),))
    assessment = assess_retrieval_cache(entry, retrieval_request(), policy(), NOW + timedelta(seconds=120), reference_available=True)
    assert assessment.status is CacheReadStatus.HIT_STALE
    assert assessment.revalidation_possible


def test_missing_extracted_reference_and_artifact_checksum_mismatch_are_invalid() -> None:
    entry = extraction_entry()
    source = artifact()
    assert source.checksum is not None
    missing = assess_extraction_cache(entry, extraction_key(), source.checksum, policy(), NOW + timedelta(seconds=1), reference_available=False)
    assert missing.status is CacheReadStatus.INVALID
    other = replace(source.checksum, value="sha256:" + "8" * 64)
    mismatch = assess_extraction_cache(entry, extraction_key(), other, policy(), NOW + timedelta(seconds=1), reference_available=True)
    assert mismatch.status is CacheReadStatus.INVALID
    assert "artifact-checksum-mismatch" in mismatch.reasons


def test_payload_policy_never_grants_implicit_web_content_persistence() -> None:
    assert search_entry().payload_custody is PayloadCustody.METADATA_ONLY
    with pytest.raises(Exception, match="persistence"):
        retrieval_entry(payload_custody=PayloadCustody.EXPLICIT_PERSISTENCE_FUTURE)
    with pytest.raises(Exception, match="persistence"):
        extraction_entry(payload_custody=PayloadCustody.EXPLICIT_PERSISTENCE_FUTURE)


def test_duplicate_records_are_idempotent_or_contradictory_never_overwritten() -> None:
    entry = search_entry()
    assert classify_cache_record_repetition(None, entry) is CacheRecordRepetition.FIRST
    assert classify_cache_record_repetition(entry, entry) is CacheRecordRepetition.IDENTICAL
    changed = replace(entry, expires_at=entry.expires_at + timedelta(seconds=1))
    assert classify_cache_record_repetition(entry, changed) is CacheRecordRepetition.CONTRADICTORY
    with pytest.raises(Exception, match="different identity"):
        classify_cache_record_repetition(entry, replace(entry, entry_id=CacheEntryId("cache-entry:other")))


def test_contracts_are_immutable_and_canonical_serialization_is_deterministic() -> None:
    entry = search_entry()
    assessment = assess_search_cache(entry, request(), PROVIDER, policy(), NOW + timedelta(seconds=1))
    assert entry.canonical_serialization() == entry.canonical_serialization()
    assert policy().canonical_serialization() == policy().canonical_serialization()
    assert entry.key.canonical_serialization() == entry.key.canonical_serialization()
    assert assessment.canonical_serialization() == assessment.canonical_serialization()
    with pytest.raises(FrozenInstanceError):
        entry.expires_at = NOW  # type: ignore[misc]


def test_cache_read_occurrence_does_not_change_semantic_assessment_fingerprint() -> None:
    entry = search_entry()
    first = assess_search_cache(entry, request(), PROVIDER, policy(), NOW + timedelta(seconds=1))
    second = assess_search_cache(entry, request(), PROVIDER, policy(), NOW + timedelta(seconds=2))
    assert first.age_seconds != second.age_seconds
    assert first.semantic_fingerprint == second.semantic_fingerprint


def test_entry_versions_and_namespaces_are_explicit() -> None:
    assert search_entry().format_version == CACHE_ENTRY_FORMAT_V1
    assert retrieval_entry().cached_observation_version != extraction_entry().cached_observation_version
    assert len({search_entry().key.namespace_reference, retrieval_entry().key.namespace_reference, extraction_entry().key.namespace_reference}) == 3
