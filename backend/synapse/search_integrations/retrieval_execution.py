"""Authorized execution boundary for one explicit HTTP Retrieval request."""

from __future__ import annotations

from datetime import UTC, datetime

from synapse.search import RetrievalAttemptId, RetrievalRequestV1, RetrievedArtifactV1
from synapse.search_adapters import HttpRetrievalAdapter

from .execution import SearchExecutionBlocked
from .governance import (
    AuthorizationEvidenceState,
    SearchAuthorizationEvidenceV1,
    SearchAuthorizationStatus,
    SearchEgressAssessmentRequestV1,
    SearchEgressAssessmentV1,
    SearchEgressOperation,
    SearchGovernanceIntegration,
)


class AuthorizedHttpRetrievalExecutor:
    def __init__(
        self, adapter: HttpRetrievalAdapter, governance: SearchGovernanceIntegration
    ) -> None:
        self._adapter = adapter
        self._governance = governance

    def execute(
        self,
        request: RetrievalRequestV1,
        attempt_id: RetrievalAttemptId,
        assessment_request: SearchEgressAssessmentRequestV1,
        assessment: SearchEgressAssessmentV1 | None,
        evidence: SearchAuthorizationEvidenceV1 | None,
        *,
        now: datetime | None = None,
    ) -> RetrievedArtifactV1:
        if assessment_request.operation is not SearchEgressOperation.SOURCE_RETRIEVAL:
            raise SearchExecutionBlocked("authorization_operation_mismatch")
        if (
            assessment_request.request_reference != str(request.retrieval_request_id)
            or assessment_request.requester_reference != str(request.requester)
            or assessment_request.destination_reference != request.source_url
            or assessment_request.policy_reference != str(request.policy_reference)
            or assessment_request.semantic_fingerprint != str(request.semantic_fingerprint)
        ):
            raise SearchExecutionBlocked("authorization_scope_mismatch")
        if assessment is None:
            raise SearchExecutionBlocked("authorization_missing")
        if assessment.status is not SearchAuthorizationStatus.ALLOWED:
            raise SearchExecutionBlocked(f"authorization_{assessment.status.value}")
        if evidence is None or evidence != assessment.authorization_evidence:
            raise SearchExecutionBlocked("authorization_evidence_missing")
        if (
            evidence.operation is not SearchEgressOperation.SOURCE_RETRIEVAL
            or evidence.request_reference != assessment_request.request_reference
            or evidence.requester_reference != assessment_request.requester_reference
            or evidence.destination_reference != assessment_request.destination_reference
            or evidence.policy_reference != assessment_request.policy_reference
            or evidence.binding_fingerprint != assessment_request.binding_fingerprint
            or evidence.payload_checksum != assessment_request.disclosed_payload_checksum
        ):
            raise SearchExecutionBlocked("authorization_scope_mismatch")
        state = self._governance.validate_evidence(
            assessment_request, evidence, now=now or datetime.now(UTC)
        )
        if state is not AuthorizationEvidenceState.VALID:
            raise SearchExecutionBlocked(f"authorization_{state.value}")
        artifact = self._adapter.retrieve(request, attempt_id)
        artifact.validate_correspondence(request)
        return artifact
