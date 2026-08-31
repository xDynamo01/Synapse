from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.test_authorized_searxng_execution import _Handler, server

from synapse.intelligence_boundary.models import ProcessingBoundary
from synapse.search import PolicyReference, SearchProviderReference
from synapse.search_adapters import (
    HttpRetrievalAdapterConfig,
    SearXNGAdapterConfig,
    SearXNGHttpTransportConfig,
    TextExtractionAdapterConfig,
)
from synapse.search_composition import (
    CapabilityState,
    SearchConsumerCompositionConfig,
    SearchPersistenceCompositionConfig,
    SearchProviderCompositionConfig,
    SearchRuntimeConfig,
    SearchRuntimeDependencies,
    build_search_runtime,
)
from synapse.search_integrations import SearchEgressAssessmentRequestV1


class _AssessmentFactory:
    def create(self, request, invocation):
        raise AssertionError("build must not evaluate Search governance")


class _Authority:
    def preview_egress(self, request):
        raise AssertionError("build must not preview egress")

    def authorize_egress(self, request):
        raise AssertionError("build must not authorize egress")

    def validate_manifest(self, *args, **kwargs):
        raise AssertionError("build must not validate authorization")


class _AllowedAuthority:
    def _authorization(self):
        return SimpleNamespace(
            allowed=True,
            decision=SimpleNamespace(decision_id="decision:composition", approval_required=False),
            manifest=SimpleNamespace(
                manifest_id="manifest:composition",
                checksum="sha256:" + "4" * 64,
                expires_at=datetime(2099, 1, 1, tzinfo=UTC).isoformat(),
            ),
        )

    def preview_egress(self, request):
        return self._authorization()

    def authorize_egress(self, request):
        return self._authorization()

    def validate_manifest(self, manifest_id, **scope):
        return SimpleNamespace(manifest_id=manifest_id, **scope)


class _LocalAssessmentFactory:
    def __init__(self, destination: str) -> None:
        self.destination = destination

    def create(self, request, invocation):
        return SearchEgressAssessmentRequestV1.for_search(
            request,
            provider_reference=str(invocation.provider),
            destination_reference=self.destination,
            boundary=ProcessingBoundary.LOCAL_NETWORK,
            classified_asset_references=("asset:composition-query",),
            classification_reference="classification:composition-v1",
            minimization_reference="minimization:composition-v1",
            capability_reference="web.search",
            disclosed_payload_checksum="sha256:" + "2" * 64,
            original_payload_fingerprint="sha256:" + "3" * 64,
            deployment_reference="deployment:controlled-searxng",
            upstream_external_processing=False,
        ).bind_invocation(invocation)


def persistence(path: Path) -> SearchPersistenceCompositionConfig:
    return SearchPersistenceCompositionConfig(
        path,
        PolicyReference("policy:search-persistence-v1"),
    )


def provider(base_url: str = "http://127.0.0.1:9") -> SearchProviderCompositionConfig:
    return SearchProviderCompositionConfig(
        SearXNGAdapterConfig(SearchProviderReference("provider:local-searxng"), base_url),
        SearXNGHttpTransportConfig(allow_private_destination=True),
    )


def test_import_and_empty_build_are_side_effect_free_and_factually_unconfigured(tmp_path: Path) -> None:
    database_path = tmp_path / "not-created.sqlite3"
    runtime = build_search_runtime(SearchRuntimeConfig())
    health = runtime.health()
    assert not database_path.exists()
    assert health.domain_contracts is CapabilityState.IMPLEMENTED
    assert health.searxng_adapter is CapabilityState.IMPLEMENTED
    assert health.searxng_transport is CapabilityState.IMPLEMENTED
    assert health.provider_configuration is CapabilityState.UNAVAILABLE
    assert health.search_operational is CapabilityState.UNAVAILABLE
    assert health.search_authorization is CapabilityState.NOT_EVALUATED
    output = runtime.components.tool_consumer.search("owner", "user", {"query": "unused"})
    assert output["status"] == "unconfigured"


def test_persistence_build_is_lazy_and_activation_restart_is_explicit(tmp_path: Path) -> None:
    path = tmp_path / "search.sqlite3"
    config = SearchRuntimeConfig(persistence=persistence(path))
    first = build_search_runtime(config)
    assert not path.exists()
    assert first.health().persistence_schema is CapabilityState.NOT_EVALUATED
    initialized = first.initialize_persistence(datetime(2026, 8, 13, tzinfo=UTC))
    assert initialized.healthy and path.exists()

    restarted = build_search_runtime(config)
    assert restarted.health().persistence_schema is CapabilityState.NOT_EVALUATED
    assert restarted.probe_persistence().healthy
    assert restarted.health().persistence_schema is CapabilityState.AVAILABLE


