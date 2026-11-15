"""Owner-invoked HTTPS reader."""
import argparse
import base64
from html.parser import HTMLParser
from http.client import HTTPException, HTTPResponse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import tempfile
import socket
import ssl
import subprocess
import time
from urllib.parse import urljoin, urlsplit


USER_AGENT = "Synapse/0.3 (https://github.com/xDynamo01/Synapse)"


class NavigationDenied(ValueError):
    """A diagnostic safe to show without exposing form or redirect data."""


def redirect_destination(current, location, approved):
    candidate = target(urljoin(current, location))
    if candidate.hostname != approved.hostname:
        raise NavigationDenied(f"Redirecionamento para outra origem bloqueado ({candidate.hostname}).")
    return candidate.geturl()


def protect_session(data, decrypt=False):
    import ctypes as c
    from ctypes import wintypes as w

    class Blob(c.Structure):
        _fields_ = [("size", w.DWORD), ("data", c.POINTER(c.c_ubyte))]

    buffer = (c.c_ubyte * len(data)).from_buffer_copy(data)
    source, output = Blob(len(data), buffer), Blob()
    api = c.WinDLL("crypt32", use_last_error=True)
    operation = api.CryptUnprotectData if decrypt else api.CryptProtectData
    operation.argtypes = [c.POINTER(Blob), c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p, w.DWORD, c.POINTER(Blob)]
    operation.restype = w.BOOL
    if not operation(c.byref(source), None, None, None, None, 1, c.byref(output)):
        raise c.WinError(c.get_last_error())
    kernel = c.WinDLL("kernel32")
    kernel.LocalFree.argtypes = [c.c_void_p]
    kernel.LocalFree.restype = c.c_void_p
    try:
        return c.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


def quarantine_directory():
    return Path(os.environ["LOCALAPPDATA"]) / "Synapse" / "browser" / "quarantine"


def quarantine_text(body):
    # The preview download path only accepts inert UTF-8 text. The raw body
    # remains encrypted and has no executable filename or automatic opener.
    text = body.decode("utf-8", errors="strict")
    if not text or any(not char.isprintable() and char not in "\r\n\t" for char in text):
        raise ValueError("Download não passou na validação de texto UTF-8")
    digest = hashlib.sha256(body).hexdigest()
    directory = quarantine_directory()
    directory.mkdir(parents=True, exist_ok=True)
    encrypted = protect_session(body)
    with tempfile.NamedTemporaryFile(dir=directory, delete=False) as file:
        temporary = Path(file.name)
        try:
            file.write(encrypted)
            file.close()
            os.replace(temporary, directory / (digest + ".dpapi"))
        finally:
            temporary.unlink(missing_ok=True)
    return {"sha256": digest, "bytes": len(body), "media_type": "text/plain"}


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = None
        self.images = []
        self.stylesheets = []

    def handle_starttag(self, tag, attrs):
        if tag == "link" and self.hidden is None and len(self.stylesheets) < 32:
            attrs_by_name = dict(attrs)
            href = attrs_by_name.get("href")
            if href and "stylesheet" in (attrs_by_name.get("rel") or "").lower().split():
                self.stylesheets.append(href)
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


def launch_offline_browser(runtime):
    # Contents are fetched by the HTTPS broker. The renderer has no reason to
    # resolve Internet hosts, even when separate from a Playwright page.
    args = ["--host-resolver-rules=MAP * ~NOTFOUND"]
    if os.name == "nt":
        args.append("--enable-features=RendererAppContainer")
    return runtime.chromium.launch(headless=True, chromium_sandbox=True, args=args)


