from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from synapse.intelligence_boundary.errors import StaleEgressManifest
from synapse.intelligence_boundary.models import ProcessingBoundary, ProcessingPurpose
from synapse.search_integrations import (
    AuthorizationEvidenceState,
    SearchAuthorizationStatus,
    SearchEgressAssessmentRequestV1,
    SearchEgressOperation,
    SearchGovernanceIntegration,
)

NOW = datetime(2026, 8, 12, 12, tzinfo=UTC)


def _request(
    operation: SearchEgressOperation = SearchEgressOperation.SEARCH_PROVIDER_INVOCATION,
) -> SearchEgressAssessmentRequestV1:
    retrieval = operation is SearchEgressOperation.SOURCE_RETRIEVAL
    return SearchEgressAssessmentRequestV1(
        operation=operation,
        request_reference="search-retrieval-request:r1" if retrieval else "search-request:r1",
        requester_reference="actor:researcher",
        provider_reference=None if retrieval else "provider:searxng",
        destination_reference="https://source.example/page" if retrieval else "http://localhost:8080",
        boundary=ProcessingBoundary.EXTERNAL_TOOL,
        purpose=(
            ProcessingPurpose.EXTERNAL_RETRIEVAL
            if retrieval
            else ProcessingPurpose.EXTERNAL_SEARCH
        ),
        classified_asset_references=("asset-query-1",),
        classification_reference="classification:query-1@v3",
        minimization_reference="minimization:query-1@v2",
        policy_reference="policy:web-search@v4",
        capability_reference="web.search",
        correlation_reference="correlation:1",
        causation_references=("cause:1",),
        occurred_at=NOW,
        semantic_fingerprint="sha256:" + "1" * 64,
        disclosed_payload_checksum="sha256:" + "2" * 64,
        original_payload_fingerprint="sha256:" + "3" * 64,
        deployment_reference="deployment:local-searxng" if not retrieval else None,
        upstream_external_processing=True if not retrieval else None,
    )


class _Authority:
    def __init__(self, status: str = "allowed") -> None:
        self.status = status
        self.authorize_calls = 0
        self.validated = False

    def _authorization(self, *, allowed: bool, approval: bool = False):  # type: ignore[no-untyped-def]
        decision = SimpleNamespace(
            decision_id=f"decision:{self.status}", approval_required=approval
        )
        manifest = SimpleNamespace(
            manifest_id=f"manifest:{self.status}",
            checksum="sha256:" + "4" * 64,
            expires_at=(NOW + timedelta(minutes=15)).isoformat(),
        )
        return SimpleNamespace(allowed=allowed, decision=decision, manifest=manifest)

    def preview_egress(self, request):  # type: ignore[no-untyped-def]
        if self.status == "unavailable":
            raise RuntimeError("secret endpoint details")
        if self.status == "approval_required":
            return self._authorization(allowed=False, approval=True)
        if self.status in {"denied", "trust_unknown"}:
            return self._authorization(allowed=False)
        return self._authorization(allowed=True)

    def authorize_egress(self, request):  # type: ignore[no-untyped-def]
        self.authorize_calls += 1
        if self.status == "missing_evidence":
            authorization = self._authorization(allowed=True)
            authorization.manifest = None
            return authorization
        return self._authorization(allowed=True)

    def validate_manifest(self, manifest_id, **scope):  # type: ignore[no-untyped-def]
        self.validated = True
        if self.status == "stale":
            raise StaleEgressManifest("changed trust profile")
        if self.status == "invalid":
            raise RuntimeError("revoked or unavailable evidence")
        return SimpleNamespace(manifest_id=manifest_id, **scope)


@pytest.mark.parametrize(
    ("authority_status", "expected"),
    [
        ("allowed", SearchAuthorizationStatus.ALLOWED),
        ("denied", SearchAuthorizationStatus.DENIED),
        ("approval_required", SearchAuthorizationStatus.APPROVAL_REQUIRED),
        ("unavailable", SearchAuthorizationStatus.UNAVAILABLE),
        ("trust_unknown", SearchAuthorizationStatus.DENIED),
        ("missing_evidence", SearchAuthorizationStatus.UNAVAILABLE),
    ],
)
def test_search_assessment_fails_closed_and_only_allowed_reaches_gate(
    authority_status: str, expected: SearchAuthorizationStatus
) -> None:
    authority = _Authority(authority_status)
    result = SearchGovernanceIntegration(authority).assess(_request())  # type: ignore[arg-type]

    assert result.status is expected
    assert result.eligible_for_external_execution is (expected is SearchAuthorizationStatus.ALLOWED)
    expected_gate_calls = 1 if authority_status in {"allowed", "missing_evidence"} else 0
    assert authority.authorize_calls == expected_gate_calls
    assert "secret" not in result.safe_reason_code


