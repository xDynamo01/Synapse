from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from tests.test_http_retrieval_adapter import local_server
from tests.test_search_governance_integration import _Authority
from tests.test_search_retrieval_contracts import retrieval_request

from synapse.intelligence_boundary.models import ProcessingBoundary
from synapse.search import RetrievalAttemptId, RetrievalOutcome
from synapse.search_adapters import HttpRetrievalAdapter, HttpRetrievalAdapterConfig
from synapse.search_integrations import (
    AuthorizedHttpRetrievalExecutor,
    SearchAuthorizationStatus,
    SearchEgressAssessmentRequestV1,
    SearchExecutionBlocked,
    SearchGovernanceIntegration,
)

NOW = datetime(2026, 8, 12, 12, tzinfo=UTC)


def assessment_request(request):
    return SearchEgressAssessmentRequestV1.for_retrieval(
        request,
        provider_reference=None,
        boundary=ProcessingBoundary.LOCAL_NETWORK,
        classified_asset_references=("asset:retrieval-source",),
        classification_reference="classification:retrieval-v1",
        minimization_reference="minimization:retrieval-v1",
        capability_reference="web.retrieve",
        disclosed_payload_checksum="sha256:" + "2" * 64,
        original_payload_fingerprint="sha256:" + "3" * 64,
    )


@pytest.mark.parametrize(
    "status",
    ["denied", "approval_required", "unavailable"],
)
def test_blocked_retrieval_authorization_produces_zero_network_attempt(
    status: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = retrieval_request()
    authority = _Authority(status)
    governance = SearchGovernanceIntegration(authority)
    assessment_input = assessment_request(request)
    assessment = governance.assess(assessment_input)
    adapter = HttpRetrievalAdapter()
    attempts = 0

    def forbidden(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise AssertionError("network adapter must not run")

    monkeypatch.setattr(adapter, "retrieve", forbidden)
    with pytest.raises(SearchExecutionBlocked, match=f"authorization_{assessment.status.value}"):
        AuthorizedHttpRetrievalExecutor(adapter, governance).execute(
            request,
            RetrievalAttemptId("search-retrieval-attempt:blocked"),
            assessment_input,
            assessment,
            assessment.authorization_evidence,
            now=NOW,
        )
    assert attempts == 0


def test_search_authorization_or_missing_evidence_cannot_execute_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = retrieval_request()
    governance = SearchGovernanceIntegration(_Authority())
    assessment_input = assessment_request(request)
    allowed = governance.assess(assessment_input)
    assert allowed.status is SearchAuthorizationStatus.ALLOWED
    adapter = HttpRetrievalAdapter()
    attempts = 0

    def forbidden(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise AssertionError("network adapter must not run")

    monkeypatch.setattr(adapter, "retrieve", forbidden)
    with pytest.raises(SearchExecutionBlocked, match="authorization_evidence_missing"):
        AuthorizedHttpRetrievalExecutor(adapter, governance).execute(
            request,
            RetrievalAttemptId("search-retrieval-attempt:missing"),
            assessment_input,
            allowed,
            None,
            now=NOW,
        )
    assert attempts == 0


def test_explicit_authorized_retrieval_executes_once_against_controlled_server() -> None:
    with local_server() as base_url:
        request = replace(retrieval_request(), source_url=f"{base_url}/ok")
        governance = SearchGovernanceIntegration(_Authority())
        assessment_input = assessment_request(request)
        allowed = governance.assess(assessment_input)
        adapter = HttpRetrievalAdapter(
            HttpRetrievalAdapterConfig(allow_private_destinations=True)
        )
        artifact = AuthorizedHttpRetrievalExecutor(adapter, governance).execute(
            request,
            RetrievalAttemptId("search-retrieval-attempt:authorized"),
            assessment_input,
            allowed,
            allowed.authorization_evidence,
            now=NOW,
        )
        assert artifact.outcome is RetrievalOutcome.RETRIEVED
        assert artifact.source_url == request.source_url
