"""Test-only OpenAI-compatible loopback fixture; never imported by production."""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import NamedTemporaryFile

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
        is_plan = request.get("response_format", {}).get("json_schema", {}).get("name") == "mission_plan"
        posted = marker.parent / "learning-post" if "response_format" in request and not is_plan else marker
        # Publish only complete JSON. The CLI tests use marker existence as readiness.
        with NamedTemporaryFile(dir=posted.parent, delete=False, mode="w", encoding="utf-8") as staged:
            json.dump(request, staged, ensure_ascii=False)
        temporary = Path(staged.name)
        try:
            temporary.replace(posted)
        finally:
            temporary.unlink(missing_ok=True)
        if (marker.parent / "require-one-system").exists() and any(message["role"] == "system" for message in request["messages"][1:]):
            self.send_error(500, "System message must be at the beginning.")
            return
        while held and not release.exists():
            time.sleep(.01)
        while "response_format" in request and not is_plan and (marker.parent / "learning-hold").exists():
            time.sleep(.01)
        try:
            scripted = marker.parent / "learning-response"
            mapping = marker.parent / "learning-map"
            if is_plan:
                content = (marker.parent / "mission-response").read_text(encoding="utf-8")
            elif "response_format" in request and mapping.exists():
                content = json.dumps(json.loads(mapping.read_text(encoding="utf-8"))[request["messages"][-1]["content"]])
            else:
                conversation = marker.parent / "conversation-response"
                content = (scripted.read_text(encoding="utf-8") if scripted.exists() else json.dumps({"candidates": []})) if "response_format" in request else (conversation.read_text(encoding="utf-8") if conversation.exists() else "Olá, ação")
            self.reply({"choices": [{"message": {"role": "assistant", "content": content}}]})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
print(server.server_port, flush=True)
server.serve_forever()
