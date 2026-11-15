"""Playwright session operations with HTTPS performed by the network broker."""
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
import time
from urllib.parse import urlencode, urljoin

from .browser_read import launch_offline_browser, open_offline_page, set_inert_document, target
from .browser_transport import exchange


class BrowserSession:
    def __init__(self, runtime, origin, storage_state=None, transport=exchange):
        approved = target(origin)
        if approved.path not in ("", "/") or approved.query or approved.fragment:
            raise ValueError("Expected an HTTPS origin")
        self.origin = f"https://{approved.hostname}"
        self.transport = transport
        self.cookies = {}
        for cookie in (storage_state or {}).get("cookies", []):
            if cookie.get("domain") == approved.hostname and cookie.get("secure") is True:
                self.cookies[(cookie["name"], cookie["path"])] = cookie
        self.browser = launch_offline_browser(runtime)
        try:
            self.context, self.page = open_offline_page(self.browser)
        except BaseException:
            self.browser.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.browser.close()

    def storage_state(self):
        self._prune_cookies()
        return {"cookies":list(self.cookies.values()), "origins":[]}

    def _destination(self, address):
        parsed = target(address)
        if f"https://{parsed.hostname}" != self.origin or parsed.fragment:
            raise ValueError("Destination is outside the browser session origin")
        return parsed.geturl()

    def _store_cookies(self, address, headers):
        host = target(self.origin).hostname
        default_path = target(address).path.rpartition("/")[0] or "/"
        for key, value in headers:
            if key.lower() != "set-cookie" or len(value) > 4096:
                continue
            jar = SimpleCookie()
            jar.load(value)
            for item in jar.values():
                if item["domain"] and item["domain"].lower() != host:
                    continue
                # This session only connects to HTTPS. Keep all imported cookies HTTPS-only.
                cookie = {"name": item.key, "value": item.value, "domain": host,
                          "path": item["path"] or default_path, "secure": True,
                          "httpOnly": bool(item["httponly"])}
                if not cookie["path"].startswith("/"):
                    continue
                if item["samesite"].lower() in ("strict", "lax", "none"):
                    cookie["sameSite"] = item["samesite"].capitalize()
                try:
                    if item["max-age"]:
                        cookie["expires"] = max(0, time.time() + int(item["max-age"]))
                    elif item["expires"]:
                        cookie["expires"] = max(0, parsedate_to_datetime(item["expires"]).timestamp())
                except (ValueError, OverflowError):
                    continue
                self.cookies[(item.key,cookie["path"])] = cookie
        self._prune_cookies()

    def _prune_cookies(self):
        now = time.time()
        for key, cookie in list(self.cookies.items()):
            if cookie.get("expires", -1) != -1 and cookie["expires"] <= now:
                del self.cookies[key]

    def _cookie_header(self, address):
        self._prune_cookies()
        path = target(address).path or "/"
        applicable = [
            cookie for cookie in self.cookies.values()
            if path == cookie["path"] or path.startswith(cookie["path"].rstrip("/") + "/")
        ]
        values = []
        for cookie in sorted(applicable, key=lambda item: -len(item["path"])):
            name, value = cookie["name"], cookie["value"]
            if not name or not name.isascii() or any(char in name for char in "=; ,\t\r\n"):
                raise ValueError("Invalid browser cookie name")
            if any(not (0x21 <= ord(char) <= 0x7E) or char in '\",;\\' for char in value):
                raise ValueError("Invalid browser cookie value")
            # Browser cookie octets go over the wire verbatim. SimpleCookie
            # would quote valid base64 padding, breaking signed cookies.
            values.append(f"{name}={value}")
        return "; ".join(values)

    def _exchange(self, address, *, method="GET", form_action=None, body=b"", allowed=None):
        address = self._destination(address)
        for _ in range(6):
            if allowed is not None and address not in allowed:
                raise ValueError("Redirect is outside the approved browser destinations")
            response = self.transport(
                self.origin, address, method=method, form_action=form_action,
                body=body, cookie=self._cookie_header(address),
            )
            self._store_cookies(address, response.headers)
            if response.status not in (301, 302, 303, 307, 308):
                return address, response
            location = next((value for key, value in response.headers if key.lower() == "location"), "")
            if not location or (method == "POST" and response.status in (307, 308)):
                raise ValueError("Unapproved browser redirect")
            address = self._destination(urljoin(address, location))
            method, form_action, body = "GET", None, b""
        raise ValueError("Authenticated browser exceeded the redirect limit")

    def _document(self, response):
        if response.status != 200:
            raise ValueError("Authenticated document did not return HTTP 200")
        set_inert_document(self.page, response.body.decode("utf-8", errors="replace"))

    def read(self, address, *, allowed=None):
        known_values = {cookie["value"] for cookie in self.cookies.values()}
        source, response = self._exchange(address, allowed=allowed)
        self._document(response)
        text = self.page.locator("body").inner_text(timeout=3000)[:64000]
        known_values.update(cookie["value"] for cookie in self.cookies.values())
        for value in sorted(known_values - {""}, key=len, reverse=True):
            text = text.replace(value, "[omitido]")
        return {"source": source, "text": text[:64000]}

    def login(self, *, page, action, username, password, probe, expected_text):
        action = self._destination(action)
        probe = self._destination(probe)
        allowed = {self._destination(page), action, probe}
        if not expected_text or len(expected_text) > 256:
            raise ValueError("A bounded login verification marker is required")
        before_url, before = self._exchange(probe, allowed=allowed)
        if before_url == probe and before.status == 200:
            self._document(before)
            if expected_text in self.page.locator("body").inner_text(timeout=3000):
                raise ValueError("Authenticated probe already matched before login")
        source, response = self._exchange(page, allowed=allowed)
        self._document(response)
        forms = self.page.locator("form").evaluate_all("""forms => forms
            .filter(form => form.querySelector("input[type=password]"))
            .slice(0, 2)
            .map(form => ({
                method: form.method,
                action: form.getAttribute("action") || "",
                enctype: form.enctype,
                fields: Array.from(form.elements).slice(0, 33).map(field => ({
                    name: field.name,
                    type: field.type,
                    value: field.type === "hidden" ? field.value : "",
                    disabled: field.matches(":disabled")
                }))
            }))""")
        if len(forms) != 1:
            raise ValueError("Expected one password form")
        form = forms[0]
        if (form["method"] != "post" or form["enctype"] != "application/x-www-form-urlencoded"
                or self._destination(urljoin(source, form["action"])) != action
                or len(form["fields"]) > 32):
            raise ValueError("Login form does not match the approved submission")
        candidates = [field for field in form["fields"] if field["name"] and not field["disabled"]]
        users = [field["name"] for field in candidates if field["type"] in ("text", "email")]
        passwords = [field["name"] for field in candidates if field["type"] == "password"]
        names = [field["name"] for field in candidates]
        if len(users) != 1 or len(passwords) != 1 or len(set(names)) != len(names):
            raise ValueError("Ambiguous login fields")
        fields = [(field["name"], field["value"]) for field in candidates if field["type"] == "hidden"]
        fields.extend(((users[0], username), (passwords[0], password)))
        result_url, result = self._exchange(
            action, method="POST", form_action=action,
            body=urlencode(fields).encode("ascii"), allowed=allowed,
        )
        if result_url != probe:
            result_url, result = self._exchange(probe, allowed=allowed)
        if result_url != probe:
            raise ValueError("The authenticated probe returned a different page")
        self._document(result)
        if expected_text not in self.page.locator("body").inner_text(timeout=3000)[:64000]:
            raise ValueError("The authenticated probe did not verify login")
        return {"authenticated": True, "source": result_url}
