"""Single-operation consumer integration from Tools to Search contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

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
    SearchProviderResultStatus,
    SearchProviderResultV1,
    SearchPurpose,
    SearchRequestId,
    SearchRequestOccurrence,
    SearchRequestV1,
    required_capabilities,
)

from .execution import AuthorizedSearXNGExecutor, SearchExecutionBlocked
from .governance import (
    SearchAuthorizationStatus,
    SearchEgressAssessmentRequestV1,
    SearchGovernanceIntegration,
)


class SearchConsumerStatus(StrEnum):
    UNCONFIGURED = "unconfigured"
    UNAVAILABLE = "unavailable"
    DENIED = "denied"
    APPROVAL_REQUIRED = "approval_required"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TIMEOUT = "timeout"
    MALFORMED_RESPONSE = "malformed_response"
    NO_RESULTS = "no_results"
    RESULTS = "results"


@dataclass(frozen=True, slots=True)
class SearchConsumerExecution:
    status: SearchConsumerStatus
    result: SearchProviderResultV1 | None = None
    view: DeduplicatedSearchViewV1 | None = None
    decision_reference: str | None = None
    safe_message: str = "Search operation completed."


class SearchConsumerExecutionPort(Protocol):
    def execute(self, request: SearchRequestV1) -> SearchConsumerExecution: ...


class SearchAssessmentFactoryPort(Protocol):
    def create(
        self, request: SearchRequestV1, invocation: SearchProviderInvocationV1
    ) -> SearchEgressAssessmentRequestV1: ...


class ConfiguredSearchOperation:
    """One provider choice, one governance assessment and at most one invocation."""

    def __init__(
        self,
        provider: SearchProviderReference,
        governance: SearchGovernanceIntegration,
        executor: AuthorizedSearXNGExecutor,
        assessment_factory: SearchAssessmentFactoryPort,
        *,
        timeout_seconds: int = 20,
    ) -> None:
        self._provider = provider
        self._governance = governance
        self._executor = executor
        self._assessment_factory = assessment_factory
        self._timeout = ProviderTimeoutContract(timeout_seconds)

    def execute(self, request: SearchRequestV1) -> SearchConsumerExecution:
        invocation = SearchProviderInvocationV1(
            SearchInvocationId(f"search-invocation:{uuid4().hex}"),
            request,
            request.request_id,
            request.semantic_fingerprint,
            self._provider,
            required_capabilities(request),
            request.correlation,
            request.causation,
            SearchOccurrence(request.occurrence.occurred_at),
            self._timeout,
            request.policy_reference,
        )
        assessment_request = self._assessment_factory.create(request, invocation)
        assessment = self._governance.assess(assessment_request)
        if assessment.status is not SearchAuthorizationStatus.ALLOWED:
            mapped = {
                SearchAuthorizationStatus.DENIED: SearchConsumerStatus.DENIED,
                SearchAuthorizationStatus.APPROVAL_REQUIRED: SearchConsumerStatus.APPROVAL_REQUIRED,
                SearchAuthorizationStatus.UNAVAILABLE: SearchConsumerStatus.UNAVAILABLE,
            }[assessment.status]
            return SearchConsumerExecution(
                mapped,
                decision_reference=assessment.decision_reference,
                safe_message=assessment.safe_reason_code,
            )
        try:
            execution = self._executor.execute(
                invocation,
                assessment_request,
                assessment,
                assessment.authorization_evidence,
            )
        except SearchExecutionBlocked as error:
            return SearchConsumerExecution(
                SearchConsumerStatus.UNAVAILABLE,
                decision_reference=assessment.decision_reference,
                safe_message=error.safe_reason_code,
            )
        result = execution.provider_result
        mapped_result = {
            SearchProviderResultStatus.RESULTS: SearchConsumerStatus.RESULTS,
            SearchProviderResultStatus.NO_RESULTS: SearchConsumerStatus.NO_RESULTS,
            SearchProviderResultStatus.PROVIDER_UNAVAILABLE: SearchConsumerStatus.PROVIDER_UNAVAILABLE,
            SearchProviderResultStatus.TIMEOUT: SearchConsumerStatus.TIMEOUT,
            SearchProviderResultStatus.MALFORMED_RESPONSE: SearchConsumerStatus.MALFORMED_RESPONSE,
            SearchProviderResultStatus.POLICY_BLOCKED: SearchConsumerStatus.DENIED,
            SearchProviderResultStatus.UNSUPPORTED_CAPABILITY: SearchConsumerStatus.UNAVAILABLE,
        }[result.status]
        return SearchConsumerExecution(
            mapped_result,
            result,
            execution.normalized_view,
            execution.authorization_decision_reference,
            result.diagnostic.safe_message if result.diagnostic else "Search operation completed.",
        )


class SearchToolConsumer:
    """Maps one Tool call to one Search request; it performs no research loop."""

    def __init__(self, execution: SearchConsumerExecutionPort) -> None:
        self._execution = execution

    def search(
        self, actor_id: str, actor_type: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        request = self._request(actor_id, actor_type, arguments)
        observation = self._execution.execute(request)
        projected = self._project(observation)
        projected["request_reference"] = str(request.request_id)
        projected["request_fingerprint"] = str(request.semantic_fingerprint)
        projected["message"] = observation.safe_message
        if observation.decision_reference is not None:
            projected["decision_reference"] = observation.decision_reference
        return projected

    @staticmethod
    def _request(
        actor_id: str, actor_type: str, arguments: dict[str, object]
    ) -> SearchRequestV1:
        query = str(arguments.get("query", "")).strip()
        limit = arguments.get("result_limit", 10)
        correlation = str(arguments.get("correlation_id") or f"search-tool:{uuid4().hex}")
        return SearchRequestV1(
            request_id=SearchRequestId(f"search-request:{uuid4().hex}"),
            requester=RequesterReference(f"{actor_type}:{actor_id}"),
            query=query,
            purpose=SearchPurpose("tool.web-search"),
            correlation=CorrelationReference(correlation),
            occurrence=SearchRequestOccurrence(datetime.now(UTC)),
            language=str(arguments["language"]) if arguments.get("language") else None,
            locale=str(arguments["locale"]) if arguments.get("locale") else None,
            result_limit=limit if isinstance(limit, int) and not isinstance(limit, bool) else 0,
            policy_reference=PolicyReference("capability:web.search"),
        )

    @staticmethod
    def _project(observation: SearchConsumerExecution) -> dict[str, object]:
        output: dict[str, object] = {
            "status": observation.status.value,
            "results": [],
        }
        result = observation.result
        view = observation.view
        if result is None or view is None:
            return output
        output["provider_reference"] = str(result.provider)
        output["provider_invocation_reference"] = str(result.invocation_id)
        assert result.result_set is not None
        source_results = {item.result_id: item for item in result.result_set.results}
        output["results"] = [
            {
                "result_reference": str(source_results[item.result_id].result_id),
                "title": source_results[item.result_id].title,
                "source_url": source_results[item.result_id].source_url,
                "provider_snippet": source_results[item.result_id].provider_snippet,
                "source_reference": str(source_results[item.result_id].source),
                "rank": item.normalized_rank,
                "publication_date": (
                    published.isoformat()
                    if (published := source_results[item.result_id].publication_date)
                    else None
                ),
                "freshness": source_results[item.result_id].freshness.status.value,
                "provenance_reference": str(
                    source_results[item.result_id].provider_result_reference
                ),
                "retrieved_content": None,
                "evidence": None,
            }
            for item in view.deduplicated_ranked_view
        ]
        return output
