from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from synapse.commands.handlers.core_operations import CoreOperationsCommandHandler
from synapse.commands.services import CommandServices
from synapse.core.events import EventBus
from synapse.core.exceptions import PermissionDenied
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.core.serialization import load_structured_file
from synapse.search import (
    CorrelationReference,
    DeduplicatedSearchViewV1,
    PolicyReference,
    ProviderTimeoutContract,
    RequesterReference,
    SearchInvocationId,
    SearchOccurrence,
    SearchProviderInvocationV1,
    SearchProviderReference,
    SearchPurpose,
    SearchRequestId,
    SearchRequestOccurrence,
    SearchRequestV1,
    required_capabilities,
)
from synapse.search_adapters import SearXNGAdapter, SearXNGAdapterConfig
from synapse.search_integrations import (
    SearchConsumerExecution,
    SearchConsumerStatus,
    SearchToolConsumer,
)
from synapse.tools.base import ToolRegistry
from synapse.tools.builtin import WebSearchTool

NOW = datetime(2026, 8, 12, 12, tzinfo=UTC)


class _Execution:
    def __init__(self, observation: SearchConsumerExecution) -> None:
        self.observation = observation
        self.requests: list[SearchRequestV1] = []

    def execute(self, request: SearchRequestV1) -> SearchConsumerExecution:
        self.requests.append(request)
        return self.observation


def _result() -> tuple[object, DeduplicatedSearchViewV1]:
    request = SearchRequestV1(
        SearchRequestId("search-request:tool-result"),
        RequesterReference("agent:researcher"),
        "neutral query",
        SearchPurpose("tool.web-search"),
        CorrelationReference("correlation:tool-result"),
        SearchRequestOccurrence(NOW),
        policy_reference=PolicyReference("capability:web.search"),
    )
    provider = SearXNGAdapterConfig(
        provider=SearchProviderReference("provider:fake"),
        base_url="https://search.invalid",
    )
    invocation = SearchProviderInvocationV1(
        SearchInvocationId("search-invocation:tool-result"),
        request,
        request.request_id,
        request.semantic_fingerprint,
        provider.provider,
        required_capabilities(request),
        request.correlation,
        (),
        SearchOccurrence(NOW),
        ProviderTimeoutContract(10),
        request.policy_reference,
    )
    adapter = SearXNGAdapter(provider)
    result = adapter.parse_response(
        invocation,
        {
            "results": [
                {
                    "url": "https://example.com/source",
                    "title": "Source title",
                    "content": "Provider supplied snippet",
                    "publishedDate": "2026-08-11T10:00:00Z",
                }
            ]
        },
        NOW,
    )
    return result, adapter.normalized_projection(result)


def _permissions(tmp_path: Path, allowed: bool) -> PermissionManager:
    config = tmp_path / "config"
    config.mkdir()
    value = '{"subjects":{"agent:researcher":["web.search"]}}' if allowed else '{"subjects":{}}'
    (config / "permissions.yaml").write_text(value, encoding="utf-8")
    return PermissionManager(tmp_path, EventBus(tmp_path))


def test_tool_permission_allows_request_but_egress_denial_remains_separate(
    tmp_path: Path,
) -> None:
    execution = _Execution(
        SearchConsumerExecution(
            SearchConsumerStatus.DENIED,
            decision_reference="decision:denied",
            safe_message="Search egress was denied.",
        )
    )
    registry = ToolRegistry(_permissions(tmp_path, True), EventBus(tmp_path))
    registry.register(WebSearchTool(SearchToolConsumer(execution)))

    output = registry.execute(
        "web_search", PermissionContext("researcher", "agent"), {"query": "one query"}
    )

    assert output["status"] == "denied"
    assert output["decision_reference"] == "decision:denied"
    assert len(execution.requests) == 1


def test_missing_tool_permission_blocks_before_search_consumer(tmp_path: Path) -> None:
    execution = _Execution(SearchConsumerExecution(SearchConsumerStatus.RESULTS))
    registry = ToolRegistry(_permissions(tmp_path, False), EventBus(tmp_path))
    registry.register(WebSearchTool(SearchToolConsumer(execution)))

    with pytest.raises(PermissionDenied):
        registry.execute(
            "web_search", PermissionContext("researcher", "agent"), {"query": "blocked"}
        )
    assert execution.requests == []