def test_provider_configuration_does_not_probe_or_execute_and_missing_governance_fails_closed() -> None:
    runtime = build_search_runtime(
        SearchRuntimeConfig(
            provider=provider(),
            consumer=SearchConsumerCompositionConfig(_AssessmentFactory()),
        )
    )
    health = runtime.health()
    assert runtime.components.provider is not None
    assert runtime.components.provider.operation is None
    assert runtime.components.search_execution is None
    assert health.provider_configuration is CapabilityState.CONFIGURED
    assert health.provider_reachability is CapabilityState.UNTESTED
    assert health.provider_api is CapabilityState.UNTESTED
    assert health.governance is CapabilityState.UNAVAILABLE
    assert health.search_operational is CapabilityState.DEGRADED


def test_injected_governance_is_wired_but_never_evaluated_during_build() -> None:
    runtime = build_search_runtime(
        SearchRuntimeConfig(
            provider=provider(),
            consumer=SearchConsumerCompositionConfig(_AssessmentFactory()),
        ),
        SearchRuntimeDependencies(_Authority()),
    )
    assert runtime.components.provider is not None
    assert runtime.components.provider.operation is not None
    assert runtime.components.search_execution is runtime.components.provider.operation
    assert runtime.health().governance is CapabilityState.AVAILABLE
    assert runtime.health().search_operational is CapabilityState.UNTESTED


def test_retrieval_extraction_cache_consumer_and_evidence_capabilities_are_granular(
    tmp_path: Path,
) -> None:
    runtime = build_search_runtime(
        SearchRuntimeConfig(
            persistence=persistence(tmp_path / "search.sqlite3"),
            retrieval=HttpRetrievalAdapterConfig(allow_private_destinations=True),
            extraction=TextExtractionAdapterConfig(),
        )
    )
    health = runtime.health()
    assert runtime.components.retrieval is not None
    assert runtime.components.extraction is not None
    assert health.http_retrieval_adapter is CapabilityState.IMPLEMENTED
    assert health.retrieval_governance is CapabilityState.UNAVAILABLE
    assert health.retrieval_reachability is CapabilityState.UNTESTED
    assert health.text_extraction is CapabilityState.AVAILABLE
    assert health.pdf_extraction is CapabilityState.UNSUPPORTED
    assert health.search_cache is CapabilityState.AVAILABLE
    assert health.retrieval_cache is CapabilityState.AVAILABLE
    assert health.extraction_cache is CapabilityState.AVAILABLE
    assert health.consumer_integration is CapabilityState.AVAILABLE
    assert health.evidence_projection is CapabilityState.AVAILABLE


def test_extraction_requires_explicit_retrieval_configuration() -> None:
    runtime = build_search_runtime(
        SearchRuntimeConfig(extraction=TextExtractionAdapterConfig())
    )
    assert runtime.components.extraction is None
    assert runtime.health().text_extraction is CapabilityState.UNAVAILABLE


def test_build_has_no_global_ready_boolean_or_active_probe_surface() -> None:
    runtime = build_search_runtime(SearchRuntimeConfig(provider=provider()))
    assert "ready" not in {name for name in runtime.health().__dataclass_fields__}
    assert not hasattr(runtime, "probe_provider")
    assert not hasattr(runtime, "search_automatically")
    assert not hasattr(runtime, "retrieve_automatically")
    assert not hasattr(runtime, "extract_automatically")


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"results": []}, "no_results"),
        (
            {
                "results": [
                    {
                        "url": "https://example.com/source",
                        "title": "Controlled source",
                        "content": "Provider snippet only",
                    }
                ]
            },
            "results",
        ),
    ],
)
def test_explicit_authorized_search_through_composition_against_controlled_server(
    payload: object, expected: str
) -> None:
    with server(payload=payload) as base_url:
        runtime = build_search_runtime(
            SearchRuntimeConfig(
                provider=provider(base_url),
                consumer=SearchConsumerCompositionConfig(_LocalAssessmentFactory(base_url)),
            ),
            SearchRuntimeDependencies(_AllowedAuthority()),
        )
        assert _Handler.requests == 0
        result = runtime.components.tool_consumer.search(
            "researcher", "agent", {"query": "explicit controlled search"}
        )
        assert result["status"] == expected
        assert _Handler.requests == 1
