from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator

import pytest

from synapse.intelligence_boundary.models import ProcessingBoundary, ProcessingPurpose
from synapse.search import (
    CorrelationReference,
    PolicyReference,
    ProviderResultRepetition,
    ProviderTimeoutContract,
    RequesterReference,
    SearchInvocationId,
    SearchOccurrence,
    SearchProviderInvocationV1,
    SearchProviderReference,
    SearchProviderResultStatus,
    SearchPurpose,
    SearchRequestId,
    SearchRequestOccurrence,
    SearchRequestV1,
    classify_provider_result_repetition,
    required_capabilities,
)
from synapse.search_adapters import (
    SearXNGAdapter,
    SearXNGAdapterConfig,
    SearXNGHttpTransport,
    SearXNGHttpTransportConfig,
)
from synapse.search_integrations import (
    AuthorizationEvidenceState,
    AuthorizedSearXNGExecutor,
    SearchAuthorizationEvidenceV1,
    SearchAuthorizationStatus,
    SearchEgressAssessmentRequestV1,
    SearchEgressAssessmentV1,
    SearchEgressOperation,
    SearchExecutionBlocked,
)

NOW = datetime.now(UTC)
PROVIDER = SearchProviderReference("provider:searxng-local")


class _Handler(BaseHTTPRequestHandler):
    requests = 0
    status = 200
    body = b'{"results": []}'
    delay = 0.0
    redirect: str | None = None
    declared_length: int | None = None

    def do_GET(self) -> None:
        type(self).requests += 1
        if type(self).delay:
            time.sleep(type(self).delay)
        if type(self).redirect is not None and self.path.startswith("/search"):
            self.send_response(302)
            self.send_header("Location", type(self).redirect)
            self.end_headers()
            return
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        if type(self).declared_length != -1:
            self.send_header(
                "Content-Length",
                str(type(self).declared_length or len(type(self).body)),
            )
        self.end_headers()
        try:
            self.wfile.write(type(self).body)
        except BrokenPipeError:
            pass

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def server(
    *,
    status: int = 200,
    payload: object = None,
    raw: bytes | None = None,
    delay: float = 0.0,
    redirect: str | None = None,
    declared_length: int | None = None,
) -> Iterator[str]:
    _Handler.requests = 0
    _Handler.status = status
    _Handler.body = raw if raw is not None else json.dumps(payload or {"results": []}).encode()
    _Handler.delay = delay
    _Handler.redirect = redirect
    _Handler.declared_length = declared_length
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


class _Governance:
    def __init__(self, state: AuthorizationEvidenceState = AuthorizationEvidenceState.VALID) -> None:
        self.state = state
        self.validations = 0

    def validate_evidence(self, request, evidence, *, now=None):  # type: ignore[no-untyped-def]
        self.validations += 1
        return self.state


def invocation(*, timeout: int = 3) -> SearchProviderInvocationV1:
    request = SearchRequestV1(
        SearchRequestId("search-request:operational-1"),
        RequesterReference("actor:researcher"),
        "controlled neutral query",
        SearchPurpose("technical.research"),
        CorrelationReference("correlation:operational-1"),
        SearchRequestOccurrence(NOW),
        policy_reference=PolicyReference("policy:web-search@v4"),
    )
    return SearchProviderInvocationV1(
        SearchInvocationId("search-invocation:operational-1"),
        request,
        request.request_id,
        request.semantic_fingerprint,
        PROVIDER,
        required_capabilities(request),
        request.correlation,
        (),
        SearchOccurrence(NOW),
        ProviderTimeoutContract(timeout),
        request.policy_reference,
    )


def authorization(
    value: SearchProviderInvocationV1, destination: str
) -> tuple[SearchEgressAssessmentRequestV1, SearchEgressAssessmentV1, SearchAuthorizationEvidenceV1]:
    request = SearchEgressAssessmentRequestV1.for_search(
        value.request,
        provider_reference=str(value.provider),
        destination_reference=destination,
        boundary=ProcessingBoundary.LOCAL_NETWORK,
        classified_asset_references=("asset-query-1",),
        classification_reference="classification:query-1@v3",
        minimization_reference="minimization:query-1@v2",
        capability_reference="web.search",
        disclosed_payload_checksum="sha256:" + "2" * 64,
        original_payload_fingerprint="sha256:" + "3" * 64,
        deployment_reference="deployment:controlled-searxng",
        upstream_external_processing=True,
    ).bind_invocation(value)
    evidence = SearchAuthorizationEvidenceV1(
        "decision:allowed",
        "manifest:allowed",
        "sha256:" + "4" * 64,
        SearchAuthorizationStatus.ALLOWED,
        SearchEgressOperation.SEARCH_PROVIDER_INVOCATION,
        request.request_reference,
        request.requester_reference,
        request.provider_reference,
        request.destination_reference,
        ProcessingPurpose.EXTERNAL_SEARCH,
        request.classification_reference,
        request.minimization_reference,
        request.policy_reference,
        request.binding_fingerprint,
        request.disclosed_payload_checksum,
        NOW + timedelta(minutes=15),
        request.provider_invocation_reference,
    )
    return request, SearchEgressAssessmentV1(
        SearchAuthorizationStatus.ALLOWED,
        evidence.decision_reference,
        request.policy_reference,
        "egress_allowed",
        evidence,
    ), evidence


