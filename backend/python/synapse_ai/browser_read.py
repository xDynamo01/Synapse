"""Owner-invoked HTTPS reader and transient form submission."""
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
import sys
import time
from urllib.parse import urlencode, urljoin, urlsplit
from http.cookiejar import CookieJar
from urllib.request import Request


USER_AGENT = "Synapse/0.3 (https://github.com/xDynamo01/Synapse)"


class NavigationDenied(ValueError):
    """A diagnostic safe to show without exposing form or redirect data."""


def redirect_destination(current, location, approved):
    candidate = target(urljoin(current, location))
    if candidate.hostname != approved.hostname:
        raise NavigationDenied(f"Redirecionamento para outra origem bloqueado ({candidate.hostname}).")
    return candidate.geturl()


WIKI_HOST = "test.wikipedia.org"
AUTH_HOST = "auth.wikimedia.org"
AUTH_PATH = "/testwiki/wiki/Special:UserLogin"
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


def session_file():
    return Path(os.environ["LOCALAPPDATA"]) / "Synapse" / "browser" / "testwiki-session.dpapi"


def save_session(username, cookies):
    destination = session_file()
    destination.parent.mkdir(parents=True, exist_ok=True)
    records = [vars(cookie) for cookie in cookies if not cookie.is_expired()]
    payload = json.dumps({"username": username, "cookies": records}).encode()
    if len(payload) > 65536:
        raise ValueError("Session exceeds limit")
    encrypted = protect_session(payload)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            file.write(encrypted)
            file.close()
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)


def quarantine_text(body):
    # The preview download path only accepts inert UTF-8 text. The raw body
    # remains encrypted and has no executable filename or automatic opener.
    text = body.decode("utf-8", errors="strict")
    if not text or any(not char.isprintable() and char not in "\r\n\t" for char in text):
        raise ValueError("Download não passou na validação de texto UTF-8")
    digest = hashlib.sha256(body).hexdigest()
    directory = session_file().parent / "quarantine"
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


def load_session():
    from http.cookiejar import Cookie
    with session_file().open("rb") as file:
        encrypted = file.read(131073)
    if len(encrypted) > 131072:
        raise ValueError("Session exceeds limit")
    data = json.loads(protect_session(encrypted, decrypt=True))
    jar = CookieJar()
    for record in data["cookies"]:
        record["rest"] = record.pop("_rest")
        cookie = Cookie(**record)
        if not cookie.is_expired():
            jar.set_cookie(cookie)
    return data["username"], jar


WIKI_PROBE = "https://test.wikipedia.org/w/api.php?action=query&meta=userinfo&format=json"


def login_redirect(current, location, approved, central, submitted):
    if central and submitted:
        candidate = target(urljoin(current, location))
        if candidate.hostname == WIKI_HOST:
            return candidate.geturl()
        if candidate.hostname == AUTH_HOST and target(current).hostname == AUTH_HOST:
            return candidate.geturl()
        raise NavigationDenied("Redirecionamento fora do login da Wikipedia de testes bloqueado.")
    return redirect_destination(current, location, approved)


def verified_identity(body, username):
    try:
        user = json.loads(body)["query"]["userinfo"]
        return (type(user.get("id")) is int and user["id"] > 0 and "anon" not in user
                and user.get("name", "").replace("_", " ").casefold() == username.replace("_", " ").casefold())
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = None
        self.images = []
        self.stylesheets = []
        self.forms = []
        self.form = None

    def handle_starttag(self, tag, attrs):
        if self.hidden is None:
            fields = dict(attrs)
            if tag == "form" and self.form is None and len(self.forms) < 8:
                if (fields.get("method") or "").lower() == "post" and fields.get("enctype", "application/x-www-form-urlencoded") == "application/x-www-form-urlencoded":
                    self.form = {"action": fields.get("action") or "", "fields": []}
            elif tag == "input" and self.form is not None and len(self.form["fields"]) < 32:
                name = fields.get("name")
                kind = (fields.get("type") or "text").lower()
                if name and len(name) <= 128 and "disabled" not in fields and "form" not in fields and kind in ("text", "email", "password", "hidden"):
                    self.form["fields"].append((name, kind, fields.get("value") or ""))
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
        if tag == "form" and self.hidden is None and self.form is not None:
            if any(kind == "password" for _, kind, _ in self.form["fields"]):
                self.forms.append(self.form)
            self.form = None
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


