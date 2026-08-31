"""Controlled stdlib HTTP retrieval adapter with no extraction or durable storage."""

from __future__ import annotations

import hashlib
import ipaddress
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import Message
from threading import Lock
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from synapse.search import (
    ArtifactChecksum,
    ArtifactContentReference,
    RetrievalAttemptId,
    RetrievalOutcome,
    RetrievalProvenance,
    RetrievalRequestV1,
    RetrievalTransportReference,
    RetrievedArtifactId,
    RetrievedArtifactV1,
    SearchOccurrence,
    SearchValidationError,
    normalize_search_url,
)

HTTP_RETRIEVAL_ADAPTER_VERSION = "http-retrieval-adapter-v1"
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _TimeoutSocket(Protocol):
    def settimeout(self, value: float) -> None: ...


class _SocketRaw(Protocol):
    _sock: _TimeoutSocket


class _SocketFile(Protocol):
    raw: _SocketRaw


class _SocketResponse(Protocol):
    fp: _SocketFile


@dataclass(frozen=True, slots=True)
class HttpRetrievalAdapterConfig:
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 10.0
    maximum_redirects: int = 5
    chunk_size: int = 64 * 1024
    user_agent: str = "Synapse-Search-Retrieval/1"
    allow_private_destinations: bool = False

    def __post_init__(self) -> None:
        if not 0.1 <= self.connect_timeout_seconds <= 60:
            raise SearchValidationError("HTTP connect timeout is invalid")
        if not 0.1 <= self.read_timeout_seconds <= 300:
            raise SearchValidationError("HTTP read timeout is invalid")
        if not 0 <= self.maximum_redirects <= 10:
            raise SearchValidationError("HTTP redirect limit is invalid")
        if not 1024 <= self.chunk_size <= 1024 * 1024:
            raise SearchValidationError("HTTP retrieval chunk size is invalid")
        if not self.user_agent.strip() or "\r" in self.user_agent or "\n" in self.user_agent:
            raise SearchValidationError("HTTP User-Agent is invalid")


@dataclass(frozen=True, slots=True)
class HttpRetrievalHealth:
    adapter_available: bool
    transport_library_available: bool
    network_authority_integrated: bool
    external_reachability_tested: bool


class TransientArtifactContentStore:
    """Process-local bytes with explicit release; not persistence or cache."""

    def __init__(self) -> None:
        self._items: dict[ArtifactContentReference, bytes] = {}
        self._lock = Lock()

    def put(self, reference: ArtifactContentReference, content: bytes) -> None:
        with self._lock:
            if reference in self._items:
                raise SearchValidationError("transient artifact reference already exists")
            self._items[reference] = content

    def read(self, reference: ArtifactContentReference) -> bytes:
        with self._lock:
            try:
                return self._items[reference]
            except KeyError as error:
                raise SearchValidationError("transient artifact content is unavailable") from error

    def release(self, reference: ArtifactContentReference) -> None:
        with self._lock:
            self._items.pop(reference, None)

    def contains(self, reference: ArtifactContentReference) -> bool:
        with self._lock:
            return reference in self._items


