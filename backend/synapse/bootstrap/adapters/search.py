from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlparse

from synapse.core.data_dir import DataDir
from synapse.intelligence_boundary.contracts import (
    EgressDecisionPort,
    InformationAssetRegistrationPort,
)
from synapse.intelligence_boundary.models import (
    DataClassification,
    InformationAsset,
    InformationOwnership,
    ProcessingBoundary,
    TrainingUsePolicy,
)
from synapse.search import (
    PolicyReference,
    SearchProviderInvocationV1,
    SearchProviderReference,
    SearchRequestV1,
)
from synapse.search_adapters import SearXNGAdapterConfig, SearXNGHttpTransportConfig
from synapse.search_composition import (
    SearchConsumerCompositionConfig,
    SearchPersistenceCompositionConfig,
    SearchProviderCompositionConfig,
    SearchRuntime,
    SearchRuntimeConfig,
    SearchRuntimeDependencies,
    build_search_runtime,
)
from synapse.search_integrations import SearchEgressAssessmentRequestV1
from synapse.search_integrations.governance import SearchEgressAuthorityPort
from synapse.tools.models import ToolExecutionRequest
from synapse.tools.registry import RuntimeToolRegistry


class SearchBootstrapEgressPort(
    SearchEgressAuthorityPort,
    InformationAssetRegistrationPort,
    EgressDecisionPort,
    Protocol,
):
    """Boundary capabilities Search needs during bootstrap and execution."""


def configure_search_runtime(
    *,
    data_dir: DataDir,
    tools: RuntimeToolRegistry,
    egress_gate: SearchBootstrapEgressPort,
) -> SearchRuntime:
    base_url = os.environ.get("SYNAPSE_SEARXNG_URL", "").strip()
    runtime = build_search_runtime(
        _search_config(data_dir, base_url, egress_gate),
        SearchRuntimeDependencies(egress_gate),
    )
    if base_url:
        runtime.initialize_persistence(datetime.now(UTC))
        _replace_web_search_tool(tools, runtime)
    return runtime


def _search_config(
    data_dir: DataDir,
    base_url: str,
    egress_gate: SearchBootstrapEgressPort,
) -> SearchRuntimeConfig:
    if not base_url:
        return SearchRuntimeConfig()
    database_path = data_dir.resolve("search/search.sqlite3")
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return SearchRuntimeConfig(
        persistence=SearchPersistenceCompositionConfig(
            database_path,
            PolicyReference("policy:workplace-search-cache-v1"),
        ),
        provider=SearchProviderCompositionConfig(
            SearXNGAdapterConfig(SearchProviderReference("provider:local-searxng"), base_url),
            SearXNGHttpTransportConfig(allow_private_destination=_is_private_loopback(base_url)),
        ),
        consumer=SearchConsumerCompositionConfig(_WorkplaceSearchAssessmentFactory(egress_gate, base_url)),
    )


def _replace_web_search_tool(tools: RuntimeToolRegistry, search: SearchRuntime) -> None:
    current = tools.unregister("web_search")
    tools.register(current, lambda request: _run_web_search(search, request))


def _run_web_search(search: SearchRuntime, request: ToolExecutionRequest) -> dict[str, object]:
    query = str(request.arguments.get("query", "")).strip()
    if not query:
        raise ValueError("web_search requires query")
    arguments: dict[str, object] = {"query": query}
    for name in ("result_limit", "language", "locale", "correlation_id"):
        if request.arguments.get(name) is not None:
            arguments[name] = request.arguments[name]
    return dict(search.components.tool_consumer.search(request.caller, request.caller_type, arguments))


class _WorkplaceSearchAssessmentFactory:
    def __init__(self, egress_gate: SearchBootstrapEgressPort, destination: str) -> None:
        self._egress_gate = egress_gate
        self._destination = destination

    def create(
        self,
        request: SearchRequestV1,
        invocation: SearchProviderInvocationV1,
    ) -> SearchEgressAssessmentRequestV1:
        query_hash = hashlib.sha256(request.query.encode("utf-8")).hexdigest()
        asset_id = f"search_query_{query_hash[:24]}"
        try:
            asset = self._egress_gate.get_asset(asset_id)
        except Exception:
            asset = self._egress_gate.register_asset(
                InformationAsset(
                    asset_id=asset_id,
                    owner=InformationOwnership.USER,
                    source_domain="synapse.search",
                    source_reference=str(request.request_id),
                    content_type="text/search-query",
                    classification=DataClassification.PUBLIC,
                    categories=("web.search_query",),
                    retention_policy="metadata-only",
                    training_use_policy=TrainingUsePolicy.PROHIBITED,
                    external_processing_policy="policy-controlled",
                    checksum=f"sha256:{query_hash}",
                    metadata={
                        "estimated_tokens": max(1, len(request.query.split())),
                        "content_redacted": True,
                        "query_sha256": query_hash,
                    },
                )
        )
        payload_checksum = f"sha256:{hashlib.sha256(str(request.semantic_fingerprint).encode('utf-8')).hexdigest()}"
        return SearchEgressAssessmentRequestV1.for_search(
            request,
            provider_reference=str(invocation.provider),
            destination_reference=self._destination,
            boundary=ProcessingBoundary.LOCAL_NETWORK
            if _is_private_loopback(self._destination)
            else ProcessingBoundary.EXTERNAL_PROVIDER,
            classified_asset_references=(asset.asset_id,),
            classification_reference=f"classification:{asset.revision}:{asset.checksum}",
            minimization_reference="minimization:search-query-only",
            capability_reference="web.search",
            disclosed_payload_checksum=payload_checksum,
            original_payload_fingerprint=str(request.semantic_fingerprint),
            deployment_reference="deployment:workplace-search",
            upstream_external_processing=not _is_private_loopback(self._destination),
        ).bind_invocation(invocation)


def _is_private_loopback(base_url: str) -> bool:
    hostname = (urlparse(base_url).hostname or "").lower()
    return hostname in {"127.0.0.1", "localhost", "::1"}
