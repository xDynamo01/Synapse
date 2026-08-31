"""Pure SearXNG request translation and response parsing with no production transport."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast, runtime_checkable

from synapse.search import (
    CapabilitySupportStatus,
    DeduplicatedSearchViewV1,
    FreshnessFacts,
    FreshnessKind,
    NormalizedSearchResultV1,
    ProviderFactStatus,
    ProviderMetadataEntry,
    ProviderResultReference,
    PublicationDateProvenance,
    SafeSearchMode,
    SearchCapabilityReference,
    SearchDetailReference,
    SearchDiagnostic,
    SearchErrorCode,
    SearchOutcomeCode,
    SearchProviderCapabilitiesV1,
    SearchProviderCapability,
    SearchProviderCapabilityFact,
    SearchProviderHealthStatus,
    SearchProviderHealthV1,
    SearchProviderInvocationV1,
    SearchProviderResultStatus,
    SearchProviderResultV1,
    SearchResultId,
    SearchResultProvenance,
    SearchResultSetId,
    SearchResultSetProvenance,
    SearchResultSetV1,
    SearchSourceReference,
    SearchValidationError,
    build_deduplicated_view,
    normalize_search_url,
)

from .config import SearXNGAdapterConfig

SEARXNG_ADAPTER_VERSION = "searxng-adapter-v1"
_SAFE_SEARCH = {
    SafeSearchMode.OFF: "0",
    SafeSearchMode.MODERATE: "1",
    SafeSearchMode.STRICT: "2",
}
_WINDOW_RANGES = {86400: "day", 2592000: "month", 31536000: "year"}


@dataclass(frozen=True, slots=True)
class SearXNGTransportRequest:
    method: str
    endpoint_path: str
    parameters: tuple[tuple[str, str], ...]
    expected_format: str
    timeout_seconds: int

    def __post_init__(self) -> None:
        if self.method != "GET" or self.expected_format != "json":
            raise SearchValidationError("SearXNG transport representation is unsupported")
        if any(key.lower() in {"authorization", "api_key", "token"} for key, _ in self.parameters):
            raise SearchValidationError("SearXNG transport request cannot contain credentials")


@dataclass(frozen=True, slots=True)
class SearXNGTransportResponse:
    status_code: int
    payload: object
    observed_at: datetime

    def __post_init__(self) -> None:
        if not 100 <= self.status_code <= 599:
            raise SearchValidationError("SearXNG transport status is invalid")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise SearchValidationError("SearXNG response occurrence must be timezone-aware")
        object.__setattr__(self, "observed_at", self.observed_at.astimezone(UTC))


@runtime_checkable
class SearXNGTransportPort(Protocol):
    """Adapter-local transport boundary; it grants no egress authority."""

    def exchange(self, request: SearXNGTransportRequest) -> SearXNGTransportResponse: ...


class SearXNGTransportError(RuntimeError):
    """Safe transport failure without response payload or endpoint disclosure."""


class SearXNGTransportTimeout(SearXNGTransportError):
    pass


class SearXNGTransportUnavailable(SearXNGTransportError):
    pass


class SearXNGTransportMalformed(SearXNGTransportError):
    pass


class SearXNGTransportResponseTooLarge(SearXNGTransportError):
    pass


class SearXNGAdapter:
    def __init__(
        self,
        config: SearXNGAdapterConfig,
        transport: SearXNGTransportPort | None = None,
    ) -> None:
        self._config = config
        self._transport = transport

    @property
    def capabilities(self) -> SearchProviderCapabilitiesV1:
        supported = {
            SearchProviderCapability.BASIC_WEB_SEARCH,
            SearchProviderCapability.LANGUAGE_FILTERING,
            SearchProviderCapability.CATEGORY_FILTERING,
            SearchProviderCapability.FRESHNESS_CONSTRAINTS,
            SearchProviderCapability.SAFE_SEARCH,
            SearchProviderCapability.RESULT_LIMIT,
            SearchProviderCapability.PROVIDER_REPORTED_DATES,
        }
        return SearchProviderCapabilitiesV1(
            provider=self._config.provider,
            provider_type=SearchCapabilityReference("provider-type:searxng"),
            manifest_reference=SearchDetailReference(f"manifest:{SEARXNG_ADAPTER_VERSION}"),
            facts=tuple(
                SearchProviderCapabilityFact(
                    capability,
                    (
                        CapabilitySupportStatus.SUPPORTED
                        if capability in supported
                        else CapabilitySupportStatus.UNSUPPORTED
                    ),
                )
                for capability in SearchProviderCapability
            ),
        )

    @property
    def health(self) -> SearchProviderHealthV1:
        return SearchProviderHealthV1(
            provider=self._config.provider,
            status=SearchProviderHealthStatus.CONFIGURED,
            observed_at=datetime.now(UTC),
            capability_declaration_available=ProviderFactStatus.YES,
            configured=ProviderFactStatus.YES,
            reachable=ProviderFactStatus.UNKNOWN,
            response_format_supported=ProviderFactStatus.YES,
            authorization_available=ProviderFactStatus.UNKNOWN,
            network_egress_available=ProviderFactStatus.UNKNOWN,
            adapter_reference=SearchDetailReference(f"adapter:{SEARXNG_ADAPTER_VERSION}"),
        )

    def translate_invocation(
        self, invocation: SearchProviderInvocationV1
    ) -> SearXNGTransportRequest:
        if invocation.provider != self._config.provider:
            raise SearchValidationError("SearXNG adapter provider identity mismatch")
        unsupported = invocation.unsupported_capabilities(self.capabilities)
        if unsupported:
            raise SearchValidationError("SearXNG invocation requires unsupported capabilities")
        request = invocation.request
        params: list[tuple[str, str]] = [("q", request.query), ("format", "json")]
        language = request.language or request.locale
        if language is not None:
            params.append(("language", language))
        if request.categories:
            categories: list[str] = []
            for category in request.categories:
                mapped = self._config.category_for(category)
                if mapped is None:
                    raise SearchValidationError("Search category has no explicit SearXNG mapping")
                categories.append(mapped)
            params.append(("categories", ",".join(categories)))
        freshness = request.freshness
        if freshness.kind is not FreshnessKind.NONE:
            if freshness.kind is not FreshnessKind.WINDOW or freshness.window_seconds not in _WINDOW_RANGES:
                raise SearchValidationError("Search freshness constraint cannot be represented by SearXNG")
            params.append(("time_range", _WINDOW_RANGES[freshness.window_seconds]))
        params.append(("safesearch", _SAFE_SEARCH[request.safe_search]))
        params.append(("limit", str(request.result_limit)))
        return SearXNGTransportRequest(
            method="GET",
            endpoint_path=self._config.endpoint_path,
            parameters=tuple(params),
            expected_format=self._config.expected_format,
            timeout_seconds=invocation.timeout.timeout_seconds,
        )

    def invoke(self, invocation: SearchProviderInvocationV1) -> SearchProviderResultV1:
        try:
            transport_request = self.translate_invocation(invocation)
        except SearchValidationError:
            return self._failure(
                invocation,
                SearchProviderResultStatus.UNSUPPORTED_CAPABILITY,
                SearchErrorCode.UNSUPPORTED_CAPABILITY,
                "Invocation constraints cannot be represented by this SearXNG adapter.",
                invocation.occurrence.occurred_at,
            )
        if self._transport is None:
            return self._failure(
                invocation,
                SearchProviderResultStatus.PROVIDER_UNAVAILABLE,
                SearchErrorCode.PROVIDER_UNAVAILABLE,
                "No SearXNG transport is composed.",
                invocation.occurrence.occurred_at,
            )
        try:
            response = self._transport.exchange(transport_request)
        except SearXNGTransportTimeout:
            return self._failure(
                invocation,
                SearchProviderResultStatus.TIMEOUT,
                SearchErrorCode.PROVIDER_TIMEOUT,
                "SearXNG transport timed out; remote completion is unknown.",
                datetime.now(UTC),
            )
        except SearXNGTransportResponseTooLarge:
            return self._failure(
                invocation,
                SearchProviderResultStatus.MALFORMED_RESPONSE,
                SearchErrorCode.PAYLOAD_TOO_LARGE,
                "SearXNG response exceeded the admitted size.",
                datetime.now(UTC),
            )
        except SearXNGTransportMalformed:
            return self._failure(
                invocation,
                SearchProviderResultStatus.MALFORMED_RESPONSE,
                SearchErrorCode.PROVIDER_RESPONSE_MALFORMED,
                "SearXNG transport response was malformed.",
                datetime.now(UTC),
            )
        except SearXNGTransportUnavailable:
            return self._failure(
                invocation,
                SearchProviderResultStatus.PROVIDER_UNAVAILABLE,
                SearchErrorCode.PROVIDER_UNAVAILABLE,
                "SearXNG transport was unavailable.",
                datetime.now(UTC),
            )
        if response.status_code != 200:
            if response.status_code in {401, 403}:
                status = SearchProviderResultStatus.POLICY_BLOCKED
                code = SearchErrorCode.POLICY_BLOCKED
            elif response.status_code == 429 or response.status_code >= 500:
                status = SearchProviderResultStatus.PROVIDER_UNAVAILABLE
                code = SearchErrorCode.PROVIDER_UNAVAILABLE
            else:
                status = SearchProviderResultStatus.MALFORMED_RESPONSE
                code = SearchErrorCode.PROVIDER_RESPONSE_MALFORMED
            return self._failure(
                invocation,
                status,
                code,
                "SearXNG returned a non-success transport status.",
                response.observed_at,
            )
        return self.parse_response(invocation, response.payload, response.observed_at)

    def parse_response(
        self,
        invocation: SearchProviderInvocationV1,
        payload: object,
        observed_at: datetime,
    ) -> SearchProviderResultV1:
        if invocation.provider != self._config.provider:
            raise SearchValidationError("SearXNG response provider identity mismatch")
        if not isinstance(payload, Mapping) or "results" not in payload:
            return self._malformed(invocation, observed_at, "SearXNG root payload is malformed.")
        raw_results = payload["results"]
        if not isinstance(raw_results, list):
            return self._malformed(invocation, observed_at, "SearXNG results field is malformed.")
        normalized: list[NormalizedSearchResultV1] = []
        diagnostics: list[SearchDiagnostic] = []
        for position, raw_item in enumerate(raw_results, start=1):
            if not isinstance(raw_item, Mapping):
                return self._malformed(invocation, observed_at, "SearXNG result entry is malformed.")
            item = cast(Mapping[object, object], raw_item)
            parsed = self._parse_result(invocation, item, position, diagnostics)
            if parsed is None:
                return self._malformed(invocation, observed_at, "SearXNG result is missing required fields.")
            normalized.append(parsed)
        result_set = self._result_set(invocation, tuple(normalized), tuple(diagnostics))
        status = (
            SearchProviderResultStatus.RESULTS
            if normalized
            else SearchProviderResultStatus.NO_RESULTS
        )
        return SearchProviderResultV1(
            invocation_id=invocation.invocation_id,
            request_id=invocation.request_id,
            request_fingerprint=invocation.request_fingerprint,
            provider=invocation.provider,
            required_capabilities=invocation.required_capabilities,
            correlation=invocation.correlation,
            status=status,
            observed_at=observed_at,
            result_set=result_set,
        )

    def normalized_projection(
        self, provider_result: SearchProviderResultV1
    ) -> DeduplicatedSearchViewV1:
        if provider_result.result_set is None:
            raise SearchValidationError("SearXNG projection requires a successful result set")
        return build_deduplicated_view(provider_result.result_set)

    def _parse_result(
        self,
        invocation: SearchProviderInvocationV1,
        item: Mapping[object, object],
        position: int,
        diagnostics: list[SearchDiagnostic],
    ) -> NormalizedSearchResultV1 | None:
        url = item.get("url")
        title = item.get("title")
        if not isinstance(url, str) or not isinstance(title, str) or not title.strip():
            return None
        try:
            url_fact = normalize_search_url(url)
        except SearchValidationError:
            return None
        canonical = item.get("canonical_url")
        canonical_url = canonical if isinstance(canonical, str) else None
        if canonical_url is not None:
            try:
                normalize_search_url(canonical_url)
            except SearchValidationError:
                return None
        date_value = item.get("publishedDate", item.get("published_date"))
        publication_date = self._parse_date(date_value)
        if date_value is not None and publication_date is None:
            diagnostics.append(
                SearchDiagnostic(
                    SearchErrorCode.PROVENANCE_INCOMPLETE,
                    "SearXNG publication date was not parseable.",
                    invocation.occurrence.occurred_at,
                    request_id=invocation.request_id,
                )
            )
        result_token = self._token(invocation.invocation_id.value, str(position), url)
        result_id = SearchResultId(f"search-result:{result_token}")
        provider_result_reference = ProviderResultReference(
            f"provider-result:searxng-{result_token}"
        )
        metadata = self._metadata(item, url_fact.normalized_url_fingerprint.value)
        provenance = SearchResultProvenance(
            request_id=invocation.request_id,
            request_fingerprint=invocation.request_fingerprint,
            provider=invocation.provider,
            provider_invocation=invocation.invocation_id,
            result_id=result_id,
            provider_result_reference=provider_result_reference,
            source_url=url,
            search_occurrence=invocation.occurrence,
            provider_position=position,
            correlation=invocation.correlation,
            causation=invocation.causation,
        )
        freshness = FreshnessFacts.from_observation(
            invocation.request.freshness,
            publication_date=publication_date,
            provider_reported_date=publication_date,
            search_occurrence=invocation.occurrence,
        )
        snippet = item.get("content")
        language = item.get("language")
        content_type = item.get("mime_type")
        source_label = item.get("source")
        return NormalizedSearchResultV1(
            result_id=result_id,
            source_url=url,
            canonical_url=canonical_url,
            title=title,
            provider_snippet=snippet if isinstance(snippet, str) else None,
            source=SearchSourceReference(f"source:{url_fact.hostname}"),
            source_label=source_label if isinstance(source_label, str) else None,
            provider=invocation.provider,
            provider_result_reference=provider_result_reference,
            provider_position=position,
            normalized_rank=position,
            search_occurrence=invocation.occurrence,
            publication_date=publication_date,
            publication_date_provenance=(
                PublicationDateProvenance.PROVIDER_EXPLICIT
                if publication_date is not None
                else PublicationDateProvenance.UNKNOWN
            ),
            provider_reported_date=publication_date,
            language=language if isinstance(language, str) else None,
            content_type=content_type if isinstance(content_type, str) else None,
            freshness=freshness,
            provenance=provenance,
            provider_metadata=metadata,
        )

    @staticmethod
    def _metadata(
        item: Mapping[object, object], normalized_fingerprint: str
    ) -> tuple[ProviderMetadataEntry, ...]:
        metadata = [
            ProviderMetadataEntry("searxng", "normalized-url-fingerprint", normalized_fingerprint)
        ]
        engines = item.get("engines")
        if isinstance(engines, list) and all(isinstance(engine, str) for engine in engines):
            metadata.append(ProviderMetadataEntry("searxng", "engines", ",".join(engines)))
        engine = item.get("engine")
        if isinstance(engine, str):
            metadata.append(ProviderMetadataEntry("searxng", "engine", engine))
        category = item.get("category")
        if isinstance(category, str):
            metadata.append(ProviderMetadataEntry("searxng", "category", category))
        score = item.get("score")
        if isinstance(score, (str, int, float)) and not isinstance(score, bool):
            metadata.append(ProviderMetadataEntry("searxng", "score", str(score)))
        return tuple(metadata)

    @staticmethod
    def _parse_date(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(UTC)

    def _result_set(
        self,
        invocation: SearchProviderInvocationV1,
        results: tuple[NormalizedSearchResultV1, ...],
        diagnostics: tuple[SearchDiagnostic, ...],
    ) -> SearchResultSetV1:
        identity = self._token(invocation.invocation_id.value, "result-set")
        outcome = SearchOutcomeCode.RESULTS if results else SearchOutcomeCode.NO_RESULTS
        provenance = SearchResultSetProvenance(
            request_id=invocation.request_id,
            request_fingerprint=invocation.request_fingerprint,
            provider=invocation.provider,
            provider_invocation=invocation.invocation_id,
            search_occurrence=invocation.occurrence,
            correlation=invocation.correlation,
            causation=invocation.causation,
        )
        return SearchResultSetV1(
            result_set_id=SearchResultSetId(f"search-result-set:{identity}"),
            request_id=invocation.request_id,
            request_fingerprint=invocation.request_fingerprint,
            provider=invocation.provider,
            provider_invocation=invocation.invocation_id,
            outcome=outcome,
            results=results,
            search_occurrence=invocation.occurrence,
            provenance=provenance,
            diagnostics=diagnostics,
        )

    def _malformed(
        self, invocation: SearchProviderInvocationV1, observed_at: datetime, message: str
    ) -> SearchProviderResultV1:
        return self._failure(
            invocation,
            SearchProviderResultStatus.MALFORMED_RESPONSE,
            SearchErrorCode.PROVIDER_RESPONSE_MALFORMED,
            message,
            observed_at,
        )

    @staticmethod
    def _failure(
        invocation: SearchProviderInvocationV1,
        status: SearchProviderResultStatus,
        code: SearchErrorCode,
        message: str,
        observed_at: datetime,
    ) -> SearchProviderResultV1:
        return SearchProviderResultV1(
            invocation_id=invocation.invocation_id,
            request_id=invocation.request_id,
            request_fingerprint=invocation.request_fingerprint,
            provider=invocation.provider,
            required_capabilities=invocation.required_capabilities,
            correlation=invocation.correlation,
            status=status,
            observed_at=observed_at,
            diagnostic=SearchDiagnostic(code, message, observed_at, request_id=invocation.request_id),
        )

    @staticmethod
    def _token(*parts: str) -> str:
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]
