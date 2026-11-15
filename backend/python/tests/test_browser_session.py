import os
import select
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from synapse_ai.browser_session import BrowserSession
from synapse_ai.browser_transport import Response
from synapse_ai.browser_vault import SessionVault


@unittest.skipUnless(os.environ.get("SYNAPSE_TEST_PLAYWRIGHT"), "requires dedicated Chromium")
class BrowserSessionTests(unittest.TestCase):
    def test_untrusted_markup_remains_inert_in_the_dedicated_browser(self):
        from playwright.sync_api import sync_playwright

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener, sync_playwright() as runtime:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            canary = f"http://127.0.0.1:{listener.getsockname()[1]}/unexpected"
            body = (
                f'<meta http-equiv="refresh" content="0;url={canary}">'
                f'<iframe src="{canary}">frame content</iframe><img src="{canary}">'
                f'<link rel="stylesheet" href="{canary}">'
                '<script>document.body.textContent = "script content";</script>'
                '<p>Safe projection marker</p>'
            ).encode()
            origin = "https://first.example.com"
            transport = lambda *args, **kwargs: Response(200, (), body)
            with BrowserSession(runtime, origin, transport=transport) as session:
                result = session.read(origin + "/protected")
                self.assertEqual(result["text"].strip(), "Safe projection marker")
                self.assertEqual(session.context.cookies(), [])
                self.assertEqual(session.page.url, "about:blank")
                self.assertEqual(select.select([listener], [], [], 0.25)[0], [])

    def test_two_forms_restore_sessions_without_replaying_credentials(self):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as runtime, tempfile.TemporaryDirectory() as directory:
            vault = SessionVault(directory)
            for host, username_type in [("first.example.com", "text"), ("second.example.com", "email")]:
                with self.subTest(host=host):
                    origin = "https://" + host
                    requests = []

                    def site(approved, address, *, method, form_action, body, cookie):
                        self.assertEqual(approved, origin)
                        requests.append((address, method))
                        if address.endswith("/login"):
                            markup = f'<form method="post" action="/submit"><input type="{username_type}" name="user"><input name="pass" type="password"><input name="csrf" type="hidden" value="one"></form>'
                            return Response(200, (), markup.encode())
                        if address.endswith("/submit"):
                            self.assertEqual(method, "POST")
                            self.assertEqual(form_action, address)
                            self.assertEqual(parse_qs(body.decode()), {
                                "user": ["owner@example.com"], "pass": ["disposable"], "csrf": ["one"]
                            })
                            return Response(303, (("Location", "/account"),
                                                  ("Set-Cookie", "session=cHJvb2Y=; Secure; HttpOnly; Path=/")), b"")
                        return Response(200, (), b"<p>Signed in: fixture owner</p><p>session cHJvb2Y=</p>" if cookie == "session=cHJvb2Y="
                                        else b"<p>Sign in required</p>")

                    credential = vault.save_credentials(origin, "owner@example.com", "disposable")
                    with BrowserSession(runtime, origin, transport=site) as session:
                        result = session.login(page=origin + "/login", action=origin + "/submit",
                                               probe=origin + "/account", expected_text="Signed in: fixture owner",
                                               **vault.load_credentials(origin, credential))
                        self.assertTrue(result["authenticated"])
                        self.assertEqual(session.context.cookies(), [])
                        handle = vault.save(origin, session.storage_state())
                    with BrowserSession(runtime, origin, storage_state=vault.load(origin, handle),
                                        transport=site) as restored:
                        text = restored.read(origin + "/account")["text"]
                        self.assertIn("Signed in", text)
                        self.assertIn("session [omitido]", text)
                        self.assertNotIn("cHJvb2Y=", text)
                        self.assertEqual(restored.context.cookies(), [])
                        with self.assertRaisesRegex(ValueError, "outside"):
                            restored.read("https://foreign.example.com/account")
                    self.assertEqual(sum(method == "POST" for _, method in requests), 1)
                    vault.revoke(origin, handle)
                    with self.assertRaises(FileNotFoundError):
                        vault.load(origin, handle)
