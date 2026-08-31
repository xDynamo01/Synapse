"""Bounded stdlib HTTP transport for an explicitly configured SearXNG origin."""

from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from synapse.search import SearchValidationError

from .config import SearXNGAdapterConfig
from .searxng import (
    SearXNGTransportMalformed,
    SearXNGTransportRequest,
    SearXNGTransportResponse,
    SearXNGTransportResponseTooLarge,
    SearXNGTransportTimeout,
    SearXNGTransportUnavailable,
)

SEARXNG_HTTP_TRANSPORT_VERSION = "searxng-http-transport-v1"
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True, slots=True)
class SearXNGHttpTransportConfig:
    maximum_response_bytes: int = 2 * 1024 * 1024
    maximum_redirects: int = 3
    chunk_size: int = 64 * 1024
    user_agent: str = "Synapse-SearXNG/1"
    allow_private_destination: bool = False

    def __post_init__(self) -> None:
        if not 1024 <= self.maximum_response_bytes <= 32 * 1024 * 1024:
            raise SearchValidationError("SearXNG response limit is invalid")
        if not 0 <= self.maximum_redirects <= 5:
            raise SearchValidationError("SearXNG redirect limit is invalid")
        if not 1024 <= self.chunk_size <= 1024 * 1024:
            raise SearchValidationError("SearXNG transport chunk size is invalid")
        if not self.user_agent.strip() or "\r" in self.user_agent or "\n" in self.user_agent:
            raise SearchValidationError("SearXNG User-Agent is invalid")


@dataclass(frozen=True, slots=True)
class SearXNGTransportHealth:
    transport_implemented: bool
    configured: bool
    authorization_integrated: bool
    reachable: bool | None
    json_api_usable: bool | None
    search_operational: bool | None
    upstream_external_processing: bool | None


class SearXNGHttpTransport:
    """Transport only: authorization must be enforced by its consumer before exchange."""

    def __init__(
        self,
        adapter_config: SearXNGAdapterConfig,
        config: SearXNGHttpTransportConfig | None = None,
    ) -> None:
        self._adapter_config = adapter_config
        self._config = config or SearXNGHttpTransportConfig()
        self._opener = build_opener(_NoRedirect())
        self._validate_origin(adapter_config.base_url)

    @property
    def health(self) -> SearXNGTransportHealth:
        return SearXNGTransportHealth(True, True, False, None, None, None, None)

    def exchange(self, request: SearXNGTransportRequest) -> SearXNGTransportResponse:
        if request.endpoint_path != self._adapter_config.endpoint_path:
            raise SearXNGTransportMalformed("transport endpoint does not match configuration")
        query = urlencode(request.parameters, doseq=True)
        current_url = f"{self._adapter_config.base_url}{request.endpoint_path}?{query}"
        for redirect_count in range(self._config.maximum_redirects + 1):
            transport_request = Request(
                current_url,
                headers={"Accept": "application/json", "User-Agent": self._config.user_agent},
                method="GET",
            )
            try:
                response = self._opener.open(
                    transport_request, timeout=float(request.timeout_seconds)
                )
            except HTTPError as error:
                if error.code not in _REDIRECT_STATUSES:
                    error.close()
                    return SearXNGTransportResponse(error.code, {}, datetime.now(UTC))
                location = error.headers.get("Location")
                error.close()
                if location is None or redirect_count >= self._config.maximum_redirects:
                    raise SearXNGTransportMalformed("SearXNG redirect was invalid")
                next_url = urljoin(current_url, location)
                if not self._same_origin(next_url):
                    raise SearXNGTransportUnavailable("SearXNG redirect escaped authorized origin")
                current_url = next_url
                continue
            except (TimeoutError, socket.timeout) as error:
                raise SearXNGTransportTimeout("SearXNG timeout observed") from error
            except (URLError, OSError) as error:
                raise SearXNGTransportUnavailable("SearXNG transport unavailable") from error

            try:
                length = self._content_length(response.headers)
                if length is not None and length > self._config.maximum_response_bytes:
                    raise SearXNGTransportResponseTooLarge("SearXNG response too large")
                payload = bytearray()
                while True:
                    chunk = response.read(self._config.chunk_size)
                    if not chunk:
                        break
                    payload.extend(chunk)
                    if len(payload) > self._config.maximum_response_bytes:
                        raise SearXNGTransportResponseTooLarge("SearXNG response too large")
                try:
                    decoded = bytes(payload).decode("utf-8")
                    parsed = json.loads(decoded)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise SearXNGTransportMalformed("SearXNG JSON transport was malformed") from error
                return SearXNGTransportResponse(response.status, parsed, datetime.now(UTC))
            except (TimeoutError, socket.timeout) as error:
                raise SearXNGTransportTimeout("SearXNG timeout observed") from error
            except OSError as error:
                raise SearXNGTransportUnavailable("SearXNG transport unavailable") from error
            finally:
                response.close()
        raise SearXNGTransportMalformed("SearXNG redirect limit exceeded")

    def _same_origin(self, url: str) -> bool:
        current = urlsplit(url)
        configured = urlsplit(self._adapter_config.base_url)
        return (
            current.scheme == configured.scheme
            and current.hostname == configured.hostname
            and current.port == configured.port
            and current.username is None
            and current.password is None
        )

    def _validate_origin(self, url: str) -> None:
        parsed = urlsplit(url)
        assert parsed.hostname is not None
        try:
            literal = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            literal = None
        private = parsed.hostname.lower() == "localhost" or (
            literal is not None and not literal.is_global
        )
        if private and not self._config.allow_private_destination:
            raise SearchValidationError("private SearXNG requires explicit transport opt-in")

    @staticmethod
    def _content_length(headers: Message) -> int | None:
        value = headers.get("Content-Length")
        if value is None:
            return None
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if parsed >= 0 else None
