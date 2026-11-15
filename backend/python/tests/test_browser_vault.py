import importlib
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
SessionVault = importlib.import_module("synapse_ai.browser_vault").SessionVault


@unittest.skipUnless(os.name == "nt", "Windows DPAPI")
class SessionVaultTests(unittest.TestCase):
    def test_encrypted_session_survives_reopen_and_rejects_other_origins(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = SessionVault(directory)
            origin = "https://example.com"
            cookie = {"domain": "example.com", "secure": True, "value": "fixture-cookie"}
            state = {"cookies": [cookie, dict(cookie, domain="other.example.com"),
                                 dict(cookie, secure=False)],
                     "origins": [{"origin": "https://other.example.com", "localStorage": []}]}
            handle = vault.save(origin, state)
            self.assertNotIn(b"fixture-cookie", next(Path(directory).iterdir()).read_bytes())
            reopened = SessionVault(directory)
            self.assertEqual(reopened.load(origin, handle), {"cookies": [cookie], "origins": []})
            with self.assertRaisesRegex(ValueError, "scope"):
                reopened.revoke("https://other.example.com", handle)
            rotated = {"cookies": [dict(cookie, value="new-cookie")], "origins": []}
            reopened.refresh(origin, handle, rotated)
            self.assertEqual(vault.load(origin, handle), rotated)
            reopened.revoke(origin, handle)
            with self.assertRaises(FileNotFoundError):
                reopened.load(origin, handle)
            with self.assertRaises(FileNotFoundError):
                reopened.refresh(origin, handle, rotated)
            with self.assertRaisesRegex(ValueError, "Invalid session handle"):
                reopened.load(origin, "../outside")

    def test_credential_handle_is_origin_bound_and_separate_from_session_state(self):
        with tempfile.TemporaryDirectory() as directory:
            origin = "https://example.com"
            handle = SessionVault(directory).save_credentials(origin, "test", "disposable-password")
            self.assertNotIn(b"disposable-password", next(Path(directory).iterdir()).read_bytes())
            reopened = SessionVault(directory)
            with self.assertRaisesRegex(ValueError, "scope"):
                reopened.load_credentials("https://other.example.com", handle)
            with self.assertRaisesRegex(ValueError, "session"):
                reopened.load(origin, handle)
            self.assertEqual(reopened.load_credentials(origin, handle)["username"], "test")
            reopened.revoke(origin, handle)
            with self.assertRaises(FileNotFoundError):
                reopened.load_credentials(origin, handle)
