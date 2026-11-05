"""Loopback-only HTTP transport for the optional user-installed VoiceStudio API."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

from synapse.core.exceptions import ValidationError


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValidationError("VoiceStudio redirects are not permitted.")


class VoiceStudioHttpTransport:
    def __init__(self, base_url: str) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValidationError("VoiceStudio requires a local loopback HTTP endpoint.")
        self._base_url = base_url.rstrip("/")
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirects())

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        request = urllib.request.Request(
            f"{self._base_url}{path}",
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers={"Authorization": "Bearer local", "Content-Type": "application/json"},
            method=method,
        )
        try:
            with self._opener.open(request, timeout=0.25) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ValidationError(f"VoiceStudio API returned HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ValidationError("VoiceStudio local API is unavailable.") from exc

    def request_bytes(self, method: str, path: str, payload: dict[str, Any]) -> bytes:
        request = urllib.request.Request(
            f"{self._base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": "Bearer local", "Content-Type": "application/json"},
            method=method,
        )
        try:
            with self._opener.open(request, timeout=120) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise ValidationError(f"VoiceStudio synthesis failed with HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ValidationError("VoiceStudio local API is unavailable.") from exc

    def request_multipart(
        self, method: str, path: str, fields: dict[str, str], file_field: str, filename: str, content: bytes
    ) -> dict[str, Any]:
        boundary = f"----SynapseVoice{int(time.time() * 1000)}"
        parts: list[bytes] = []
        for key, value in fields.items():
            parts += [f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode()]
        parts += [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode(),
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        request = urllib.request.Request(
            f"{self._base_url}{path}", data=b"".join(parts),
            headers={"Authorization": "Bearer local", "Content-Type": f"multipart/form-data; boundary={boundary}"},
            method=method,
        )
        try:
            with self._opener.open(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise ValidationError(f"VoiceStudio profile creation failed with HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ValidationError("VoiceStudio local API is unavailable.") from exc

