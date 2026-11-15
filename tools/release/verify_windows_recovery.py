"""Validate authorized writes and prepared-effect recovery in an installed Core."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import uuid

installed=Path(os.environ["SYNAPSE_PACKAGE_ACCEPTANCE"])
with tempfile.TemporaryDirectory(prefix="synapse-release-tool-") as area:
    base=Path(area)
    state=base/"state"
    work=base/"workspace"
    work.mkdir()
    core=installed/"synapse-backend.exe"
    def command(payload, expected_error=None):
        data=json.dumps({"version":1,"request_id":uuid.uuid4().hex,"command":payload})+"\n"
        result=subprocess.run([core,"--state-dir",state,"--workspace",work],input=data,
            capture_output=True,text=True,encoding="utf-8",check=True,timeout=20,cwd=base)
        response=json.loads(result.stdout)
        if expected_error:
            assert response["error"]["code"]==expected_error,response
            return response["error"]
        assert response["ok"],response
        return response["result"]
    body="disposable release proof"
    digest=hashlib.sha256(body.encode()).hexdigest()
    proposal=command({"type":"mission_propose","mission_id":"tools","contract":{
        "version":1,"scope":"project:package","objective":"Publish two approved text files",
        "actions":["artifact_create"],"resources":["allowed.txt","pending.txt"],
        "artifact_digests":{"allowed.txt":digest,"pending.txt":digest},"rollback":"manual removal"}})
    command({"type":"mission_approve","mission_id":"tools","contract_digest":proposal["contract_digest"]})
    def create(path,error=None):
        return command({"type":"tool_execute","mission_id":"tools","operation":{
            "type":"create","path":path,"content":body}},error)
    create("outside.txt","permission_denied")
    create("allowed.txt")
    assert (work/"allowed.txt").read_text()==body
    assert not (work/"outside.txt").exists()

    # Reproduce the persistent state left after a prepare receipt with no write.
    # The production executable handles the recovery, without test fault flags.
    with closing(sqlite3.connect(state/"core.sqlite3")) as database, database:
        owner_root=database.execute("SELECT value FROM metadata WHERE key='workspace_root'").fetchone()[0]
        target=str(Path(owner_root)/"pending.txt")
        database.execute("INSERT INTO tool_intents(request_id,request_digest,mission_id,target,content_digest,status) VALUES(?,?,?,?,?,'prepared')",
            ("fixture-prepared","discard-only","tools",target,digest))
        database.execute("INSERT INTO intent_operations VALUES(?,?)",
            ("fixture-prepared",json.dumps({"type":"create","path":"pending.txt","content":body})))
    create("pending.txt","recovery_required")
    assert not (work/"pending.txt").exists()
    command({"type":"tool_recovery","intent_id":"fixture-prepared","mode":"safe_abandon"})
    create("pending.txt")
    assert (work/"pending.txt").read_text()==body
    print(json.dumps({"approved_write":True,"outside_contract_denied":True,
        "pending_write_blocked":True,"safe_abandon_applied":True,"authorized_write_after_recovery":True}))
