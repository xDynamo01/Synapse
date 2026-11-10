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
from synapse_ai.protocol import validate


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
    def test_generation_mapping_and_validation(self):
        request = self.request()
        request['version'] = 2
        request['generation'] = {'max_output_tokens': 32, 'timeout_ms': 2000, 'reasoning_effort': 'none'}
        request['digest'] = hashlib.sha256(json.dumps({k:v for k,v in request.items() if k != 'digest'}, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        self.assertTrue(self.worker(request)[1]['ok'])
        self.assertEqual(self.server.seen['max_tokens'], 32)
        self.assertEqual(self.server.seen['reasoning_effort'], 'none')
        for effort in ('provider_default', 'low', 'medium', 'high'):
            candidate = request | {'generation': request['generation'] | {'reasoning_effort': effort}}
            candidate['digest'] = hashlib.sha256(json.dumps({k:v for k,v in candidate.items() if k != 'digest'}, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
            self.assertTrue(self.worker(candidate)[1]['ok'])
            if effort == 'provider_default':
                self.assertNotIn('reasoning_effort', self.server.seen)
            else:
                self.assertEqual(self.server.seen['reasoning_effort'], effort)
        for key, value in [('max_output_tokens', True), ('max_output_tokens', 0), ('timeout_ms', False), ('timeout_ms', 120001), ('reasoning_effort', 'invalid'), ('extra', 1)]:
            candidate = request | {'generation': request['generation'] | {key: value}}
            with self.assertRaises(ValueError): validate(candidate)
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
        bare = {"version": 2, "request_id": "r", "model_id": "selected", "endpoint": self.endpoint, "messages": [{"role":"user","content":"private question"}], "generation": {"max_output_tokens":1024,"timeout_ms":10000,"reasoning_effort":"provider_default"}}
        digest = hashlib.sha256(json.dumps(bare, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        return bare | {"digest": digest}
    def worker(self, request):
        child = subprocess.run([sys.executable, "-m", "synapse_ai"], input=json.dumps(request).encode()+b"\n", cwd=ROOT, capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 0, child.stderr)
        return [json.loads(line) for line in child.stdout.splitlines()]
    def test_handshake_real_loopback_and_bound_request(self):
        hello, answer = self.worker(self.request())
        self.assertEqual(hello, {"type": "hello", "version": 2})
        self.assertTrue(answer["ok"])
        self.assertEqual(answer["content"], "answer")
        self.assertEqual(self.server.seen, {"model": "selected", "messages": [{"role": "user", "content": "private question"}], "stream": False, "max_tokens": 1024})
    def test_digest_and_version_rejected_before_provider(self):
        request = self.request(); request["digest"] = "0" * 64
        self.assertEqual(self.worker(request)[1]["error"], "digest_mismatch")
        request = self.request(); request["version"] = 1
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
    def test_message_schema_and_limits_reject_unsafe_or_incomplete_history(self):
        request=self.request()
        for messages in ([], [{"role":"tool","content":"override"}], [{"role":"assistant","content":"answer"}], [{"role":"user","content":"ok","tool_calls":[]}], [{"role":"user","content":" "}], [{"role":"user","content":"a"*32769}], [{"role":"user","content":"é"*16000}]*2, [{"role":"user","content":"x"}]*65):
            candidate=request | {"messages":messages}
            candidate["digest"]=hashlib.sha256(json.dumps({k:candidate[k] for k in ("version","request_id","model_id","endpoint","messages","generation")},sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
            with self.assertRaises(ValueError): validate(candidate)

    def test_invalid_utf8_is_rejected_before_provider(self):
        child = subprocess.run([sys.executable, "-m", "synapse_ai"], input=b'\xff\n', cwd=ROOT, capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(json.loads(child.stdout.splitlines()[1])["error"], "invalid_request")
        self.assertIsNone(self.server.seen)

if __name__ == "__main__":
    unittest.main()