def test_allowed_evidence_preserves_policy_classification_minimization_provenance() -> None:
    request = _request()
    result = SearchGovernanceIntegration(_Authority()).assess(request)  # type: ignore[arg-type]

    evidence = result.authorization_evidence
    assert evidence is not None
    assert evidence.policy_reference == request.policy_reference
    assert evidence.classification_reference == request.classification_reference
    assert evidence.minimization_reference == request.minimization_reference
    assert evidence.payload_checksum == request.disclosed_payload_checksum
    assert evidence.binding_fingerprint == request.binding_fingerprint
    assert (
        f"original_payload_fingerprint:{request.original_payload_fingerprint}"
        in request.to_egress_request().constraints
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider_reference", "provider:other"),
        ("request_reference", "search-request:other"),
        ("purpose", ProcessingPurpose.EXTERNAL_RETRIEVAL),
        ("requester_reference", "actor:other"),
        ("destination_reference", "https://other.example"),
    ],
)
def test_authorization_evidence_cannot_be_reused_outside_its_scope(
    field: str, value: object
) -> None:
    request = _request()
    integration = SearchGovernanceIntegration(_Authority())  # type: ignore[arg-type]
    evidence = integration.assess(request).authorization_evidence
    assert evidence is not None

    assert replace(evidence, **{field: value})
    assert integration.validate_evidence(request, replace(evidence, **{field: value}), now=NOW) is AuthorizationEvidenceState.MISMATCHED


def test_expired_historical_allow_is_not_current_authorization() -> None:
    request = _request()
    integration = SearchGovernanceIntegration(_Authority())  # type: ignore[arg-type]
    evidence = integration.assess(request).authorization_evidence
    assert evidence is not None

    assert integration.validate_evidence(request, evidence, now=evidence.expires_at) is AuthorizationEvidenceState.EXPIRED


def test_authority_can_mark_matching_evidence_stale() -> None:
    request = _request()
    authority = _Authority()
    integration = SearchGovernanceIntegration(authority)  # type: ignore[arg-type]
    evidence = integration.assess(request).authorization_evidence
    assert evidence is not None
    authority.status = "stale"

    assert integration.validate_evidence(request, evidence, now=NOW) is AuthorizationEvidenceState.STALE


def test_revoked_or_invalid_evidence_fails_closed() -> None:
    request = _request()
    authority = _Authority()
    integration = SearchGovernanceIntegration(authority)  # type: ignore[arg-type]
    evidence = integration.assess(request).authorization_evidence
    assert evidence is not None
    authority.status = "invalid"

    assert integration.validate_evidence(request, evidence, now=NOW) is AuthorizationEvidenceState.INVALID


def test_search_authorization_is_not_retrieval_authorization() -> None:
    integration = SearchGovernanceIntegration(_Authority())  # type: ignore[arg-type]
    search = _request()
    retrieval = _request(SearchEgressOperation.SOURCE_RETRIEVAL)
    evidence = integration.assess(search).authorization_evidence
    assert evidence is not None

    assert integration.validate_evidence(retrieval, evidence, now=NOW) is AuthorizationEvidenceState.MISMATCHED


def test_local_searxng_does_not_hide_upstream_external_processing() -> None:
    request = _request()

    assert request.deployment_reference == "deployment:local-searxng"
    assert request.upstream_external_processing is True
    assert "upstream_external_processing:true" in request.to_egress_request().constraints
    assert request.boundary is ProcessingBoundary.EXTERNAL_TOOL


def test_capability_permission_and_adapter_safety_are_not_governance_authorization() -> None:
    request = _request(SearchEgressOperation.SOURCE_RETRIEVAL)

    assert request.capability_reference == "web.search"
    assert request.destination_reference.startswith("https://")
    assert SearchGovernanceIntegration(_Authority("unavailable")).assess(request).status is SearchAuthorizationStatus.UNAVAILABLE  # type: ignore[arg-type]


def test_integration_performs_no_network_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("network execution is outside this integration")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    result = SearchGovernanceIntegration(_Authority()).assess(_request())  # type: ignore[arg-type]

    assert result.status is SearchAuthorizationStatus.ALLOWED