def executor(base_url: str, governance: _Governance, *, endpoint: str = "/search", limit: int = 4096) -> AuthorizedSearXNGExecutor:
    config = SearXNGAdapterConfig(PROVIDER, base_url, endpoint_path=endpoint)
    transport = SearXNGHttpTransport(
        config,
        SearXNGHttpTransportConfig(
            maximum_response_bytes=limit,
            allow_private_destination=True,
        ),
    )
    adapter = SearXNGAdapter(config, transport)
    return AuthorizedSearXNGExecutor(adapter, governance, transport.health)  # type: ignore[arg-type]


def execute(base_url: str, *, governance_state: AuthorizationEvidenceState = AuthorizationEvidenceState.VALID):
    value = invocation()
    request, assessment, evidence = authorization(value, base_url)
    return executor(base_url, _Governance(governance_state)).execute(
        value, request, assessment, evidence, now=NOW
    )


def test_allowed_authorization_executes_and_builds_normalized_deduplicated_view() -> None:
    payload = {"results": [{"url": "https://example.com/a", "title": "A"}]}
    with server(payload=payload) as base_url:
        result = execute(base_url)
        assert _Handler.requests == 1
    assert result.provider_result.status is SearchProviderResultStatus.RESULTS
    assert result.normalized_view is not None
    assert len(result.normalized_view.deduplicated_ranked_view) == 1


def test_no_results_is_successful_and_distinct_from_failures() -> None:
    with server(payload={"results": []}) as base_url:
        result = execute(base_url)
    assert result.provider_result.status is SearchProviderResultStatus.NO_RESULTS
    assert result.normalized_view is not None


@pytest.mark.parametrize(
    ("assessment_status", "code"),
    [
        (None, "authorization_missing"),
        (SearchAuthorizationStatus.DENIED, "authorization_denied"),
        (SearchAuthorizationStatus.APPROVAL_REQUIRED, "authorization_approval_required"),
        (SearchAuthorizationStatus.UNAVAILABLE, "authorization_unavailable"),
    ],
)
def test_non_allowed_assessment_proves_zero_network_attempt(
    assessment_status: SearchAuthorizationStatus | None, code: str
) -> None:
    with server() as base_url:
        value = invocation()
        request, assessment, evidence = authorization(value, base_url)
        if assessment_status is None:
            assessment = None  # type: ignore[assignment]
        else:
            assessment = replace(assessment, status=assessment_status)
        with pytest.raises(SearchExecutionBlocked, match=code):
            executor(base_url, _Governance()).execute(value, request, assessment, evidence, now=NOW)
        assert _Handler.requests == 0