def verify_windows_renderers(browser):
    if os.name != "nt":
        return

    import ctypes
    from ctypes import wintypes as win

    devtools = browser.new_browser_cdp_session()
    try:
        processes = devtools.send("SystemInfo.getProcessInfo")["processInfo"]
    finally:
        devtools.detach()
    renderers = [process["id"] for process in processes if process["type"] == "renderer"]
    if not renderers:
        raise ValueError("Chromium did not provide a renderer for isolation verification")

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    security = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.OpenProcess.argtypes = [win.DWORD, win.BOOL, win.DWORD]
    kernel.OpenProcess.restype = win.HANDLE
    kernel.CloseHandle.argtypes = [win.HANDLE]
    security.OpenProcessToken.argtypes = [win.HANDLE, win.DWORD, ctypes.POINTER(win.HANDLE)]
    security.GetTokenInformation.argtypes = [
        win.HANDLE, win.INT, win.LPVOID, win.DWORD, ctypes.POINTER(win.DWORD),
    ]

    def first_token_field(token, category):
        needed = win.DWORD()
        security.GetTokenInformation(token, category, None, 0, ctypes.byref(needed))
        if not 4 <= needed.value <= 65536:
            raise ValueError("Invalid Chromium token information")
        data = ctypes.create_string_buffer(needed.value)
        if not security.GetTokenInformation(token, category, data, needed, ctypes.byref(needed)):
            raise ValueError("Chromium renderer isolation could not be verified")
        return int.from_bytes(data.raw[:4], "little")

    token_is_app_container, token_capabilities = 29, 30
    process_query_limited_information, token_query = 0x1000, 0x0008
    for pid in renderers:
        process = kernel.OpenProcess(process_query_limited_information, False, pid)
        token = win.HANDLE()
        try:
            if not process or not security.OpenProcessToken(process, token_query, ctypes.byref(token)):
                raise ValueError("Chromium renderer token could not be opened")
            if (first_token_field(token, token_is_app_container) != 1
                    or first_token_field(token, token_capabilities) != 0):
                raise ValueError("Chromium renderer must use an AppContainer without network capabilities")
        finally:
            if token:
                kernel.CloseHandle(token)
            if process:
                kernel.CloseHandle(process)


def open_offline_page(browser):
    context = browser.new_context(
        offline=True, java_script_enabled=False, service_workers="block",
        accept_downloads=False,
    )
    context.route("**/*", lambda route: route.abort())
    context.route_web_socket("**/*", lambda route: route.close())
    page = context.new_page()
    verify_windows_renderers(browser)
    return context, page


def set_inert_document(page, markup):
    executable = os.environ.get("SYNAPSE_BROWSER_PROJECTOR_EXECUTABLE", "")
    if not Path(executable).is_absolute():
        raise ValueError("Isolated HTML projector is unavailable")
    try:
        projected = subprocess.run(
            [executable, "--project-broker"], input=markup.encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=35,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=True,
        ).stdout
        markup = json.loads(projected)
    except (OSError, subprocess.SubprocessError, ValueError):
        raise ValueError("Isolated HTML projection failed") from None
    if not isinstance(markup, str):
        raise ValueError("Invalid HTML projection")
    page.set_content(
        '<meta http-equiv="Content-Security-Policy" '
        """content="default-src 'none'; base-uri 'none'; form-action 'none'">""",
        wait_until="domcontentloaded", timeout=5000,
    )
    page.evaluate("""markup => {
        const documentSource = new DOMParser().parseFromString(markup, "text/html");
        documentSource.querySelectorAll("meta, base, script, iframe, frame, object, embed, portal")
            .forEach(element => element.remove());
        const fragment = document.createDocumentFragment();
        while (documentSource.body.firstChild) fragment.append(documentSource.body.firstChild);
        document.body.replaceChildren(fragment);
    }""", markup)


def render_mission_document(markup):
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        raise ValueError("Playwright is unavailable in the browser worker") from None
    try:
        with sync_playwright() as runtime:
            with launch_offline_browser(runtime) as browser:
                _, page = open_offline_page(browser)
                set_inert_document(page, markup)
                text = page.locator("body").inner_text(timeout=3000)
                links = page.locator("a[href]").evaluate_all(
                    "(links) => links.slice(0, 64).map(link => link.getAttribute('href'))"
                )
                return text[:64000], links
    except Error:
        raise ValueError("Isolated Chromium rendering failed") from None


