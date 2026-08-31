"""Reference-only Search integration with the authoritative egress boundary."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from synapse.intelligence_boundary.contracts import EgressDecisionPort, EgressGatePort
from synapse.intelligence_boundary.errors import (
    EgressApprovalRequired,
    EgressDenied,
    IntelligenceBoundaryError,
    StaleEgressManifest,
)
from synapse.intelligence_boundary.models import (
    EgressAuthorization,
    EgressRequest,
    ProcessingBoundary,
    ProcessingPurpose,
)
from synapse.search import RetrievalRequestV1, SearchProviderInvocationV1, SearchRequestV1


class SearchEgressOperation(StrEnum):
    SEARCH_PROVIDER_INVOCATION = "search_provider_invocation"
    SOURCE_RETRIEVAL = "source_retrieval"


class SearchAuthorizationStatus(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    APPROVAL_REQUIRED = "approval_required"
    UNAVAILABLE = "unavailable"


class AuthorizationEvidenceState(StrEnum):
    VALID = "valid"
    EXPIRED = "expired"
    STALE = "stale"
    MISMATCHED = "mismatched"
    INVALID = "invalid"


class SearchEgressAuthorityPort(EgressDecisionPort, EgressGatePort, Protocol):
    """Narrow consumer-owned view of Intelligence Boundary authority."""


@dataclass(frozen=True, slots=True)
class SearchEgressAssessmentRequestV1:
    operation: SearchEgressOperation
    request_reference: str
    requester_reference: str
    provider_reference: str | None
    destination_reference: str
    boundary: ProcessingBoundary
    purpose: ProcessingPurpose
    classified_asset_references: tuple[str, ...]
    classification_reference: str
    minimization_reference: str
    policy_reference: str
    capability_reference: str
    correlation_reference: str
    causation_references: tuple[str, ...]
    occurred_at: datetime
    semantic_fingerprint: str
    disclosed_payload_checksum: str
    original_payload_fingerprint: str
    deployment_reference: str | None = None
    upstream_external_processing: bool | None = None
    provider_invocation_reference: str | None = None

    def __post_init__(self) -> None:
        occurred_at = self.occurred_at
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("assessment occurrence must be timezone-aware")
        object.__setattr__(self, "occurred_at", occurred_at.astimezone(UTC))
        expected = {
            SearchEgressOperation.SEARCH_PROVIDER_INVOCATION: ProcessingPurpose.EXTERNAL_SEARCH,
            SearchEgressOperation.SOURCE_RETRIEVAL: ProcessingPurpose.EXTERNAL_RETRIEVAL,
        }
        if self.purpose is not expected[self.operation]:
            raise ValueError("operation and processing purpose do not correspond")
        if (
            not self.classified_asset_references
            or not self.classification_reference
            or not self.minimization_reference
        ):
            raise ValueError("classification evidence is required")
        if not self.policy_reference or not self.disclosed_payload_checksum:
            raise ValueError("policy and disclosed payload checksum are required")
        if not self.original_payload_fingerprint or not self.semantic_fingerprint:
            raise ValueError("original and semantic fingerprints are required")

    @classmethod
    def for_search(
        cls,
        request: SearchRequestV1,
        *,
        provider_reference: str,
        destination_reference: str,
        boundary: ProcessingBoundary,
        classified_asset_references: tuple[str, ...],
        classification_reference: str,
        minimization_reference: str,
        capability_reference: str,
        disclosed_payload_checksum: str,
        original_payload_fingerprint: str,
        deployment_reference: str | None = None,
        upstream_external_processing: bool | None = None,
    ) -> SearchEgressAssessmentRequestV1:
        if request.policy_reference is None:
            raise ValueError("Search egress requires an explicit policy reference")
        return cls(
            SearchEgressOperation.SEARCH_PROVIDER_INVOCATION,
            str(request.request_id),
            str(request.requester),
            provider_reference,
            destination_reference,
            boundary,
            ProcessingPurpose.EXTERNAL_SEARCH,
            classified_asset_references,
            classification_reference,
            minimization_reference,
            str(request.policy_reference),
            capability_reference,
            str(request.correlation),
            tuple(str(item) for item in request.causation),
            request.occurrence.occurred_at,
            str(request.semantic_fingerprint),
            disclosed_payload_checksum,
            original_payload_fingerprint,
            deployment_reference,
            upstream_external_processing,
        )

    @classmethod
    def for_retrieval(
        cls,
        request: RetrievalRequestV1,
        *,
        provider_reference: str | None,
        boundary: ProcessingBoundary,
        classified_asset_references: tuple[str, ...],
        classification_reference: str,
        minimization_reference: str,
        capability_reference: str,
        disclosed_payload_checksum: str,
        original_payload_fingerprint: str,
    ) -> SearchEgressAssessmentRequestV1:
        return cls(
            SearchEgressOperation.SOURCE_RETRIEVAL,
            str(request.retrieval_request_id),
            str(request.requester),
            provider_reference,
            request.source_url,
            boundary,
            ProcessingPurpose.EXTERNAL_RETRIEVAL,
            classified_asset_references,
            classification_reference,
            minimization_reference,
            str(request.policy_reference),
            capability_reference,
            str(request.correlation),
            tuple(str(item) for item in request.causation),
            request.occurrence.occurred_at,
            str(request.semantic_fingerprint),
            disclosed_payload_checksum,
            original_payload_fingerprint,
        )

    @property
    def binding_fingerprint(self) -> str:
        payload = {
            "operation": self.operation,
            "request": self.request_reference,
            "requester": self.requester_reference,
            "provider": self.provider_reference,
            "destination": self.destination_reference,
            "boundary": self.boundary,
            "purpose": self.purpose,
            "assets": self.classified_asset_references,
            "classification": self.classification_reference,
            "minimization": self.minimization_reference,
            "policy": self.policy_reference,
            "capability": self.capability_reference,
            "semantic_fingerprint": self.semantic_fingerprint,
            "payload_checksum": self.disclosed_payload_checksum,
            "original_payload_fingerprint": self.original_payload_fingerprint,
            "provider_invocation": self.provider_invocation_reference,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    def to_egress_request(self) -> EgressRequest:
        constraints = [
            f"classification_reference:{self.classification_reference}",
            f"minimization_reference:{self.minimization_reference}",
            f"policy_reference:{self.policy_reference}",
            f"capability_reference:{self.capability_reference}",
            f"binding_fingerprint:{self.binding_fingerprint}",
            f"original_payload_fingerprint:{self.original_payload_fingerprint}",
        ]
        if self.upstream_external_processing is not None:
            constraints.append(
                f"upstream_external_processing:{str(self.upstream_external_processing).lower()}"
            )
        return EgressRequest(
            asset_ids=self.classified_asset_references,
            requester=self.requester_reference,
            destination=self.destination_reference,
            boundary=self.boundary,
            purpose=self.purpose,
            provider_id=self.provider_reference,
            payload_checksum=self.disclosed_payload_checksum,
            correlation_id=self.correlation_reference,
            constraints=tuple(constraints),
        )

    def bind_invocation(
        self, invocation: SearchProviderInvocationV1
    ) -> SearchEgressAssessmentRequestV1:
        from dataclasses import replace

        if self.operation is not SearchEgressOperation.SEARCH_PROVIDER_INVOCATION:
            raise ValueError("Retrieval authorization cannot bind a provider invocation")
        if (
            self.request_reference != str(invocation.request_id)
            or self.requester_reference != str(invocation.request.requester)
            or self.provider_reference != str(invocation.provider)
            or self.semantic_fingerprint != str(invocation.request_fingerprint)
            or self.policy_reference
            != str(invocation.policy_reference or invocation.request.policy_reference)
            or self.correlation_reference != str(invocation.correlation)
        ):
            raise ValueError("provider invocation does not correspond to egress assessment")
        return replace(self, provider_invocation_reference=str(invocation.invocation_id))


@dataclass(frozen=True, slots=True)
class SearchAuthorizationEvidenceV1:
    decision_reference: str
    manifest_reference: str
    manifest_checksum: str
    status: SearchAuthorizationStatus
    operation: SearchEgressOperation
    request_reference: str
    requester_reference: str
    provider_reference: str | None
    destination_reference: str
    purpose: ProcessingPurpose
    classification_reference: str
    minimization_reference: str
    policy_reference: str
    binding_fingerprint: str
    payload_checksum: str
    expires_at: datetime
    provider_invocation_reference: str | None = None


@dataclass(frozen=True, slots=True)
class SearchEgressAssessmentV1:
    status: SearchAuthorizationStatus
    decision_reference: str | None
    policy_reference: str
    safe_reason_code: str
    authorization_evidence: SearchAuthorizationEvidenceV1 | None = None
    approval_reference: str | None = None

    @property
    def eligible_for_external_execution(self) -> bool:
        return self.status is SearchAuthorizationStatus.ALLOWED and self.authorization_evidence is not None


class SearchGovernanceIntegration:
    def __init__(self, authority: SearchEgressAuthorityPort) -> None:
        self._authority = authority

    def assess(self, request: SearchEgressAssessmentRequestV1) -> SearchEgressAssessmentV1:
        egress = request.to_egress_request()
        try:
            preview = self._authority.preview_egress(egress)
        except IntelligenceBoundaryError as exc:
            return self._unavailable(request, exc.code)
        except Exception:
            return self._unavailable(request, "governance_unavailable")

        if preview.decision.approval_required:
            return SearchEgressAssessmentV1(
                SearchAuthorizationStatus.APPROVAL_REQUIRED,
                preview.decision.decision_id,
                request.policy_reference,
                "approval_required",
            )
        if not preview.allowed:
            return SearchEgressAssessmentV1(
                SearchAuthorizationStatus.DENIED,
                preview.decision.decision_id,
                request.policy_reference,
                "egress_denied",
            )
        try:
            authorization = self._authority.authorize_egress(egress)
        except EgressApprovalRequired:
            return SearchEgressAssessmentV1(
                SearchAuthorizationStatus.APPROVAL_REQUIRED,
                preview.decision.decision_id,
                request.policy_reference,
                "approval_required",
            )
        except EgressDenied:
            return SearchEgressAssessmentV1(
                SearchAuthorizationStatus.DENIED,
                preview.decision.decision_id,
                request.policy_reference,
                "egress_denied",
            )
        except Exception:
            return self._unavailable(request, "governance_unavailable")
        evidence = self._evidence(request, authorization)
        if evidence is None:
            return self._unavailable(request, "authorization_evidence_missing")
        return SearchEgressAssessmentV1(
            SearchAuthorizationStatus.ALLOWED,
            authorization.decision.decision_id,
            request.policy_reference,
            "egress_allowed",
            evidence,
        )

    def validate_evidence(
        self,
        request: SearchEgressAssessmentRequestV1,
        evidence: SearchAuthorizationEvidenceV1,
        *,
        now: datetime | None = None,
    ) -> AuthorizationEvidenceState:
        expected = (
            evidence.status is SearchAuthorizationStatus.ALLOWED
            and evidence.operation is request.operation
            and evidence.request_reference == request.request_reference
            and evidence.requester_reference == request.requester_reference
            and evidence.provider_reference == request.provider_reference
            and evidence.destination_reference == request.destination_reference
            and evidence.purpose is request.purpose
            and evidence.classification_reference == request.classification_reference
            and evidence.minimization_reference == request.minimization_reference
            and evidence.policy_reference == request.policy_reference
            and evidence.binding_fingerprint == request.binding_fingerprint
            and evidence.payload_checksum == request.disclosed_payload_checksum
            and evidence.provider_invocation_reference
            == request.provider_invocation_reference
        )
        if not expected:
            return AuthorizationEvidenceState.MISMATCHED
        observed_at = (now or datetime.now(UTC)).astimezone(UTC)
        if evidence.expires_at <= observed_at:
            return AuthorizationEvidenceState.EXPIRED
        try:
            self._authority.validate_manifest(
                evidence.manifest_reference,
                payload_checksum=request.disclosed_payload_checksum,
                provider_id=request.provider_reference,
                destination=request.destination_reference,
                purpose=request.purpose.value,
            )
        except StaleEgressManifest:
            return AuthorizationEvidenceState.STALE
        except Exception:
            return AuthorizationEvidenceState.INVALID
        return AuthorizationEvidenceState.VALID

    @staticmethod
    def _evidence(
        request: SearchEgressAssessmentRequestV1,
        authorization: EgressAuthorization,
    ) -> SearchAuthorizationEvidenceV1 | None:
        manifest = authorization.manifest
        if not authorization.allowed or manifest is None:
            return None
        return SearchAuthorizationEvidenceV1(
            authorization.decision.decision_id,
            manifest.manifest_id,
            manifest.checksum,
            SearchAuthorizationStatus.ALLOWED,
            request.operation,
            request.request_reference,
            request.requester_reference,
            request.provider_reference,
            request.destination_reference,
            request.purpose,
            request.classification_reference,
            request.minimization_reference,
            request.policy_reference,
            request.binding_fingerprint,
            request.disclosed_payload_checksum,
            datetime.fromisoformat(manifest.expires_at).astimezone(UTC),
            request.provider_invocation_reference,
        )

    @staticmethod
    def _unavailable(
        request: SearchEgressAssessmentRequestV1, code: str
    ) -> SearchEgressAssessmentV1:
        safe_code = code if code in {"boundary_record_not_found"} else "governance_unavailable"
        return SearchEgressAssessmentV1(
            SearchAuthorizationStatus.UNAVAILABLE,
            None,
            request.policy_reference,
            safe_code,
        )