@pytest.mark.parametrize(
    ("state", "code"),
    [
        (AuthorizationEvidenceState.EXPIRED, "authorization_expired"),
        (AuthorizationEvidenceState.STALE, "authorization_stale"),
        (AuthorizationEvidenceState.MISMATCHED, "authorization_mismatched"),
        (AuthorizationEvidenceState.INVALID, "authorization_invalid"),
    ],
)
def test_invalid_evidence_state_proves_zero_network_attempt(
    state: AuthorizationEvidenceState, code: str
) -> None:
    with server() as base_url:
        value = invocation()
        request, assessment, evidence = authorization(value, base_url)
        with pytest.raises(SearchExecutionBlocked, match=code):
            executor(base_url, _Governance(state)).execute(
                value, request, assessment, evidence, now=NOW
            )
        assert _Handler.requests == 0


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("provider_reference", "provider:other"),
        ("destination_reference", "http://127.0.0.1:1"),
        ("requester_reference", "actor:other"),
        ("request_reference", "search-request:other"),
        ("purpose", ProcessingPurpose.EXTERNAL_RETRIEVAL),
        ("provider_invocation_reference", "search-invocation:other"),
    ],
)
def test_wrong_scope_proves_zero_network_attempt(field: str, replacement: object) -> None:
    with server() as base_url:
        value = invocation()
        request, assessment, evidence = authorization(value, base_url)
        evidence = replace(evidence, **{field: replacement})
        assessment = replace(assessment, authorization_evidence=evidence)
        with pytest.raises(SearchExecutionBlocked):
            executor(base_url, _Governance()).execute(
                value, request, assessment, evidence, now=NOW
            )
        assert _Handler.requests == 0


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, SearchProviderResultStatus.MALFORMED_RESPONSE),
        (403, SearchProviderResultStatus.POLICY_BLOCKED),
        (429, SearchProviderResultStatus.PROVIDER_UNAVAILABLE),
        (500, SearchProviderResultStatus.PROVIDER_UNAVAILABLE),
    ],
)
def test_http_status_mapping(status: int, expected: SearchProviderResultStatus) -> None:
    with server(status=status) as base_url:
        result = execute(base_url)
    assert result.provider_result.status is expected
    assert result.normalized_view is None


@pytest.mark.parametrize(
    "raw",
    [b"not-json", b"\xff", b'{"wrong": []}'],
)
def test_malformed_encoding_json_or_shape_is_factual(raw: bytes) -> None:
    with server(raw=raw) as base_url:
        result = execute(base_url)
    assert result.provider_result.status is SearchProviderResultStatus.MALFORMED_RESPONSE


def test_timeout_is_observed_without_retry_or_termination_claim() -> None:
    with server(delay=1.5) as base_url:
        value = invocation(timeout=1)
        request, assessment, evidence = authorization(value, base_url)
        result = executor(base_url, _Governance()).execute(
            value, request, assessment, evidence, now=NOW
        )
        assert _Handler.requests == 1
    assert result.provider_result.status is SearchProviderResultStatus.TIMEOUT
    assert result.provider_result.completion_after_timeout is None


@pytest.mark.parametrize("declared", [True, False])
def test_response_size_bound_uses_header_and_bounded_stream(declared: bool) -> None:
    raw = json.dumps({"results": [], "padding": "x" * 5000}).encode()
    with server(raw=raw, declared_length=len(raw) if declared else -1) as base_url:
        value = invocation()
        request, assessment, evidence = authorization(value, base_url)
        result = executor(base_url, _Governance(), limit=1024).execute(
            value, request, assessment, evidence, now=NOW
        )
    assert result.provider_result.diagnostic is not None
    assert result.provider_result.diagnostic.code.value == "payload_too_large"


def test_redirect_within_origin_is_allowed_but_cross_origin_is_blocked() -> None:
    with server(redirect="/final") as base_url:
        result = execute(base_url)
        assert result.provider_result.status is SearchProviderResultStatus.NO_RESULTS
        assert _Handler.requests == 2
    with server(redirect="http://127.0.0.1:1/search") as base_url:
        result = execute(base_url)
        assert result.provider_result.status is SearchProviderResultStatus.PROVIDER_UNAVAILABLE
        assert _Handler.requests == 1


def test_health_does_not_infer_reachability_authorization_or_upstream_locality() -> None:
    with server() as base_url:
        value = executor(base_url, _Governance()).health
    assert value.transport_implemented and value.configured
    assert value.authorization_integration_available
    assert value.provider_reachable is None
    assert value.search_operational is None
    assert value.upstream_external_processing is None


def test_identical_duplicate_is_idempotent_and_contradiction_is_explicit() -> None:
    with server(payload={"results": []}) as base_url:
        first = execute(base_url).provider_result
        second = execute(base_url).provider_result
    assert (
        classify_provider_result_repetition(first, second)
        is ProviderResultRepetition.IDENTICAL_REPEAT
    )
    with server(payload={"results": [{"url": "https://example.com", "title": "Different"}]}) as base_url:
        contradictory = execute(base_url).provider_result
    assert (
        classify_provider_result_repetition(first, contradictory)
        is ProviderResultRepetition.CONTRADICTORY_REPEAT
    )


def test_execution_result_contains_no_raw_provider_json_or_credentials() -> None:
    payload = {"results": [{"url": "https://example.com", "title": "Safe"}], "raw_secret": "must-not-persist"}
    with server(payload=payload) as base_url:
        result = execute(base_url)
    assert "raw_secret" not in repr(result)
    assert "must-not-persist" not in repr(result)