def fetch(origin, destination, image=False, css=False, download=False, skill=False, mission=False):
    approved = target(origin)
    if approved.path not in ("", "/") or approved.query or approved.fragment:
        raise ValueError("Approval must identify an origin")
    context = ssl.create_default_context()
    expires = time.monotonic() + 15
    for _ in range(6):
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
                accept = "image/png, image/jpeg" if image else "text/css" if css else "text/html, text/plain"
                if skill:
                    accept = "application/json, text/plain"
                headers = f"GET {path} HTTP/1.1\r\nHost: {url.hostname}\r\nAccept: {accept}\r\nUser-Agent: {USER_AGENT}\r\nConnection: close\r\n\r\n"
                tls.sendall(headers.encode("ascii"))
                with HTTPResponse(tls) as response:
                    response.begin()
                    if response.status in (301, 302, 303, 307, 308):
                        location = response.getheader("Location")
                        if not location or "\\" in location or any(ord(c) <= 32 or ord(c) == 127 for c in location):
                            raise ValueError("Invalid redirect")
                        if len(location) > 4096 or (":" in location.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
                                                    and not location.lower().startswith("https://")):
                            raise ValueError("Invalid redirect")
                        if mission:
                            candidate = target(urljoin(destination, location))
                            return {"redirect": candidate.geturl()}
                        destination = redirect_destination(destination, location, approved)
                        continue
                    if response.status != 200:
                        raise NavigationDenied(f"O servidor respondeu HTTP {response.status}.")
                    if response.getheader("Content-Encoding", "identity").lower() != "identity":
                        raise ValueError("Unsupported HTTP encoding")
                    media = response.headers.get_content_type()
                    allowed = ("image/png", "image/jpeg") if image else ("text/css",) if css else ("text/html", "text/plain")
                    if skill:
                        allowed = ("application/json", "text/plain")
                    if download:
                        allowed = ("text/plain",)
                    if media not in allowed or (not download and response.getheader("Content-Disposition")):
                        if skill:
                            raise ValueError("Skill packages require inline JSON or UTF-8 text")
                        raise ValueError("Only inline HTML and plain text are supported")
                    limit = 2 * 1024 * 1024 if image else 262144
                    if skill:
                        limit = 49152
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
                    if skill:
                        return {"source": destination, "document": body.decode("utf-8")}
                    if download:
                        return {"quarantine": quarantine_text(bytes(body))}
                    if image:
                        return {"image": base64.b64encode(body).decode("ascii")}
                    if css:
                        return {"css": body.decode("utf-8", errors="replace")}
                    images = []
                    stylesheets = []
                    text = body.decode("utf-8", errors="replace")
                    if mission and os.environ.get("SYNAPSE_BROWSER_ENGINE") == "playwright" and media == "text/html":
                        rendered, links = render_mission_document(text)
                        destinations = []
                        for link in links:
                            try:
                                destinations.append(target(urljoin(destination, link)).geturl())
                            except ValueError:
                                continue
                        return {"origin": origin, "source": destination, "text": rendered,
                                "links": list(dict.fromkeys(destinations)), "renderer": "playwright"}
                    if media == "text/html":
                        parser = PageText()
                        parser.feed(text)
                        parser.close()
                        text = "\n".join(parser.parts)
                        for src, items in [(src, images) for src in parser.images] + [(src, stylesheets) for src in parser.stylesheets]:
                            try:
                                candidate = target(urljoin(destination, src))
                            except ValueError:
                                continue
                            if candidate.hostname == approved.hostname:
                                items.append(candidate.geturl())
                    return {"origin": origin, "text": text[:64000], "images": list(dict.fromkeys(images)), "stylesheets": list(dict.fromkeys(stylesheets)), "markup": body.decode("utf-8", errors="replace") if media == "text/html" else None}
    raise ValueError("Redirect limit exceeded")


def skill_catalog(result):
    entries = json.loads(result["document"])
    if not isinstance(entries, list) or len(entries) > 50:
        raise ValueError("Expected a catalog of at most 50 entries")
    source = result["source"]
    origin = target(source).hostname
    packages = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"name", "url"}:
            raise ValueError("Invalid Skill catalog entry")
        name, address = entry["name"], entry["url"]
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise ValueError("Invalid Skill catalog name")
        if not isinstance(address, str) or not address or len(address) > 4096:
            raise ValueError("Invalid Skill package URL")
        destination = target(urljoin(source, address))
        if destination.hostname != origin:
            raise ValueError("Skill package is outside the catalog origin")
        packages.append({"name": name, "url": destination.geturl()})
    return {"source": source, "packages": packages}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--mission-read", action="store_true")
    modes.add_argument("--image", action="store_true")
    modes.add_argument("--css", action="store_true")
    modes.add_argument("--quarantine-text", action="store_true")
    modes.add_argument("--mission-download", action="store_true")
    modes.add_argument("--skill-package", action="store_true")
    modes.add_argument("--skill-catalog", action="store_true")
    parser.add_argument("url")
    args = parser.parse_args()
    try:
        url = target(args.url)
        result = fetch(args.origin or f"https://{url.hostname}", args.url, image=args.image,
                       css=args.css, download=args.quarantine_text or args.mission_download,
                       skill=args.skill_package or args.skill_catalog,
                       mission=args.mission_read or args.mission_download)
        print(json.dumps(skill_catalog(result) if args.skill_catalog else result))
    except NavigationDenied as error:
        parser.exit(1, f"{error}\n")
    except (ValueError, OSError, HTTPException) as error:
        parser.exit(1, f"Reading failed: {error}\n")


if __name__ == "__main__":
    main()