def test_tool_maps_canonical_request_fields_and_enforces_result_limit() -> None:
    execution = _Execution(SearchConsumerExecution(SearchConsumerStatus.UNCONFIGURED))
    consumer = SearchToolConsumer(execution)
    output = consumer.search(
        "researcher",
        "agent",
        {
            "query": "  bounded query  ",
            "result_limit": 7,
            "language": "pt-BR",
            "correlation_id": "correlation:from-tool",
        },
    )
    request = execution.requests[0]
    assert request.query == "bounded query"
    assert request.result_limit == 7
    assert request.language == "pt-br"
    assert str(request.requester) == "agent:researcher"
    assert output["status"] == "unconfigured"
    with pytest.raises(ValueError):
        consumer.search(
            "researcher",
            "agent",
            {"query": "invalid limit", "result_limit": 51},
        )


def test_normalized_tool_projection_keeps_snippet_distinct_from_content_and_evidence() -> None:
    result, view = _result()
    execution = _Execution(
        SearchConsumerExecution(SearchConsumerStatus.RESULTS, result, view)  # type: ignore[arg-type]
    )
    output = SearchToolConsumer(execution).search(
        "researcher", "agent", {"query": "one query"}
    )
    item = output["results"][0]  # type: ignore[index]
    assert item["provider_snippet"] == "Provider supplied snippet"
    assert item["retrieved_content"] is None
    assert item["evidence"] is None
    assert item["rank"] == 1
    assert item["provenance_reference"].startswith("provider-result:")


@pytest.mark.parametrize(
    "status",
    [
        SearchConsumerStatus.UNCONFIGURED,
        SearchConsumerStatus.UNAVAILABLE,
        SearchConsumerStatus.APPROVAL_REQUIRED,
        SearchConsumerStatus.PROVIDER_UNAVAILABLE,
        SearchConsumerStatus.TIMEOUT,
        SearchConsumerStatus.MALFORMED_RESPONSE,
        SearchConsumerStatus.NO_RESULTS,
    ],
)
def test_tool_preserves_search_outcome_taxonomy(status: SearchConsumerStatus) -> None:
    output = SearchToolConsumer(_Execution(SearchConsumerExecution(status))).search(
        "owner", "user", {"query": "single operation"}
    )
    assert output["status"] == status.value


def test_default_web_search_is_factual_unconfigured_not_legacy_not_implemented() -> None:
    output = WebSearchTool().run(PermissionContext("owner"), query="one query")
    assert output["status"] == "unconfigured"
    assert output["provider_configured"] is False
    assert "not_implemented" not in repr(output)


def test_search_command_maps_delivery_status_without_provider_logic() -> None:
    class Tools:
        def execute(self, name, context, arguments):
            assert name == "web_search"
            return {"status": "approval_required", "message": "Approval is required."}

    handler = CoreOperationsCommandHandler(CommandServices(tools=Tools()))
    result = handler._search(PermissionContext("owner"), "query")
    assert result.status == "approval_required"
    assert result.output == "Approval is required."


def test_web_search_tool_has_no_provider_http_or_research_loop() -> None:
    import inspect

    source = inspect.getsource(WebSearchTool)
    assert "SearXNG" not in source
    assert "urllib" not in source
    assert "while " not in source
    assert source.count("self._consumer.search") == 1


def test_web_search_permission_is_canonical_and_reconciled_for_declaring_agents() -> None:
    root = Path(__file__).resolve().parents[1]
    permissions = load_structured_file(root / "data/config/permissions.yaml")["subjects"]
    declaring_agents = {
        path.parent.name
        for path in (root / "data/agents").glob("*/CONFIG.yaml")
        if "web.search" in path.read_text(encoding="utf-8")
    }
    granted_agents = {
        subject.removeprefix("agent:")
        for subject, values in permissions.items()
        if subject.startswith("agent:") and "web.search" in values
    }
    assert declaring_agents == granted_agents == {"artemis", "orchestrator", "researcher"}
    assert all(
        values.count("web.search") == 1
        for values in permissions.values()
        if "web.search" in values
    )
