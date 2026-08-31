from __future__ import annotations

import hashlib
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator

import pytest

from synapse.search import (
    CorrelationReference,
    PolicyReference,
    RequesterReference,
    RetrievalAttemptId,
    RetrievalOutcome,
    RetrievalRequestId,
    RetrievalRequestV1,
    SearchOccurrence,
    SearchRequestId,
    SearchResultId,
    SearchValidationError,
)
from synapse.search_adapters import (
    HttpRetrievalAdapter,
    HttpRetrievalAdapterConfig,
    TransientArtifactContentStore,
)

NOW = datetime(2026, 8, 12, 22, 0, tzinfo=UTC)


class LocalHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        routes = {
            "/ok": (200, b"hello artifact", "text/html; charset=utf-8"),
            "/empty": (204, b"", "text/plain"),
            "/json": (200, b'{"ok":true}', "application/json"),
            "/binary": (200, b"\x00\x01\x02", "application/octet-stream"),
            "/missing-type": (200, b"unknown", None),
            "/404": (404, b"not found", "text/plain"),
            "/403": (403, b"forbidden", "text/plain"),
            "/429": (429, b"limited", "text/plain"),
            "/500": (500, b"error", "text/plain"),
        }
        if self.path == "/redirect":
            self._redirect("/ok")
            return
        if self.path == "/redirect-chain":
            self._redirect("/redirect")
            return
        if self.path == "/loop-a":
            self._redirect("/loop-b")
            return
        if self.path == "/loop-b":
            self._redirect("/loop-a")
            return
        if self.path == "/unsafe":
            self._redirect("file:///private/file")
            return
        if self.path.startswith("/chain/"):
            index = int(self.path.rsplit("/", 1)[1])
            self._redirect(f"/chain/{index + 1}")
            return
        if self.path == "/declared-large":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", "100000")
            self.end_headers()
            return
        if self.path == "/stream-large":
            body = b"x" * 8192
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/slow":
            body = b"late"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.flush()
            time.sleep(0.2)
            try:
                self.wfile.write(body)
            except OSError:
                pass
            return
        status, body, content_type = routes.get(
            self.path, (404, b"not found", "text/plain")
        )
        self.send_response(status)
        if content_type is not None:
            self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def local_server() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), LocalHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def retrieval(url: str, **updates: object) -> RetrievalRequestV1:
    values: dict[str, object] = {
        "retrieval_request_id": RetrievalRequestId("search-retrieval-request:http-1"),
        "source_result_id": SearchResultId("search-result:http-1"),
        "search_request_id": SearchRequestId("search-request:http-1"),
        "source_url": url,
        "requester": RequesterReference("principal:owner"),
        "accepted_content_types": (
            "text/html",
            "text/plain",
            "application/json",
            "application/octet-stream",
        ),
        "maximum_bytes": 4096,
        "policy_reference": PolicyReference("policy:controlled-local-egress"),
        "correlation": CorrelationReference("correlation:http-1"),
        "causation": (),
        "occurrence": SearchOccurrence(datetime.now(UTC)),
    }
    values.update(updates)
    return RetrievalRequestV1(**values)  # type: ignore[arg-type]


def adapter(**updates: object) -> HttpRetrievalAdapter:
    values: dict[str, object] = {
        "allow_private_destinations": True,
        "connect_timeout_seconds": 1.0,
        "read_timeout_seconds": 1.0,
        "maximum_redirects": 3,
        "chunk_size": 1024,
    }
    values.update(updates)
    return HttpRetrievalAdapter(HttpRetrievalAdapterConfig(**values))  # type: ignore[arg-type]


def attempt(value: int = 1) -> RetrievalAttemptId:
    return RetrievalAttemptId(f"search-retrieval-attempt:http-{value}")


def test_200_streams_payload_calculates_checksum_and_exact_correspondence() -> None:
    with local_server() as base:
        request = retrieval(f"{base}/ok")
        runtime = adapter()
        artifact = runtime.retrieve(request, attempt())
    assert artifact.outcome is RetrievalOutcome.RETRIEVED
    assert artifact.reported_content_type == "text/html; charset=utf-8"
    assert artifact.normalized_content_type == "text/html"
    assert artifact.content_length == len(b"hello artifact")
    assert artifact.checksum is not None
    assert artifact.checksum.value == "sha256:" + hashlib.sha256(b"hello artifact").hexdigest()
    assert artifact.content_reference is not None
    assert runtime.content_store.read(artifact.content_reference) == b"hello artifact"
    artifact.validate_correspondence(request)


def test_204_empty_body_is_a_valid_retrieved_artifact() -> None:
    with local_server() as base:
        artifact = adapter().retrieve(retrieval(f"{base}/empty"), attempt())
    assert artifact.outcome is RetrievalOutcome.RETRIEVED
    assert artifact.content_length == 0
    assert artifact.checksum == __import__("synapse.search", fromlist=["ArtifactChecksum"]).ArtifactChecksum(
        "sha256:" + hashlib.sha256(b"").hexdigest()
    )


@pytest.mark.parametrize(
    ("path", "outcome"),
    [
        ("/404", RetrievalOutcome.NOT_FOUND),
        ("/403", RetrievalOutcome.POLICY_BLOCKED),
        ("/429", RetrievalOutcome.UNAVAILABLE),
        ("/500", RetrievalOutcome.UNAVAILABLE),
    ],
)
def test_status_codes_map_factually(path: str, outcome: RetrievalOutcome) -> None:
    with local_server() as base:
        artifact = adapter().retrieve(retrieval(f"{base}{path}"), attempt())
    assert artifact.outcome is outcome
    assert artifact.content_reference is None


