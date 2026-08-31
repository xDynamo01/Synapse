"""Consumer-owned provider boundary and factual invocation contracts for Search."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol, runtime_checkable

from .canonical import SEARCH_CANONICAL_FORMAT_V1, canonical_json, semantic_fingerprint
from .errors import SearchDiagnostic, SearchErrorCode, SearchValidationError
from .identities import (
    CausationReference,
    CorrelationReference,
    PolicyReference,
    SearchCapabilityReference,
    SearchDetailReference,
    SearchFingerprint,
    SearchInvocationId,
    SearchProviderReference,
    SearchRequestId,
)
from .models import SearchRequestV1
from .results import SearchOccurrence, SearchResultSetV1

SEARCH_PROVIDER_INVOCATION_FORMAT_V1 = "search-provider-invocation-v1"
SEARCH_PROVIDER_RESULT_FORMAT_V1 = "search-provider-result-v1"
SEARCH_PROVIDER_CAPABILITIES_FORMAT_V1 = "search-provider-capabilities-v1"
SEARCH_PROVIDER_HEALTH_FORMAT_V1 = "search-provider-health-v1"


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SearchValidationError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


class SearchProviderCapability(StrEnum):
    BASIC_WEB_SEARCH = "basic_web_search"
    LANGUAGE_FILTERING = "language_filtering"
    CATEGORY_FILTERING = "category_filtering"
    DOMAIN_CONSTRAINTS = "domain_constraints"
    FRESHNESS_CONSTRAINTS = "freshness_constraints"
    SAFE_SEARCH = "safe_search"
    RESULT_LIMIT = "result_limit"
    PROVIDER_REPORTED_DATES = "provider_reported_dates"


class CapabilitySupportStatus(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True, order=True)
class SearchProviderCapabilityFact:
    capability: SearchProviderCapability
    status: CapabilitySupportStatus
    detail_reference: SearchDetailReference | None = None


@dataclass(frozen=True, slots=True)
class SearchProviderCapabilitiesV1:
    provider: SearchProviderReference
    provider_type: SearchCapabilityReference
    manifest_reference: SearchDetailReference | None
    facts: tuple[SearchProviderCapabilityFact, ...]
    format_version: str = SEARCH_PROVIDER_CAPABILITIES_FORMAT_V1

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.facts, key=lambda item: item.capability.value))
        if len({item.capability for item in ordered}) != len(ordered):
            raise SearchValidationError("provider capability declaration contains duplicates")
        if not any(
            item.capability is SearchProviderCapability.BASIC_WEB_SEARCH
            for item in ordered
        ):
            raise SearchValidationError("provider must declare basic web-search capability")
        if self.format_version != SEARCH_PROVIDER_CAPABILITIES_FORMAT_V1:
            raise SearchValidationError("unsupported provider-capabilities format")
        object.__setattr__(self, "facts", ordered)

    def support_for(self, capability: SearchProviderCapability) -> CapabilitySupportStatus:
        return next(
            (item.status for item in self.facts if item.capability is capability),
            CapabilitySupportStatus.UNKNOWN,
        )

    def semantic_content(self) -> dict[str, object]:
        return {
            "format": self.format_version,
            "provider": self.provider,
            "provider_type": self.provider_type,
            "manifest_reference": self.manifest_reference,
            "facts": self.facts,
        }

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())

    def canonical_serialization(self) -> str:
        return canonical_json(
            {
                "canonical_format": SEARCH_CANONICAL_FORMAT_V1,
                "capabilities": self,
                "semantic_fingerprint": self.semantic_fingerprint,
            }
        )


def required_capabilities(request: SearchRequestV1) -> tuple[SearchProviderCapability, ...]:
    required = {
        SearchProviderCapability.BASIC_WEB_SEARCH,
        SearchProviderCapability.RESULT_LIMIT,
        SearchProviderCapability.SAFE_SEARCH,
    }
    if request.language is not None or request.locale is not None:
        required.add(SearchProviderCapability.LANGUAGE_FILTERING)
    if request.categories:
        required.add(SearchProviderCapability.CATEGORY_FILTERING)
    if request.domains.include or request.domains.exclude:
        required.add(SearchProviderCapability.DOMAIN_CONSTRAINTS)
    if request.freshness.kind.value != "none":
        required.add(SearchProviderCapability.FRESHNESS_CONSTRAINTS)
    return tuple(sorted(required, key=lambda item: item.value))


@dataclass(frozen=True, slots=True)
class ProviderTimeoutContract:
    timeout_seconds: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, int)
            or not 1 <= self.timeout_seconds <= 300
        ):
            raise SearchValidationError("provider timeout must be between 1 and 300 seconds")


@dataclass(frozen=True, slots=True)
class SearchProviderInvocationV1:
    invocation_id: SearchInvocationId
    request: SearchRequestV1
    request_id: SearchRequestId
    request_fingerprint: SearchFingerprint
    provider: SearchProviderReference
    required_capabilities: tuple[SearchProviderCapability, ...]
    correlation: CorrelationReference
    causation: tuple[CausationReference, ...]
    occurrence: SearchOccurrence
    timeout: ProviderTimeoutContract
    policy_reference: PolicyReference | None = None
    retry_of: SearchInvocationId | None = None
    format_version: str = SEARCH_PROVIDER_INVOCATION_FORMAT_V1

    def __post_init__(self) -> None:
        if self.request_id != self.request.request_id:
            raise SearchValidationError("invocation request identity mismatch")
        if self.request_fingerprint != self.request.semantic_fingerprint:
            raise SearchValidationError("invocation request fingerprint mismatch")
        required = required_capabilities(self.request)
        if tuple(sorted(set(self.required_capabilities), key=lambda item: item.value)) != required:
            raise SearchValidationError("invocation capability set does not match request constraints")
        if len(set(self.causation)) != len(self.causation):
            raise SearchValidationError("invocation causation references must be unique")
        if self.retry_of == self.invocation_id:
            raise SearchValidationError("retry must use a new provider invocation identity")
        if self.format_version != SEARCH_PROVIDER_INVOCATION_FORMAT_V1:
            raise SearchValidationError("unsupported provider-invocation format")

    def unsupported_capabilities(
        self, declaration: SearchProviderCapabilitiesV1
    ) -> tuple[SearchProviderCapability, ...]:
        if declaration.provider != self.provider:
            raise SearchValidationError("capability declaration provider mismatch")
        return tuple(
            capability
            for capability in self.required_capabilities
            if declaration.support_for(capability) is not CapabilitySupportStatus.SUPPORTED
        )

    def semantic_content(self) -> dict[str, object]:
        return {
            "format": self.format_version,
            "request_fingerprint": self.request_fingerprint,
            "provider": self.provider,
            "required_capabilities": self.required_capabilities,
            "timeout": self.timeout,
            "policy_reference": self.policy_reference,
        }

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())

    def canonical_serialization(self) -> str:
        return canonical_json(
            {
                "canonical_format": SEARCH_CANONICAL_FORMAT_V1,
                "invocation": self,
                "semantic_fingerprint": self.semantic_fingerprint,
            }
        )


class SearchProviderResultStatus(StrEnum):
    RESULTS = "results"
    NO_RESULTS = "no_results"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "timeout"
    MALFORMED_RESPONSE = "malformed_response"
    POLICY_BLOCKED = "policy_blocked"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"


class ProviderResultTimeliness(StrEnum):
    ON_TIME = "on_time"
    LATE = "late"


@dataclass(frozen=True, slots=True)
class SearchProviderResultV1:
    invocation_id: SearchInvocationId
    request_id: SearchRequestId
    request_fingerprint: SearchFingerprint
    provider: SearchProviderReference
    required_capabilities: tuple[SearchProviderCapability, ...]
    correlation: CorrelationReference
    status: SearchProviderResultStatus
    observed_at: datetime
    result_set: SearchResultSetV1 | None = None
    diagnostic: SearchDiagnostic | None = None
    completion_after_timeout: bool | None = None
    format_version: str = SEARCH_PROVIDER_RESULT_FORMAT_V1

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", _aware_utc(self.observed_at, "provider result occurrence"))
        success = self.status in {
            SearchProviderResultStatus.RESULTS,
            SearchProviderResultStatus.NO_RESULTS,
        }
        if success != (self.result_set is not None):
            raise SearchValidationError("provider result status and result-set presence contradict")
        if self.result_set is not None:
            expected = self.status.value
            if self.result_set.outcome.value != expected:
                raise SearchValidationError("provider result status and Search outcome mismatch")
            if (
                self.result_set.request_id != self.request_id
                or self.result_set.request_fingerprint != self.request_fingerprint
                or self.result_set.provider != self.provider
                or self.result_set.provider_invocation != self.invocation_id
            ):
                raise SearchValidationError("provider result-set correspondence mismatch")
        if self.status is SearchProviderResultStatus.TIMEOUT:
            if self.completion_after_timeout is not None:
                raise SearchValidationError("timeout cannot claim provider completion state")
        elif self.completion_after_timeout is not None:
            raise SearchValidationError("completion-after-timeout belongs only to timeout observations")
        if not success and self.diagnostic is None:
            raise SearchValidationError("non-success provider result requires a safe diagnostic")
        if self.diagnostic is not None and self.diagnostic.request_id not in {None, self.request_id}:
            raise SearchValidationError("provider diagnostic request mismatch")
        if self.format_version != SEARCH_PROVIDER_RESULT_FORMAT_V1:
            raise SearchValidationError("unsupported provider-result format")

    def validate_correspondence(self, invocation: SearchProviderInvocationV1) -> None:
        if (
            self.invocation_id != invocation.invocation_id
            or self.request_id != invocation.request_id
            or self.request_fingerprint != invocation.request_fingerprint
            or self.provider != invocation.provider
            or self.correlation != invocation.correlation
            or self.required_capabilities != invocation.required_capabilities
        ):
            raise SearchValidationError("provider result does not correspond to invocation")
        if self.observed_at < invocation.occurrence.occurred_at:
            raise SearchValidationError("provider result is stale relative to invocation occurrence")

    def timeliness_for(self, invocation: SearchProviderInvocationV1) -> ProviderResultTimeliness:
        self.validate_correspondence(invocation)
        deadline = invocation.occurrence.occurred_at + timedelta(
            seconds=invocation.timeout.timeout_seconds
        )
        return (
            ProviderResultTimeliness.LATE
            if self.observed_at > deadline
            else ProviderResultTimeliness.ON_TIME
        )

    def semantic_content(self) -> dict[str, object]:
        return {
            "format": self.format_version,
            "request_fingerprint": self.request_fingerprint,
            "provider": self.provider,
            "required_capabilities": self.required_capabilities,
            "status": self.status,
            "result_set_fingerprint": (
                self.result_set.semantic_fingerprint if self.result_set is not None else None
            ),
            "diagnostic_code": self.diagnostic.code if self.diagnostic is not None else None,
        }

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())

    def canonical_serialization(self) -> str:
        return canonical_json(
            {
                "canonical_format": SEARCH_CANONICAL_FORMAT_V1,
                "provider_result": self,
                "semantic_fingerprint": self.semantic_fingerprint,
            }
        )


class ProviderResultRepetition(StrEnum):
    FIRST_OBSERVATION = "first_observation"
    IDENTICAL_REPEAT = "identical_repeat"
    CONTRADICTORY_REPEAT = "contradictory_repeat"


def classify_provider_result_repetition(
    existing: SearchProviderResultV1 | None, observed: SearchProviderResultV1
) -> ProviderResultRepetition:
    if existing is None:
        return ProviderResultRepetition.FIRST_OBSERVATION
    if existing.invocation_id != observed.invocation_id:
        raise SearchValidationError("provider results belong to different invocations")
    if existing.semantic_fingerprint == observed.semantic_fingerprint:
        return ProviderResultRepetition.IDENTICAL_REPEAT
    return ProviderResultRepetition.CONTRADICTORY_REPEAT


class SearchProviderHealthStatus(StrEnum):
    UNCONFIGURED = "unconfigured"
    CONFIGURED = "configured"
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ProviderFactStatus(StrEnum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SearchProviderHealthV1:
    provider: SearchProviderReference
    status: SearchProviderHealthStatus
    observed_at: datetime
    capability_declaration_available: ProviderFactStatus
    configured: ProviderFactStatus
    reachable: ProviderFactStatus = ProviderFactStatus.UNKNOWN
    response_format_supported: ProviderFactStatus = ProviderFactStatus.UNKNOWN
    authorization_available: ProviderFactStatus = ProviderFactStatus.UNKNOWN
    network_egress_available: ProviderFactStatus = ProviderFactStatus.UNKNOWN
    adapter_reference: SearchDetailReference | None = None
    diagnostic_reference: SearchDetailReference | None = None
    format_version: str = SEARCH_PROVIDER_HEALTH_FORMAT_V1

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", _aware_utc(self.observed_at, "provider health occurrence"))
        if self.status is SearchProviderHealthStatus.AVAILABLE and any(
            fact is not ProviderFactStatus.YES
            for fact in (
                self.configured,
                self.reachable,
                self.response_format_supported,
                self.authorization_available,
                self.network_egress_available,
            )
        ):
            raise SearchValidationError("available provider requires explicit positive operational facts")
        if self.status is SearchProviderHealthStatus.UNCONFIGURED and self.configured is not ProviderFactStatus.NO:
            raise SearchValidationError("unconfigured health requires configured=no")
        if self.format_version != SEARCH_PROVIDER_HEALTH_FORMAT_V1:
            raise SearchValidationError("unsupported provider-health format")

    def semantic_content(self) -> dict[str, object]:
        return {
            "format": self.format_version,
            "provider": self.provider,
            "status": self.status,
            "capability_declaration_available": self.capability_declaration_available,
            "configured": self.configured,
            "reachable": self.reachable,
            "response_format_supported": self.response_format_supported,
            "authorization_available": self.authorization_available,
            "network_egress_available": self.network_egress_available,
            "adapter_reference": self.adapter_reference,
        }

    @property
    def semantic_fingerprint(self) -> SearchFingerprint:
        return semantic_fingerprint(self.semantic_content())


@dataclass(frozen=True, slots=True)
class SearchRuntimeProviderHealth:
    provider_contracts_available: bool
    composed_provider_count: int
    providers: tuple[SearchProviderHealthV1, ...]

    def __post_init__(self) -> None:
        if self.composed_provider_count < 0 or self.composed_provider_count != len(self.providers):
            raise SearchValidationError("Search provider-health composition facts are inconsistent")
        if len({item.provider for item in self.providers}) != len(self.providers):
            raise SearchValidationError("Search provider-health providers must be unique")


@runtime_checkable
class SearchProviderPort(Protocol):
    """Consumer-owned capability boundary; it grants no network authority."""

    def invoke(self, invocation: SearchProviderInvocationV1) -> SearchProviderResultV1: ...


def unsupported_capability_diagnostic(
    invocation: SearchProviderInvocationV1,
    declaration: SearchProviderCapabilitiesV1,
    *,
    observed_at: datetime,
    detail_reference: SearchDetailReference | None = None,
) -> SearchProviderResultV1 | None:
    unsupported = invocation.unsupported_capabilities(declaration)
    if not unsupported:
        return None
    return SearchProviderResultV1(
        invocation_id=invocation.invocation_id,
        request_id=invocation.request_id,
        request_fingerprint=invocation.request_fingerprint,
        provider=invocation.provider,
        required_capabilities=invocation.required_capabilities,
        correlation=invocation.correlation,
        status=SearchProviderResultStatus.UNSUPPORTED_CAPABILITY,
        observed_at=observed_at,
        diagnostic=SearchDiagnostic(
            SearchErrorCode.UNSUPPORTED_CAPABILITY,
            "Provider does not declare every required Search capability.",
            observed_at,
            request_id=invocation.request_id,
            detail_reference=detail_reference,
        ),
    )
