from __future__ import annotations

import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from synapse.sidecar import (
    BackendHandshake,
    backend_is_ready,
    bind_backend_socket,
    remove_owned_handshake,
    write_handshake_atomic,
)


class SidecarHandshakeTests(unittest.TestCase):
    @staticmethod
    def handshake(port: int = 8717) -> BackendHandshake:
        return BackendHandshake(
            schema_version=1,
            host="127.0.0.1",
            port=port,
            pid=os.getpid(),
            token="test-launch-token-1234",
            started_at="2026-06-29T12:00:00+00:00",
            version="0.1.0",
        )

    def test_reserves_a_dynamic_port_before_uvicorn_starts(self) -> None:
        backend_socket = bind_backend_socket("127.0.0.1", 0)
        try:
            self.assertGreater(backend_socket.getsockname()[1], 0)
        finally:
            backend_socket.close()

    def test_handshake_is_atomically_replaced(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "runtime" / "backend-handshake.json"
            write_handshake_atomic(path, self.handshake(9101))
            write_handshake_atomic(path, self.handshake(9102))

            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["port"], 9102)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_cleanup_only_removes_owned_handshake(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "runtime" / "backend-handshake.json"
            write_handshake_atomic(path, self.handshake())

            remove_owned_handshake(path, os.getpid(), "another-token")
            self.assertTrue(path.exists())
            remove_owned_handshake(path, os.getpid(), "test-launch-token-1234")
            self.assertFalse(path.exists())

    def test_backend_ready_requires_post_startup_probe(self) -> None:
        server = _ProbeServer({"health_only": True})
        with server.running() as port:
            self.assertFalse(backend_is_ready("127.0.0.1", port))

    def test_backend_ready_accepts_only_completed_lifecycle(self) -> None:
        server = _ProbeServer({"ready": True, "startup_status": "ready"})
        with server.running() as port:
            self.assertTrue(backend_is_ready("127.0.0.1", port))

    def test_backend_ready_accepts_degraded_lifecycle(self) -> None:
        server = _ProbeServer({"ready": True, "startup_status": "degraded"})
        with server.running() as port:
            self.assertTrue(backend_is_ready("127.0.0.1", port))

    def test_backend_ready_rejects_degraded_lifecycle(self) -> None:
        server = _ProbeServer({"ready": False, "startup_status": "failed"})
        with server.running() as port:
            self.assertFalse(backend_is_ready("127.0.0.1", port))


class _ProbeServer:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def running(self) -> "_RunningProbeServer":
        return _RunningProbeServer(self.payload)


class _RunningProbeServer:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.server: HTTPServer | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> int:
        payload = self.payload

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/api/sidecar/startup-ready":
                    self.send_response(404)
                    self.end_headers()
                    return
                if payload.get("health_only"):
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps({
                    "schema": "synapse-sidecar-startup-ready-v1",
                    "ready": payload["ready"],
                    "startup_status": payload["startup_status"],
                    "resources": [],
                }).encode("utf-8")
                self.send_response(200 if payload["ready"] else 503)
                self.send_header("X-Synapse-Service", "synapse-backend")
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return int(self.server.server_address[1])

    def __exit__(self, *_exc: object) -> None:
        assert self.server is not None
        self.server.shutdown()
        self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
