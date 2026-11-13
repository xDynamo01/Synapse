"""Owner-invoked HTTPS text reader. No cookies, scripts or subresources."""
import argparse
import base64
from html.parser import HTMLParser
from http.client import HTTPResponse
import ipaddress
import json
import socket
import ssl
import time
from urllib.parse import urljoin, urlsplit


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = None
        self.images = []

    def handle_starttag(self, tag, attrs):
        if tag == "img" and self.hidden is None and len(self.images) < 32:
            src = dict(attrs).get("src")
            if src and len(src) <= 4096 and not any(c.isspace() or ord(c) < 32 or c == "\\" for c in src):
                self.images.append(src)
        if self.hidden is None and tag in {"script", "style", "template", "noscript"}:
            self.hidden = tag

    def handle_endtag(self, tag):
        if tag == self.hidden:
            self.hidden = None

    def handle_data(self, data):
        if self.hidden is None and data.strip():
            self.parts.append(data.strip())


def target(value):
    if len(value) > 4096 or not value.isascii() or any(ord(c) <= 32 or ord(c) == 127 or c == "\\" for c in value):
        raise ValueError("Invalid URL")
    url = urlsplit(value)
    host = url.hostname
    if (not value.lower().startswith("https://") or not host or url.username is not None
            or url.password is not None or url.port not in (None, 443)
            or url.netloc.lower() not in (host, host + ":443")):
        raise ValueError("Expected HTTPS hostname on port 443")
    labels = host.split(".")
    if (len(labels) < 2 or not labels[-1].isalpha() or labels[-1] in
            {"local", "localhost", "internal", "test", "invalid", "onion", "example", "arpa"}
            or any(not label or len(label) > 63 or not label[0].isalnum() or not label[-1].isalnum()
                   or not all(c.isalnum() or c == "-" for c in label) for label in labels)):
        raise ValueError("Expected a public DNS hostname")
    return url


def public(address):
    ip = ipaddress.ip_address(address)
    if not ip.is_global or ip.is_multicast or ip.is_reserved:
        return False
    return ip.version == 4 or (ip in ipaddress.ip_network("2000::/3") and ip.sixtofour is None
                              and ip not in ipaddress.ip_network("3fff::/20"))


def resolve(host):
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    if not addresses or any(not public(entry[4][0]) for entry in addresses):
        raise ValueError("DNS returned a nonpublic address")
    return addresses


def fetch(origin, destination, image=False):
    approved = target(origin)
    if approved.path not in ("", "/") or approved.query or approved.fragment:
        raise ValueError("Approval must identify an origin")
    context = ssl.create_default_context()
    expires = time.monotonic() + 15
    for _ in range(4):
        url = target(destination)
        if url.hostname != approved.hostname:
            raise ValueError("Destination is outside the approved origin")
        family, kind, proto, _, address = resolve(url.hostname)[0]
        with socket.socket(family, kind, proto) as connection:
            connection.settimeout(max(0.001, expires - time.monotonic()))
            connection.connect(address)
            if connection.getpeername()[0] != address[0]:
                raise ValueError("Peer differs from validated DNS address")
            with context.wrap_socket(connection, server_hostname=url.hostname) as tls:
                path = url.path or "/"
                if url.query:
                    path += "?" + url.query
                accept = "image/png, image/jpeg" if image else "text/html, text/plain"
                tls.sendall(f"GET {path} HTTP/1.1\r\nHost: {url.hostname}\r\nAccept: {accept}\r\nConnection: close\r\n\r\n".encode("ascii"))
                with HTTPResponse(tls) as response:
                    response.begin()
                    if response.status in (301, 302, 303, 307, 308):
                        location = response.getheader("Location")
                        if not location or "\\" in location or any(ord(c) <= 32 or ord(c) == 127 for c in location):
                            raise ValueError("Invalid redirect")
                        if len(location) > 4096 or (":" in location.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
                                                    and not location.lower().startswith("https://")):
                            raise ValueError("Invalid redirect")
                        destination = urljoin(destination, location)
                        continue
                    if response.status != 200 or response.getheader("Content-Encoding", "identity").lower() != "identity":
                        raise ValueError("Unsupported HTTP response")
                    media = response.headers.get_content_type()
                    allowed = ("image/png", "image/jpeg") if image else ("text/html", "text/plain")
                    if media not in allowed or response.getheader("Content-Disposition"):
                        raise ValueError("Only inline HTML and plain text are supported")
                    limit = 2 * 1024 * 1024 if image else 262144
                    body = bytearray()
                    while len(body) <= limit:
                        remaining = expires - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError("Read deadline exceeded")
                        tls.settimeout(remaining)
                        part = response.read1(min(16384, limit + 1 - len(body)))
                        if not part:
                            break
                        body.extend(part)
                    if len(body) > limit:
                        raise ValueError("Response exceeds size limit")
                    if image:
                        return {"image": base64.b64encode(body).decode("ascii")}
                    images = []
                    text = body.decode("utf-8", errors="replace")
                    if media == "text/html":
                        parser = PageText()
                        parser.feed(text)
                        parser.close()
                        text = "\n".join(parser.parts)
                        for src in parser.images:
                            try:
                                candidate = target(urljoin(destination, src))
                            except ValueError:
                                continue
                            if candidate.hostname == approved.hostname:
                                images.append(candidate.geturl())
                    return {"origin": origin, "text": text[:64000], "images": list(dict.fromkeys(images)), "markup": body.decode("utf-8", errors="replace") if media == "text/html" else None}
    raise ValueError("Redirect limit exceeded")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin")
    parser.add_argument("--image", action="store_true")
    parser.add_argument("url")
    args = parser.parse_args()
    try:
        url = target(args.url)
        print(json.dumps(fetch(args.origin or f"https://{url.hostname}", args.url, image=args.image)))
    except (ValueError, OSError) as error:
        parser.exit(1, f"Reading failed: {error}\n")


if __name__ == "__main__":
    main()
