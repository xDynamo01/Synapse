"""Pinned HTTPS transport for the authenticated browser worker.

The Chromium process never dials the requested site directly. A brokered
operation receives an exact origin and, for a form submission, an exact URL.
"""
from dataclasses import dataclass
from http.client import HTTPResponse
import socket
import ssl
import time

from .browser_read import resolve, target, USER_AGENT


MAX_DOCUMENT_BYTES = 256 * 1024
MAX_FORM_BYTES = 16 * 1024


@dataclass(frozen=True)
class Response:
    status: int
    headers: tuple
    body: bytes


def exchange(origin, address, *, method="GET", form_action=None, body=b"", cookie=""):
    origin_url = target(origin)
    destination = target(address)
    if (origin_url.path not in ("", "/") or origin_url.query or origin_url.fragment
            or origin_url.hostname != destination.hostname):
        raise ValueError("Browser request is outside the approved HTTPS origin")
    if method == "POST":
        if form_action is None or target(form_action).geturl() != destination.geturl():
            raise ValueError("Browser form submission requires the exact approved destination")
        if not body or len(body) > MAX_FORM_BYTES:
            raise ValueError("Browser form exceeds its size limit")
    elif method != "GET" or body:
        raise ValueError("Browser method is outside the approved operation")
    if len(cookie) > 8192 or not cookie.isascii() or any(ord(char) < 32 or ord(char) >= 127 for char in cookie):
        raise ValueError("Invalid browser cookie header")

    path = destination.path or "/"
    if destination.query:
        path += "?" + destination.query
    headers = [
        f"{method} {path} HTTP/1.1",
        f"Host: {destination.hostname}",
        "Accept: text/html, text/plain",
        f"User-Agent: {USER_AGENT}",
        "Connection: close",
    ]
    if cookie:
        headers.append(f"Cookie: {cookie}")
    if method == "POST":
        headers.extend(("Content-Type: application/x-www-form-urlencoded",
                        f"Content-Length: {len(body)}"))

    deadline = time.monotonic() + 12
    family, kind, protocol, _, peer = resolve(destination.hostname)[0]
    with socket.socket(family, kind, protocol) as connection:
        connection.settimeout(max(.001, deadline - time.monotonic()))
        connection.connect(peer)
        if connection.getpeername()[0] != peer[0]:
            raise ValueError("Browser connection peer differs from verified DNS")
        context = ssl.create_default_context()
        with context.wrap_socket(connection, server_hostname=destination.hostname) as tls:
            tls.sendall(("\r\n".join(headers) + "\r\n\r\n").encode("ascii") + body)
            with HTTPResponse(tls) as response:
                response.begin()
                if response.status in (301, 302, 303, 307, 308):
                    if method == "POST" and response.status in (307, 308):
                        raise ValueError("Browser redirects cannot replay a form submission")
                    return Response(response.status, tuple(response.getheaders()), b"")
                if response.getheader("Content-Disposition"):
                    raise ValueError("The authenticated browser does not open attachments")
                if response.getheader("Content-Encoding", "identity").lower() != "identity":
                    raise ValueError("Unsupported browser response encoding")
                if response.headers.get_content_type() not in ("text/html", "text/plain"):
                    raise ValueError("Unsupported authenticated document type")
                document = bytearray()
                while len(document) <= MAX_DOCUMENT_BYTES:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Authenticated browser response timed out")
                    tls.settimeout(remaining)
                    chunk = response.read1(min(16384, MAX_DOCUMENT_BYTES + 1 - len(document)))
                    if not chunk:
                        break
                    document.extend(chunk)
                if len(document) > MAX_DOCUMENT_BYTES:
                    raise ValueError("Authenticated browser document exceeds the size limit")
                return Response(response.status, tuple(response.getheaders()), bytes(document))
