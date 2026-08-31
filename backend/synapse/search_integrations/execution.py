"""Opt-in authorized execution of one SearXNG provider invocation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from synapse.search import (
    DeduplicatedSearchViewV1,
    SearchProviderInvocationV1,
    SearchProviderResultStatus,
    SearchProviderResultV1,
)
from synapse.search_adapters import SearXNGAdapter
from synapse.search_adapters.searxng_transport import SearXNGTransportHealth

from .governance import (
    AuthorizationEvidenceState,
    SearchAuthorizationEvidenceV1,
    SearchAuthorizationStatus,
    SearchEgressAssessmentRequestV1,
    SearchEgressAssessmentV1,
    SearchEgressOperation,
    SearchGovernanceIntegration,
)


class SearchExecutionBlocked(RuntimeError):
    def __init__(self, safe_reason_code: str) -> None:
        self.safe_reason_code = safe_reason_code
        super().__init__(safe_reason_code)


@dataclass(frozen=True, slots=True)
class AuthorizedSearchExecutionV1:
    provider_result: SearchProviderResultV1
    normalized_view: DeduplicatedSearchViewV1 | None
    authorization_decision_reference: str
    authorization_manifest_reference: str
    authorization_validated_at: datetime


@dataclass(frozen=True, slots=True)
class OperationalSearchHealthV1:
    adapter_implemented: bool
    transport_implemented: bool
    configured: bool
    authorization_integration_available: bool
    provider_reachable: bool | None
    json_api_usable: bool | None
    search_operational: bool | None
    upstream_external_processing: bool | None


class AuthorizedSearXNGExecutor:
    def __init__(
        self,
        adapter: SearXNGAdapter,
        governance: SearchGovernanceIntegration,
        transport_health: SearXNGTransportHealth,
    ) -> None:
        self._adapter = adapter
        self._governance = governance
        self._transport_health = transport_health

    @property
    def health(self) -> OperationalSearchHealthV1:
        value = self._transport_health
        return OperationalSearchHealthV1(
            True,
            value.transport_implemented,
            value.configured,
            True,
            value.reachable,
            value.json_api_usable,
            value.search_operational,
            value.upstream_external_processing,
        )

    def execute(
        self,
        invocation: SearchProviderInvocationV1,
        assessment_request: SearchEgressAssessmentRequestV1,
        assessment: SearchEgressAssessmentV1 | None,
        evidence: SearchAuthorizationEvidenceV1 | None,
        *,
        now: datetime | None = None,
    ) -> AuthorizedSearchExecutionV1:
        if assessment_request.operation is not SearchEgressOperation.SEARCH_PROVIDER_INVOCATION:
            raise SearchExecutionBlocked("authorization_operation_mismatch")
        try:
            bound = assessment_request.bind_invocation(invocation)
        except ValueError as error:
            raise SearchExecutionBlocked("authorization_scope_mismatch") from error
        if assessment is None:
            raise SearchExecutionBlocked("authorization_missing")
        if assessment.status is not SearchAuthorizationStatus.ALLOWED:
            raise SearchExecutionBlocked(f"authorization_{assessment.status.value}")
        if evidence is None or assessment.authorization_evidence != evidence:
            raise SearchExecutionBlocked("authorization_evidence_missing")
        evidence_matches = (
            evidence.status is SearchAuthorizationStatus.ALLOWED
            and evidence.operation is bound.operation
            and evidence.request_reference == bound.request_reference
            and evidence.requester_reference == bound.requester_reference
            and evidence.provider_reference == bound.provider_reference
            and evidence.destination_reference == bound.destination_reference
            and evidence.purpose is bound.purpose
            and evidence.policy_reference == bound.policy_reference
            and evidence.binding_fingerprint == bound.binding_fingerprint
            and evidence.payload_checksum == bound.disclosed_payload_checksum
            and evidence.provider_invocation_reference
            == bound.provider_invocation_reference
        )
        if not evidence_matches:
            raise SearchExecutionBlocked("authorization_scope_mismatch")
        state = self._governance.validate_evidence(bound, evidence, now=now)
        if state is not AuthorizationEvidenceState.VALID:
            raise SearchExecutionBlocked(f"authorization_{state.value}")

        result = self._adapter.invoke(invocation)
        result.validate_correspondence(invocation)
        view = (
            self._adapter.normalized_projection(result)
            if result.status
            in {SearchProviderResultStatus.RESULTS, SearchProviderResultStatus.NO_RESULTS}
            else None
        )
        observed_at = (now or datetime.now(UTC)).astimezone(UTC)
        return AuthorizedSearchExecutionV1(
            result,
            view,
            evidence.decision_reference,
            evidence.manifest_reference,
            observed_at,
        )
