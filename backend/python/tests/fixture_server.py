"""Test-only OpenAI-compatible loopback fixture; never imported by production."""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

marker = Path(sys.argv[1])
release = Path(sys.argv[2])
held = sys.argv[3] == "hold"

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def reply(self, value):
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
    def do_GET(self):
        if self.path != "/v1/models":
            self.send_error(404)
            return
        self.reply({"data": [{"id": "selected"}]})
    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert request["model"] == "selected" and request["stream"] is False
        marker.write_text(json.dumps(request,ensure_ascii=False), encoding="utf-8")
        while held and not release.exists():
            time.sleep(.01)
        try:
            self.reply({"choices": [{"message": {"role": "assistant", "content": "Olá, ação"}}]})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
print(server.server_port, flush=True)
server.serve_forever()