def fetch(origin, destination, image=False, css=False, login=None, session=None, download=False, skill=False):
    approved = target(origin)
    if approved.path not in ("", "/") or approved.query or approved.fragment:
        raise ValueError("Approval must identify an origin")
    cookies = session[1] if session is not None else CookieJar() if login is not None else None
    central = (login is not None and approved.hostname == AUTH_HOST
               and target(destination).path == AUTH_PATH and target(login["action"]).path == AUTH_PATH
               and target(login["action"]).hostname == AUTH_HOST)
    verifying = session is not None
    submitted = verifying
    payload = None
    context = ssl.create_default_context()
    expires = time.monotonic() + 15
    for _ in range(10 if central else 6):
        url = target(destination)
        if url.hostname != approved.hostname and not (central and submitted and url.hostname == WIKI_HOST):
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
                request = Request(destination)
                if cookies is not None:
                    cookies.add_cookie_header(request)
                cookie = request.get_header("Cookie")
                headers = f"{'POST' if payload is not None else 'GET'} {path} HTTP/1.1\r\nHost: {url.hostname}\r\nAccept: {accept}\r\nUser-Agent: {USER_AGENT}\r\nConnection: close\r\n"
                if cookie:
                    if any(ord(c) < 32 or ord(c) == 127 for c in cookie):
                        raise ValueError("Invalid session cookie")
                    headers += f"Cookie: {cookie}\r\n"
                if payload is not None:
                    headers += f"Content-Type: application/x-www-form-urlencoded\r\nContent-Length: {len(payload)}\r\n"
                tls.sendall((headers + "\r\n").encode("ascii") + (payload or b""))
                with HTTPResponse(tls) as response:
                    response.begin()
                    if cookies is not None:
                        cookies.extract_cookies(response, request)
                    if response.status in (301, 302, 303, 307, 308):
                        location = response.getheader("Location")
                        if not location or "\\" in location or any(ord(c) <= 32 or ord(c) == 127 for c in location):
                            raise ValueError("Invalid redirect")
                        if len(location) > 4096 or (":" in location.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
                                                    and not location.lower().startswith("https://")):
                            raise ValueError("Invalid redirect")
                        if payload is not None and response.status in (307, 308):
                            raise ValueError("Login POST cannot be replayed by a redirect")
                        payload = None
                        if verifying:
                            raise NavigationDenied("A consulta da sessão foi redirecionada.")
                        destination = login_redirect(destination, location, approved, central, submitted)
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
                    if verifying:
                        allowed = ("application/json",)
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
                    if verifying:
                        username = session[0] if session is not None else login["username"]
                        authenticated = verified_identity(body, username)
                        if authenticated and central:
                            save_session(username, cookies)
                        return {"submitted": True, "authenticated": authenticated}
                    if central and submitted and url.hostname == WIKI_HOST:
                        destination = WIKI_PROBE
                        payload = None
                        verifying = True
                        continue
                    if image:
                        return {"image": base64.b64encode(body).decode("ascii")}
                    if css:
                        return {"css": body.decode("utf-8", errors="replace")}
                    images = []
                    stylesheets = []
                    text = body.decode("utf-8", errors="replace")
                    if media == "text/html":
                        parser = PageText()
                        parser.feed(text)
                        parser.close()
                        if login is not None and not submitted:
                            if len(parser.forms) != 1:
                                raise ValueError("Expected a single supported login form")
                            form = parser.forms[0]
                            action = target(urljoin(destination, form["action"]))
                            if action.hostname != approved.hostname or action.geturl() != login["action"]:
                                raise ValueError("Login destination differs from the confirmed endpoint")
                            payload = encode_login(form, login)
                            submitted = True
                            destination = action.geturl()
                            continue
                        if login is not None:
                            return {"submitted": submitted, "login_form_present": bool(parser.forms)}
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


def encode_login(form, login):
    names = [name for name, _, _ in form["fields"]]
    passwords = [name for name, kind, _ in form["fields"] if kind == "password"]
    users = [name for name, kind, _ in form["fields"] if kind in ("text", "email")]
    if len(set(names)) != len(names) or passwords != [login["password_field"]] or login["username_field"] not in users:
        raise ValueError("Unsupported login fields")
    values = {login["username_field"]: login["username"], login["password_field"]: login["password"]}
    pairs = [(name, value if kind == "hidden" else values[name])
             for name, kind, value in form["fields"] if kind == "hidden" or name in values]
    encoded = urlencode(pairs).encode("ascii")
    if len(encoded) > 32768:
        raise ValueError("Login form exceeds limit")
    return encoded


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
    modes.add_argument("--image", action="store_true")
    modes.add_argument("--css", action="store_true")
    modes.add_argument("--login", action="store_true")
    modes.add_argument("--check-session", action="store_true")
    modes.add_argument("--quarantine-text", action="store_true")
    modes.add_argument("--skill-package", action="store_true")
    modes.add_argument("--skill-catalog", action="store_true")
    parser.add_argument("url")
    args = parser.parse_args()
    try:
        if args.check_session:
            if not session_file().is_file():
                print(json.dumps({"authenticated": False}))
            else:
                print(json.dumps(fetch("https://test.wikipedia.org", WIKI_PROBE, session=load_session())))
            return
        url = target(args.url)
        login = None
        if args.login:
            raw = sys.stdin.buffer.read(8193)
            if len(raw) > 8192:
                raise ValueError("Login request exceeds limit")
            login = json.loads(raw)
            if (not isinstance(login, dict) or set(login) != {"action", "username_field", "password_field", "username", "password"}
                    or any(not isinstance(value, str) or not value or len(value) > 4096 for value in login.values())):
                raise ValueError("Invalid login request")
        result = fetch(args.origin or f"https://{url.hostname}", args.url, image=args.image,
                       css=args.css, login=login, download=args.quarantine_text,
                       skill=args.skill_package or args.skill_catalog)
        print(json.dumps(skill_catalog(result) if args.skill_catalog else result))
    except NavigationDenied as error:
        parser.exit(1, f"{error}\n")
    except (ValueError, OSError, HTTPException) as error:
        parser.exit(1, "Login failed.\n" if args.login or args.check_session else f"Reading failed: {error}\n")


if __name__ == "__main__":
    main()
