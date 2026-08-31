"""Explicit opt-in local wiring for the Search Runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from synapse.search import PolicyReference, SearchPersistenceHealth, SearchPersistenceHealthState
from synapse.search_adapters import (
    HttpRetrievalAdapter,
    HttpRetrievalAdapterConfig,
    SearchSQLiteConfig,
    SearchSQLiteDatabase,
    SearXNGAdapter,
    SearXNGAdapterConfig,
    SearXNGHttpTransport,
    SearXNGHttpTransportConfig,
    SQLiteExtractionCacheStore,
    SQLiteRetrievalCacheStore,
    SQLiteSearchCacheStore,
    SQLiteSearchMetadataStore,
    TextExtractionAdapter,
    TextExtractionAdapterConfig,
)
from synapse.search_integrations import (
    AuthorizedHttpRetrievalExecutor,
    AuthorizedSearXNGExecutor,
    ConfiguredSearchOperation,
    SearchAssessmentFactoryPort,
    SearchConsumerExecutionPort,
    SearchGovernanceIntegration,
    SearchSourceEvidenceProjector,
    SearchToolConsumer,
)
from synapse.search_integrations.governance import SearchEgressAuthorityPort


class SearchConsumerPort(Protocol):
    def search(
        self, actor_id: str, actor_type: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        ...


class UnconfiguredSearchConsumer(SearchConsumerPort):
    def search(
        self, actor_id: str, actor_type: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        return {
            "status": "unconfigured",
            "results": [],
            "message": "Search provider is not configured.",
            "provider_configured": False,
        }


class CapabilityState(StrEnum):
    IMPLEMENTED = "implemented"
    CONFIGURED = "configured"
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    UNTESTED = "untested"
    NOT_EVALUATED = "not_evaluated"


@dataclass(frozen=True, slots=True)
class SearchPersistenceCompositionConfig:
    database_path: Path
    cache_persistence_policy: PolicyReference
    busy_timeout_ms: int = 5_000


@dataclass(frozen=True, slots=True)
class SearchProviderCompositionConfig:
    adapter: SearXNGAdapterConfig
    transport: SearXNGHttpTransportConfig = SearXNGHttpTransportConfig()


@dataclass(frozen=True, slots=True)
class SearchConsumerCompositionConfig:
    assessment_factory: SearchAssessmentFactoryPort
    timeout_seconds: int = 20


@dataclass(frozen=True, slots=True)
class SearchRuntimeConfig:
    persistence: SearchPersistenceCompositionConfig | None = None
    provider: SearchProviderCompositionConfig | None = None
    retrieval: HttpRetrievalAdapterConfig | None = None
    extraction: TextExtractionAdapterConfig | None = None
    consumer: SearchConsumerCompositionConfig | None = None


@dataclass(frozen=True, slots=True)
class SearchRuntimeDependencies:
    governance_authority: SearchEgressAuthorityPort | None = None


@dataclass(frozen=True, slots=True)
class SearchCapabilityHealth:
    domain_contracts: CapabilityState
    persistence: CapabilityState
    persistence_schema: CapabilityState
    searxng_adapter: CapabilityState
    searxng_transport: CapabilityState
    provider_configuration: CapabilityState
    governance: CapabilityState
    search_authorization: CapabilityState
    provider_reachability: CapabilityState
    provider_api: CapabilityState
    search_operational: CapabilityState
    http_retrieval_adapter: CapabilityState
    retrieval_governance: CapabilityState
    retrieval_reachability: CapabilityState
    text_extraction: CapabilityState
    pdf_extraction: CapabilityState
    search_cache: CapabilityState
    retrieval_cache: CapabilityState
    extraction_cache: CapabilityState
    consumer_integration: CapabilityState
    evidence_projection: CapabilityState


@dataclass(frozen=True, slots=True)
class SearchPersistenceComponents:
    database: SearchSQLiteDatabase
    metadata: SQLiteSearchMetadataStore
    search_cache: SQLiteSearchCacheStore
    retrieval_cache: SQLiteRetrievalCacheStore
    extraction_cache: SQLiteExtractionCacheStore


@dataclass(frozen=True, slots=True)
class SearchProviderComponents:
    transport: SearXNGHttpTransport
    adapter: SearXNGAdapter
    executor: AuthorizedSearXNGExecutor | None
    operation: ConfiguredSearchOperation | None


@dataclass(frozen=True, slots=True)
class SearchRuntimeComponents:
    persistence: SearchPersistenceComponents | None
    provider: SearchProviderComponents | None
    governance: SearchGovernanceIntegration | None
    retrieval: HttpRetrievalAdapter | None
    authorized_retrieval: AuthorizedHttpRetrievalExecutor | None
    extraction: TextExtractionAdapter | None
    search_execution: SearchConsumerExecutionPort | None
    tool_consumer: SearchConsumerPort
    evidence: SearchSourceEvidenceProjector


class SearchRuntime:
    def __init__(self, config: SearchRuntimeConfig, components: SearchRuntimeComponents) -> None:
        self._config = config
        self._components = components
        self._persistence_health: SearchPersistenceHealth | None = None

    @property
    def components(self) -> SearchRuntimeComponents:
        return self._components

    def initialize_persistence(self, occurrence: datetime) -> SearchPersistenceHealth:
        persistence = self._components.persistence
        if persistence is None:
            raise RuntimeError("Search persistence is not configured")
        persistence.database.migrate(occurrence)
        self._persistence_health = persistence.database.health()
        return self._persistence_health

    def probe_persistence(self) -> SearchPersistenceHealth:
        persistence = self._components.persistence
        if persistence is None:
            raise RuntimeError("Search persistence is not configured")
        self._persistence_health = persistence.database.health()
        return self._persistence_health

    def health(self) -> SearchCapabilityHealth:
        persistence = self._components.persistence
        provider = self._components.provider
        governance = self._components.governance
        schema = self._schema_state()
        configured_provider = provider is not None
        if provider is None:
            operational = CapabilityState.UNAVAILABLE
        elif governance is None or provider.operation is None:
            operational = CapabilityState.DEGRADED
        else:
            operational = CapabilityState.UNTESTED
        return SearchCapabilityHealth(
            CapabilityState.IMPLEMENTED,
            CapabilityState.CONFIGURED if persistence else CapabilityState.UNAVAILABLE,
            schema,
            CapabilityState.IMPLEMENTED,
            CapabilityState.IMPLEMENTED,
            CapabilityState.CONFIGURED if configured_provider else CapabilityState.UNAVAILABLE,
            CapabilityState.AVAILABLE if governance else CapabilityState.UNAVAILABLE,
            CapabilityState.NOT_EVALUATED,
            CapabilityState.UNTESTED if configured_provider else CapabilityState.UNAVAILABLE,
            CapabilityState.UNTESTED if configured_provider else CapabilityState.UNAVAILABLE,
            operational,
            CapabilityState.IMPLEMENTED,
            CapabilityState.AVAILABLE if governance else CapabilityState.UNAVAILABLE,
            CapabilityState.UNTESTED if self._components.retrieval else CapabilityState.UNAVAILABLE,
            CapabilityState.AVAILABLE if self._components.extraction else CapabilityState.UNAVAILABLE,
            CapabilityState.UNSUPPORTED,
            CapabilityState.AVAILABLE if persistence else CapabilityState.UNAVAILABLE,
            CapabilityState.AVAILABLE if persistence else CapabilityState.UNAVAILABLE,
            CapabilityState.AVAILABLE if persistence else CapabilityState.UNAVAILABLE,
            CapabilityState.AVAILABLE,
            CapabilityState.AVAILABLE,
        )

    def _schema_state(self) -> CapabilityState:
        if self._components.persistence is None:
            return CapabilityState.UNAVAILABLE
        if self._persistence_health is None:
            return CapabilityState.NOT_EVALUATED
        return (
            CapabilityState.AVAILABLE
            if self._persistence_health.state is SearchPersistenceHealthState.HEALTHY
            else CapabilityState.DEGRADED
        )


def build_search_runtime(
    config: SearchRuntimeConfig,
    dependencies: SearchRuntimeDependencies = SearchRuntimeDependencies(),
) -> SearchRuntime:
    """Wire configured components only; perform no I/O or authorization assessment."""

    governance = (
        SearchGovernanceIntegration(dependencies.governance_authority)
        if dependencies.governance_authority is not None
        else None
    )
    persistence = _build_persistence(config.persistence)
    retrieval = HttpRetrievalAdapter(config.retrieval) if config.retrieval is not None else None
    authorized_retrieval = (
        AuthorizedHttpRetrievalExecutor(retrieval, governance)
        if retrieval is not None and governance is not None
        else None
    )
    extraction = (
        TextExtractionAdapter(retrieval.content_store, config.extraction)
        if retrieval is not None and config.extraction is not None
        else None
    )
    provider = _build_provider(config, governance)
    execution = provider.operation if provider is not None else None
    consumer: SearchConsumerPort = (
        SearchToolConsumer(execution)
        if execution is not None
        else UnconfiguredSearchConsumer()
    )
    return SearchRuntime(
        config,
        SearchRuntimeComponents(
            persistence,
            provider,
            governance,
            retrieval,
            authorized_retrieval,
            extraction,
            execution,
            consumer,
            SearchSourceEvidenceProjector(),
        ),
    )


def _build_persistence(
    config: SearchPersistenceCompositionConfig | None,
) -> SearchPersistenceComponents | None:
    if config is None:
        return None
    database = SearchSQLiteDatabase(SearchSQLiteConfig(config.database_path, config.busy_timeout_ms))
    metadata = SQLiteSearchMetadataStore(database)
    return SearchPersistenceComponents(
        database,
        metadata,
        SQLiteSearchCacheStore(metadata, config.cache_persistence_policy),
        SQLiteRetrievalCacheStore(metadata, config.cache_persistence_policy),
        SQLiteExtractionCacheStore(metadata, config.cache_persistence_policy),
    )


def _build_provider(
    config: SearchRuntimeConfig,
    governance: SearchGovernanceIntegration | None,
) -> SearchProviderComponents | None:
    if config.provider is None:
        return None
    transport = SearXNGHttpTransport(config.provider.adapter, config.provider.transport)
    adapter = SearXNGAdapter(config.provider.adapter, transport)
    if governance is None or config.consumer is None:
        return SearchProviderComponents(transport, adapter, None, None)
    executor = AuthorizedSearXNGExecutor(adapter, governance, transport.health)
    operation = ConfiguredSearchOperation(
        config.provider.adapter.provider,
        governance,
        executor,
        config.consumer.assessment_factory,
        timeout_seconds=config.consumer.timeout_seconds,
    )
    return SearchProviderComponents(transport, adapter, executor, operation)
