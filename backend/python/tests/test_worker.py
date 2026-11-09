import hashlib
import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from synapse_ai.providers import ProviderError, validate_endpoint, infer


class Handler(BaseHTTPRequestHandler):
    mode = "ok"
    def log_message(self, *args):
        pass
    def do_GET(self):
        body = {"data": [{"id": "selected"}]} if self.mode != "missing" else {"data": []}
        self.reply(body)
    def do_POST(self):
        length = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(length))
        self.server.seen = request
        if self.mode == "redirect":
            self.send_response(302)
            self.send_header("Location", "http://example.org/")
            self.end_headers()
        elif self.mode == "bad":
            self.reply({"choices": [{"message": {"role": "assistant", "tool_calls": [{"id": "x"}], "content": "unsafe"}}]})
        else:
            self.reply({"choices": [{"message": {"role": "assistant", "content": "answer"}}]})
    def reply(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.seen = None
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
    def request(self):
        bare = {"version": 1, "request_id": "r", "model_id": "selected", "endpoint": self.endpoint, "prompt": "private question"}
        digest = hashlib.sha256(json.dumps(bare, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        return bare | {"digest": digest}
    def worker(self, request):
        child = subprocess.run([sys.executable, "-m", "synapse_ai"], input=json.dumps(request).encode()+b"\n", cwd=ROOT, capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 0, child.stderr)
        return [json.loads(line) for line in child.stdout.splitlines()]
    def test_handshake_real_loopback_and_bound_request(self):
        hello, answer = self.worker(self.request())
        self.assertEqual(hello, {"type": "hello", "version": 1})
        self.assertTrue(answer["ok"])
        self.assertEqual(answer["content"], "answer")
        self.assertEqual(self.server.seen, {"model": "selected", "messages": [{"role": "user", "content": "private question"}], "stream": False, "max_tokens": 1024})
    def test_digest_and_version_rejected_before_provider(self):
        request = self.request(); request["digest"] = "0" * 64
        self.assertEqual(self.worker(request)[1]["error"], "digest_mismatch")
        request = self.request(); request["version"] = 2
        self.assertEqual(self.worker(request)[1]["error"], "unsupported_version")
        self.assertIsNone(self.server.seen)
    def test_endpoint_and_model_and_malformed_are_distinct(self):
        for url in ("https://127.0.0.1:1", "http://localhost:1", "http://127.0.0.1:1/v1/other", "http://user@127.0.0.1:1"):
            with self.assertRaises(ProviderError): validate_endpoint(url)
        Handler.mode = "missing"
        self.assertEqual(self.worker(self.request())[1]["error"], "model_unavailable")
        Handler.mode = "bad"
        self.assertEqual(self.worker(self.request())[1]["error"], "provider_malformed")
        Handler.mode = "redirect"
        self.assertEqual(self.worker(self.request())[1]["error"], "provider_redirect")
        Handler.mode = "ok"

if __name__ == "__main__":
    unittest.main()
