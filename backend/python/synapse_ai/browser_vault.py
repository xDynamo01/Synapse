"""Local owner-scoped storage for opaque browser session handles on Windows."""
import ctypes
import json
from pathlib import Path
import re
import tempfile
import os
import uuid

from .browser_read import protect_session, target


MAX_SESSION_BYTES = 256 * 1024
_HANDLE = re.compile(r"[0-9a-f]{32}")


class SessionVault:
    def __init__(self, directory):
        directory = Path(directory)
        if not directory.is_absolute():
            raise ValueError("Session vault requires an absolute path")
        directory.mkdir(parents=True, exist_ok=True)
        if directory.resolve() != directory:
            raise ValueError("Session vault directory is redirected")
        self.directory = directory

    def save(self, origin, storage_state):
        origin = self._origin(origin)
        return self._save_record(origin, "session", self._state_for_origin(origin, storage_state))

    def save_credentials(self, origin, username, password):
        if any(not isinstance(value, str) or not value or "\x00" in value
               or len(value.encode("utf-8")) > 4096 for value in (username, password)):
            raise ValueError("Invalid browser credentials")
        return self._save_record(self._origin(origin), "credentials",
                                 {"username": username, "password": password})

    def refresh(self, origin, handle, storage_state):
        origin = self._origin(origin)
        self.load(origin, handle)
        self._save_record(origin, "session", self._state_for_origin(origin, storage_state),
                          existing_handle=handle)

    def _save_record(self, origin, kind, data, *, existing_handle=None):
        payload = json.dumps(
            {"version": 1, "origin": origin, "kind": kind, "data": data},
            separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        if len(payload) > MAX_SESSION_BYTES:
            raise ValueError("Session exceeds the vault size limit")
        encrypted = protect_session(payload)
        handle = existing_handle or uuid.uuid4().hex
        with tempfile.NamedTemporaryFile(dir=self.directory, delete=False) as file:
            temporary = Path(file.name)
            try:
                file.write(encrypted)
                file.flush()
                os.fsync(file.fileno())
                file.close()
                destination = self._path(handle)
                if existing_handle is None:
                    os.replace(temporary, destination)
                else:
                    # ReplaceFile requires the destination to exist at commit time.
                    # A concurrent revocation must never recreate the record.
                    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                    replace = kernel.ReplaceFileW
                    replace.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                                        ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
                    replace.restype = ctypes.c_int
                    if not replace(str(destination), str(temporary), None, 0, None, None):
                        raise ctypes.WinError(ctypes.get_last_error())
            finally:
                temporary.unlink(missing_ok=True)
        return handle

    def load(self, origin, handle):
        origin = self._origin(origin)
        record = self._load_record(origin, handle)
        if record["kind"] != "session":
            raise ValueError("Handle does not identify a browser session")
        return self._state_for_origin(origin, record["data"])

    def load_credentials(self, origin, handle):
        record = self._load_record(self._origin(origin), handle)
        if record["kind"] != "credentials":
            raise ValueError("Handle does not identify browser credentials")
        return record["data"]

    def list_records(self, origin):
        origin = self._origin(origin)
        results = []
        for path in sorted(self.directory.glob("*.dpapi")):
            if path.is_symlink() or not _HANDLE.fullmatch(path.stem):
                continue
            try:
                record = self._read_record(path)
            except (OSError, ValueError):
                continue
            if record.get("version") == 1 and record.get("origin") == origin:
                kind = record.get("kind")
                if kind in ("session", "credentials"):
                    results.append({"handle":path.stem, "kind":kind})
                    if len(results) == 64:
                        break
        return results

    def _load_record(self, origin, handle):
        record = self._read_record(self._path(handle))
        if record.get("version") != 1 or record.get("origin") != origin:
            raise ValueError("Vault record scope does not match the requested origin")
        return record

    @staticmethod
    def _read_record(path):
        if path.is_symlink():
            raise ValueError("Vault entry is redirected")

        with path.open("rb") as file:
            encrypted = file.read(MAX_SESSION_BYTES * 2 + 1)
        if len(encrypted) > MAX_SESSION_BYTES * 2:
            raise ValueError("Invalid encrypted record")
        record = json.loads(protect_session(encrypted, decrypt=True))
        if not isinstance(record, dict):
            raise ValueError("Invalid browser vault record")
        return record

    def revoke(self, origin, handle):
        self._load_record(self._origin(origin), handle)
        self._path(handle).unlink()

    def _path(self, handle):
        if not isinstance(handle, str) or not _HANDLE.fullmatch(handle):
            raise ValueError("Invalid session handle")
        return self.directory / f"{handle}.dpapi"

    @staticmethod
    def _origin(origin):
        url = target(origin)
        if url.path not in ("", "/") or url.query or url.fragment:
            raise ValueError("Session scope must be an HTTPS origin")
        return f"https://{url.hostname}"

    @staticmethod
    def _state_for_origin(origin, state):
        host = target(origin).hostname
        cookies = [
            cookie for cookie in state.get("cookies", [])
            if cookie.get("domain") == host and cookie.get("secure") is True
        ]
        origins = [
            entry for entry in state.get("origins", [])
            if entry.get("origin") == origin
        ]
        return {"cookies": cookies, "origins": origins}