def test_simple_and_chained_redirects_preserve_original_chain_and_final_url() -> None:
    with local_server() as base:
        simple = adapter().retrieve(retrieval(f"{base}/redirect"), attempt())
        chained = adapter().retrieve(retrieval(f"{base}/redirect-chain"), attempt(2))
    assert simple.source_url.endswith("/redirect")
    assert simple.observed_final_url is not None and simple.observed_final_url.endswith("/ok")
    assert simple.redirect_chain == (simple.source_url,)
    assert len(chained.redirect_chain) == 2
    assert chained.observed_final_url is not None and chained.observed_final_url.endswith("/ok")
    assert not hasattr(chained, "publisher_canonical_url")


def test_redirect_loop_excess_and_unsafe_scheme_fail_closed() -> None:
    with local_server() as base:
        loop = adapter().retrieve(retrieval(f"{base}/loop-a"), attempt())
        excess = adapter(maximum_redirects=1).retrieve(
            retrieval(f"{base}/chain/1"), attempt(2)
        )
        unsafe = adapter().retrieve(retrieval(f"{base}/unsafe"), attempt(3))
    assert loop.outcome is RetrievalOutcome.FAILED
    assert excess.outcome is RetrievalOutcome.FAILED
    assert unsafe.outcome is RetrievalOutcome.POLICY_BLOCKED


def test_content_length_and_streaming_limits_do_not_retain_oversize_content() -> None:
    store = TransientArtifactContentStore()
    runtime = HttpRetrievalAdapter(
        HttpRetrievalAdapterConfig(allow_private_destinations=True, chunk_size=1024), store
    )
    with local_server() as base:
        declared = runtime.retrieve(retrieval(f"{base}/declared-large"), attempt())
        streamed = runtime.retrieve(retrieval(f"{base}/stream-large"), attempt(2))
    assert declared.outcome is RetrievalOutcome.TOO_LARGE
    assert streamed.outcome is RetrievalOutcome.TOO_LARGE
    assert declared.content_reference is streamed.content_reference is None


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/ok", "text/html"),
        ("/json", "application/json"),
        ("/binary", "application/octet-stream"),
        ("/missing-type", None),
    ],
)
def test_content_types_are_reported_or_unknown_without_inference(
    path: str, content_type: str | None
) -> None:
    with local_server() as base:
        artifact = adapter().retrieve(retrieval(f"{base}{path}"), attempt())
    assert artifact.outcome is RetrievalOutcome.RETRIEVED
    assert artifact.normalized_content_type == content_type


def test_unsupported_mime_is_rejected_without_retaining_body() -> None:
    with local_server() as base:
        artifact = adapter().retrieve(
            retrieval(f"{base}/binary", accepted_content_types=("text/plain",)), attempt()
        )
    assert artifact.outcome is RetrievalOutcome.UNSUPPORTED_CONTENT
    assert artifact.content_reference is None


def test_read_timeout_is_factual_and_not_termination_proof() -> None:
    with local_server() as base:
        artifact = adapter(read_timeout_seconds=0.1).retrieve(
            retrieval(f"{base}/slow"), attempt()
        )
    assert artifact.outcome is RetrievalOutcome.TIMEOUT
    assert not hasattr(artifact, "remote_execution_terminated")


@pytest.mark.parametrize(
    "url",
    [
        "file:///private/file",
        "ftp://example.com/file",
        "data:text/plain,secret",
        "javascript://example.com/code",
        "http://user:password@example.com/private",
    ],
)
def test_unsupported_or_credentialed_url_fails_before_network(url: str) -> None:
    with pytest.raises(SearchValidationError):
        request = retrieval(url)
        adapter().retrieve(request, attempt())


def test_private_destinations_require_explicit_controlled_authority() -> None:
    with local_server() as base:
        request = retrieval(f"{base}/ok")
        with pytest.raises(SearchValidationError, match="private authority"):
            HttpRetrievalAdapter().retrieve(request, attempt())


def test_attempts_remain_distinct_even_when_checksum_matches() -> None:
    with local_server() as base:
        request = retrieval(f"{base}/ok")
        first = adapter().retrieve(request, attempt(1))
        second = adapter().retrieve(request, attempt(2))
    assert first.artifact_id != second.artifact_id
    assert first.retrieval_attempt_id != second.retrieval_attempt_id
    assert first.checksum == second.checksum


def test_transient_content_cleanup_is_explicit_and_no_extraction_occurs() -> None:
    with local_server() as base:
        runtime = adapter()
        artifact = runtime.retrieve(retrieval(f"{base}/ok"), attempt())
    assert artifact.content_reference is not None
    assert runtime.content_store.contains(artifact.content_reference)
    runtime.content_store.release(artifact.content_reference)
    assert not runtime.content_store.contains(artifact.content_reference)
    assert not hasattr(artifact, "extracted_content")
    assert not hasattr(runtime, "extract")


def test_health_does_not_project_localhost_success_into_internet_availability() -> None:
    health = adapter().health
    assert health.adapter_available and health.transport_library_available
    assert not health.network_authority_integrated
    assert not health.external_reachability_tested
