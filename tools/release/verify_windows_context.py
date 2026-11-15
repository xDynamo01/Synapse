"""Validate scoped context and crash recovery using the installed Windows Core."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

received=[]
entered=threading.Event()
release=threading.Event()
class Provider(BaseHTTPRequestHandler):
    def reply(self, payload):
        data=json.dumps(payload).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (ConnectionResetError, BrokenPipeError):
            pass
    def do_GET(self):
        self.reply({"data":[{"id":"fixture"}]})
    def do_POST(self):
        request=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        messages=request["messages"]
        received.append(messages)
        if messages[-1]["content"]=="interrupt this turn":
            entered.set()
            release.wait(20)
        self.reply({"choices":[{"message":{"role":"assistant","content":"packaged reply"}}]})
    def log_message(self,*args): pass

with tempfile.TemporaryDirectory(prefix="Synapse-packaged-context-") as area:
    base=Path(area)
    workspace=base/"workspace"; workspace.mkdir()
    exe=Path(os.environ["SYNAPSE_PACKAGE_ACCEPTANCE"])/"synapse-backend.exe"
    server=ThreadingHTTPServer(("127.0.0.1",0),Provider)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    def start():
        return subprocess.Popen([exe,"--state-dir",base/"state","--workspace",workspace],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,encoding="utf-8",
            cwd=base,env=dict(os.environ,SYNAPSE_PYTHON_EXECUTABLE=sys.executable))
    def call(proc, command, ok=True, rid=None):
        request={"version":1,"request_id":rid or uuid.uuid4().hex,"command":command}
        proc.stdin.write(json.dumps(request)+"\n"); proc.stdin.flush()
        result=json.loads(proc.stdout.readline())
        assert result["ok"]==ok,result
        return result["result"] if ok else result["error"]
    def wait(proc, job):
        for _ in range(180):
            status=call(proc,{"type":"job_get","job_id":job})
            if status["status"]!="running": return status
            time.sleep(.1)
        raise TimeoutError(job)
    proc=start()
    try:
        call(proc,{"type":"model_register","model":{"id":"fixture","provider":"lm_studio",
            "endpoint":f"http://127.0.0.1:{server.server_address[1]}/v1","capabilities":["chat"],"memory_bytes":4096}})
        call(proc,{"type":"chat_create","chat_id":"chat","title":"Release smoke","scope":"project:presence"})
        call(proc,{"type":"memory_put","scope":"project:source","key":"release","kind":"fact","content":"scoped marker",
            "expected_revision":0,"provenance":{"source_type":"human","source_id":"test","evidence":"release fixture"},"status":"active"})
        for turn,context in [("ordinary request",[]),("referenced request",[{"scope":"project:source","key":"release"}])]:
            result=call(proc,{"type":"conversation_start","chat_id":"chat","model_id":"fixture","content":turn,"context":context})
            assert wait(proc,result["job_id"])["status"]=="succeeded"
        plain=next(messages for messages in received if messages[-1]["content"]=="ordinary request")
        guided=next(messages for messages in received if messages[-1]["content"]=="referenced request")
        assert "scoped marker" not in str(plain) and "scoped marker" in str(guided)
        started=call(proc,{"type":"conversation_start","chat_id":"chat","model_id":"fixture","content":"interrupt this turn"})
        assert entered.wait(10)
        proc.kill(); proc.wait(timeout=10)
        proc=start()
        recovered=call(proc,{"type":"job_get","job_id":started["job_id"]})
        assert recovered["status"] in {"failed","interrupted"} and recovered["error"]=="worker_interrupted",recovered
        history=call(proc,{"type":"chat_get","chat_id":"chat"})["messages"]
        assert [message["content"] for message in history if message["role"]=="assistant"]==["packaged reply"]*2
        print(json.dumps({"explicit_memory":True,"history_after_crash":True,"interrupted_job":recovered["error"]}))
    finally:
        release.set()
        if proc.poll() is None:
            proc.stdin.close(); proc.wait(timeout=10)
        server.shutdown(); server.server_close()