class HttpRetrievalAdapter:
    def __init__(
        self,
        config: HttpRetrievalAdapterConfig | None = None,
        content_store: TransientArtifactContentStore | None = None,
    ) -> None:
        self._config = config or HttpRetrievalAdapterConfig()
        self._content_store = content_store or TransientArtifactContentStore()
        self._opener = build_opener(_NoRedirect())

    @property
    def health(self) -> HttpRetrievalHealth:
        return HttpRetrievalHealth(True, True, False, False)

    @property
    def content_store(self) -> TransientArtifactContentStore:
        return self._content_store

    def retrieve(
        self, request: RetrievalRequestV1, attempt_id: RetrievalAttemptId
    ) -> RetrievedArtifactV1:
        self._validate_destination(request.source_url)
        current_url = request.source_url
        redirect_chain: list[str] = []
        for redirect_count in range(self._config.maximum_redirects + 1):
            try:
                transport_request = Request(
                    current_url,
                    headers={
                        "User-Agent": self._config.user_agent,
                        "Accept": ", ".join(request.accepted_content_types),
                    },
                    method="GET",
                )
                response = self._opener.open(
                    transport_request, timeout=self._config.connect_timeout_seconds
                )
            except HTTPError as error:
                if error.code in _REDIRECT_STATUSES:
                    location = error.headers.get("Location")
                    error.close()
                    if location is None:
                        return self._failure(request, attempt_id, RetrievalOutcome.FAILED, current_url)
                    next_url = urljoin(current_url, location)
                    try:
                        self._validate_destination(next_url)
                    except SearchValidationError:
                        return self._failure(
                            request, attempt_id, RetrievalOutcome.POLICY_BLOCKED, current_url
                        )
                    if next_url in redirect_chain or next_url == current_url:
                        return self._failure(request, attempt_id, RetrievalOutcome.FAILED, current_url)
                    if redirect_count >= self._config.maximum_redirects:
                        return self._failure(request, attempt_id, RetrievalOutcome.FAILED, current_url)
                    redirect_chain.append(current_url)
                    current_url = next_url
                    continue
                return self._status_failure(request, attempt_id, error.code, current_url)
            except (TimeoutError, socket.timeout):
                return self._failure(request, attempt_id, RetrievalOutcome.TIMEOUT, current_url)
            except (URLError, OSError):
                return self._failure(request, attempt_id, RetrievalOutcome.UNAVAILABLE, current_url)

            try:
                self._apply_read_timeout(response)
                status = response.status
                if status not in range(200, 300):
                    return self._status_failure(request, attempt_id, status, current_url)
                content_length = self._content_length(response.headers)
                if content_length is not None and content_length > request.maximum_bytes:
                    return self._failure(
                        request, attempt_id, RetrievalOutcome.TOO_LARGE, current_url
                    )
                reported_type, normalized_type = self._content_type(response.headers)
                if normalized_type is not None and normalized_type not in request.accepted_content_types:
                    return self._failure(
                        request,
                        attempt_id,
                        RetrievalOutcome.UNSUPPORTED_CONTENT,
                        current_url,
                        reported_type=reported_type,
                        normalized_type=normalized_type,
                    )
                payload = bytearray()
                while True:
                    chunk = response.read(self._config.chunk_size)
                    if not chunk:
                        break
                    payload.extend(chunk)
                    if len(payload) > request.maximum_bytes:
                        return self._failure(
                            request, attempt_id, RetrievalOutcome.TOO_LARGE, current_url
                        )
            except (TimeoutError, socket.timeout):
                return self._failure(request, attempt_id, RetrievalOutcome.TIMEOUT, current_url)
            except OSError:
                return self._failure(request, attempt_id, RetrievalOutcome.FAILED, current_url)
            finally:
                response.close()

            return self._success(
                request,
                attempt_id,
                current_url,
                bytes(payload),
                reported_type,
                normalized_type,
                tuple(redirect_chain),
            )
        return self._failure(request, attempt_id, RetrievalOutcome.FAILED, current_url)

    def _validate_destination(self, url: str) -> None:
        normalize_search_url(url)
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
            raise SearchValidationError("HTTP retrieval URL is unsupported")
        if parsed.username is not None or parsed.password is not None:
            raise SearchValidationError("HTTP retrieval URL cannot contain credentials")
        try:
            literal = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            literal = None
        if literal is not None and not self._config.allow_private_destinations and not literal.is_global:
            raise SearchValidationError("HTTP retrieval destination requires explicit private authority")
        if parsed.hostname.lower() == "localhost" and not self._config.allow_private_destinations:
            raise SearchValidationError("HTTP retrieval destination requires explicit private authority")

    @staticmethod
    def _content_length(headers: Message) -> int | None:
        raw = headers.get("Content-Length")
        if raw is None:
            return None
        try:
            value = int(raw)
        except ValueError:
            return None
        return value if value >= 0 else None

    def _apply_read_timeout(self, response: object) -> None:
        """urllib exposes one connect timeout; set the established socket read timeout."""

        try:
            socket_object = cast(_SocketResponse, response).fp.raw._sock
            socket_object.settimeout(self._config.read_timeout_seconds)
        except AttributeError:
            return

    @staticmethod
    def _content_type(headers: Message) -> tuple[str | None, str | None]:
        raw = headers.get("Content-Type")
        if raw is None:
            return None, None
        media_type = raw.split(";", 1)[0].strip().lower()
        return raw, media_type or None

    def _success(
        self,
        request: RetrievalRequestV1,
        attempt_id: RetrievalAttemptId,
        final_url: str,
        payload: bytes,
        reported_type: str | None,
        normalized_type: str | None,
        redirect_chain: tuple[str, ...],
    ) -> RetrievedArtifactV1:
        digest = hashlib.sha256(payload).hexdigest()
        token = hashlib.sha256(
            f"{request.retrieval_request_id.value}\x1f{attempt_id.value}".encode()
        ).hexdigest()[:32]
        reference = ArtifactContentReference(f"artifact-body:http-{token}")
        self._content_store.put(reference, payload)
        artifact = self._artifact(
            request,
            attempt_id,
            RetrievalOutcome.RETRIEVED,
            final_url,
            reported_type=reported_type,
            normalized_type=normalized_type,
            content_length=len(payload),
            checksum=ArtifactChecksum(f"sha256:{digest}"),
            content_reference=reference,
            redirect_chain=redirect_chain,
        )
        try:
            artifact.validate_correspondence(request)
        except Exception:
            self._content_store.release(reference)
            raise
        return artifact

    def _status_failure(
        self,
        request: RetrievalRequestV1,
        attempt_id: RetrievalAttemptId,
        status: int,
        final_url: str,
    ) -> RetrievedArtifactV1:
        if status == 404:
            outcome = RetrievalOutcome.NOT_FOUND
        elif status in {401, 403}:
            outcome = RetrievalOutcome.POLICY_BLOCKED
        elif status == 408:
            outcome = RetrievalOutcome.TIMEOUT
        elif status == 429 or status >= 500:
            outcome = RetrievalOutcome.UNAVAILABLE
        else:
            outcome = RetrievalOutcome.FAILED
        return self._failure(request, attempt_id, outcome, final_url)

    def _failure(
        self,
        request: RetrievalRequestV1,
        attempt_id: RetrievalAttemptId,
        outcome: RetrievalOutcome,
        final_url: str,
        *,
        reported_type: str | None = None,
        normalized_type: str | None = None,
    ) -> RetrievedArtifactV1:
        artifact = self._artifact(
            request,
            attempt_id,
            outcome,
            final_url,
            reported_type=reported_type,
            normalized_type=normalized_type,
        )
        artifact.validate_correspondence(request)
        return artifact

    @staticmethod
    def _artifact(
        request: RetrievalRequestV1,
        attempt_id: RetrievalAttemptId,
        outcome: RetrievalOutcome,
        final_url: str,
        *,
        reported_type: str | None = None,
        normalized_type: str | None = None,
        content_length: int | None = None,
        checksum: ArtifactChecksum | None = None,
        content_reference: ArtifactContentReference | None = None,
        redirect_chain: tuple[str, ...] = (),
    ) -> RetrievedArtifactV1:
        token = hashlib.sha256(
            f"{request.retrieval_request_id.value}\x1f{attempt_id.value}".encode()
        ).hexdigest()[:32]
        provenance = RetrievalProvenance(
            search_request_id=request.search_request_id,
            search_result_id=request.source_result_id,
            retrieval_request_id=request.retrieval_request_id,
            retrieval_attempt_id=attempt_id,
            source_url=request.source_url,
            transport_reference=RetrievalTransportReference(
                f"transport:{HTTP_RETRIEVAL_ADAPTER_VERSION}"
            ),
            correlation=request.correlation,
            causation=request.causation,
        )
        return RetrievedArtifactV1(
            artifact_id=RetrievedArtifactId(f"search-artifact:{token}"),
            retrieval_request_id=request.retrieval_request_id,
            retrieval_attempt_id=attempt_id,
            source_result_id=request.source_result_id,
            source_url=request.source_url,
            outcome=outcome,
            retrieval_occurrence=SearchOccurrence(datetime.now(UTC)),
            provenance=provenance,
            observed_final_url=final_url,
            redirect_chain=redirect_chain,
            reported_content_type=reported_type,
            normalized_content_type=normalized_type,
            content_length=content_length,
            checksum=checksum,
            content_reference=content_reference,
        )
