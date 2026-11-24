"""Small versioned real-model regression gate, through actual Core commands.

Uses only synthetic input and an already resident local model. Never downloads,
loads, unloads or substitutes models. This is not an all-domain quality claim.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
CANARY="EVIDENCIA-5927"

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary",type=Path,required=True)
    parser.add_argument("--model",required=True)
    parser.add_argument("--model-bytes",type=int,default=4683073536)
    parser.add_argument("--check-runtime",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    resident=json.loads(subprocess.check_output(["lms","ps","--json"],text=True,encoding="utf-8",timeout=20))
    selected=next((model for model in resident if model.get("identifier")==args.model),None)
    if selected is None or selected.get("contextLength")!=32768:
        raise RuntimeError("The requested local model must already be resident with 32768 context tokens")
    model_config={key:selected.get(key) for key in ("identifier","modelKey","contextLength","quantization","sizeBytes","parallel")}
    source=args.binary.resolve(strict=True)
    binary_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    dataset_path=Path(__file__).with_name("model-evals-v1.json")
    dataset=json.loads(dataset_path.read_text(encoding="utf-8"))
    rows=[]
    with tempfile.TemporaryDirectory(prefix="synapse-model-evals-") as temporary:
        root=Path(temporary);workspace=root/"workspace";workspace.mkdir()
        binaries=root/"private-binaries";binaries.mkdir()
        binary=binaries/source.name;shutil.copyfile(source,binary)
        env=os.environ|{"SYNAPSE_PYTHON_EXECUTABLE":sys.executable,"SYNAPSE_CHECK_PYTHON_EXECUTABLE":str(args.check_runtime.resolve(strict=True)),"SYNAPSE_MANAGE_LOCAL_MODELS":"1"}
        with (root/"private-core.log").open("w",encoding="utf-8") as error_log:
            core=subprocess.Popen([str(binary),"--state-dir",str(root/"state"),"--workspace",str(workspace)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=error_log,text=True,encoding="utf-8",env=env)
            replies=queue.Queue()
            def reader():
                for line in core.stdout:replies.put(line)
                replies.put(None)
            threading.Thread(target=reader,daemon=True).start()
            counter=0
            def call(command,retry_busy=False):
                nonlocal counter
                deadline=time.monotonic()+120
                while True:
                    counter+=1
                    core.stdin.write(json.dumps({"version":1,"request_id":f"eval-{counter}","command":command})+"\n");core.stdin.flush()
                    line=replies.get(timeout=150)
                    if line is None:raise RuntimeError("Core stopped; private content withheld")
                    response=json.loads(line)
                    if response["ok"]:return response["result"]
                    if retry_busy and response["error"]["code"]=="worker_busy" and time.monotonic()<deadline:
                        time.sleep(.15)
                        continue
                    raise RuntimeError("Core command refused: "+response["error"]["code"])
            def wait(command,done,seconds=240):
                end=time.monotonic()+seconds
                while time.monotonic()<end:
                    result=call(command)
                    if done(result):return result
                    time.sleep(.1)
                raise RuntimeError("Model eval deadline")
            def chat(chat_id):
                call({"type":"chat_create","chat_id":chat_id,"title":"Synthetic model eval","scope":"project:eval"})
            def turn(chat_id,content,**extra):
                started=call({"type":"input_submit","input":{"chat_id":chat_id,"content":content,"model_id":args.model,**extra}},retry_busy=True)
                job=wait({"type":"job_get","job_id":started["job_id"]},lambda j:j["status"]!="running")
                return started,job
            try:
                call({"type":"model_register","model":{"id":args.model,"provider":"lm_studio","endpoint":"http://127.0.0.1:1234/v1","capabilities":["chat"],"memory_bytes":args.model_bytes,"generation":{"max_output_tokens":1400,"timeout_ms":120000,"reasoning_effort":"none"}}})
                call({"type":"project_register","scope":"project:eval","root":str(workspace)})
                call({"type":"memory_put","scope":"project:eval","key":"validation","kind":"fact","content":"O codigo de validacao do projeto e "+CANARY+".","expected_revision":0,"status":"active","provenance":{"source_type":"eval","source_id":"synthetic","evidence":"Synthetic case only"}})
                for case in dataset["cases"]:
                    begin=time.monotonic();chat(case["id"])
                    if case["id"]=="identity":
                        route,job=turn(case["id"],"Qual e o seu nome? Responda apenas o nome do agente.")
                        observed=job["status"]=="succeeded" and "ARTEMIS" in "".join(c for c in job.get("content","").upper() if c.isalpha())
                    elif case["id"]=="memory-not-loaded":
                        route,job=turn(case["id"],"Qual e o codigo de validacao do projeto? Se nao foi fornecido, diga que nao sabe.")
                        if job["status"]!="succeeded":raise RuntimeError("Unreferenced memory case had no valid answer")
                        observed=CANARY in job.get("content","")
                    elif case["id"]=="memory-explicit":
                        route,job=turn(case["id"],"Qual e o codigo de validacao? Responda apenas o codigo.",context=[{"scope":"project:eval","key":"validation"}])
                        observed=job["status"]=="succeeded" and CANARY in job.get("content","")
                    elif case["id"]=="translation":
                        route,job=turn(case["id"],"Traduza para ingles: bom dia.",intent="specialized",capability="translation")
                        observed=route["route"]=="specialized" and job["status"]=="succeeded" and "good morning" in job.get("content","").lower()
                    else:
                        route,job=turn(case["id"],"Crie somente agent_result.json contendo exatamente {\"agent\":\"ARTEMIS\",\"executed\":true}. Use json_validate para esse arquivo. Uma unica tarefa simples, sem swarm.",intent="mission",scope="project:eval",review_model_id=args.model)
                        if job["status"]!="succeeded":raise RuntimeError("Planner did not complete")
                        plan=call({"type":"mission_plan_get","mission_id":route["mission_id"]})
                        assert not (workspace/"agent_result.json").exists()
                        call({"type":"mission_approve","mission_id":route["mission_id"],"contract_digest":plan["mission"]["contract_digest"]})
                        if "task_graph" in plan:
                            result=wait({"type":"task_graph","action":"get","payload":{"graph_id":route["mission_id"]}},lambda r:r["state"] in ("integrated","failed"))
                            integrated=result["state"]=="integrated"
                        else:
                            call({"type":"mission_execute","mission_id":route["mission_id"]},retry_busy=True)
                            result=wait({"type":"mission_run_get","mission_id":route["mission_id"]},lambda r:r["status"] in ("integrated","failed","cancelled","recovery_required"))
                            integrated=result["status"]=="integrated"
                        observed=integrated and json.loads((workspace/"agent_result.json").read_text(encoding="utf-8"))=={"agent":"ARTEMIS","executed":True}
                    metrics=call({"type":"operational","action":"budget_get","payload":{"job_id":route["job_id"]}})
                    rows.append({**case,"observed":observed,"pass":observed==case["expected"],"latency_ms":round((time.monotonic()-begin)*1000),"operational":metrics})
                    print(json.dumps({k:v for k,v in rows[-1].items() if k!="operational"}),flush=True)
            finally:
                core.stdin.close()
                try:core.wait(timeout=15)
                except subprocess.TimeoutExpired:core.kill();core.wait()
    classes={}
    for row in rows:
        counts=classes.setdefault(row["class"],{"positive":0,"negative":0,"false_positives":0,"false_negatives":0})
        counts["positive" if row["expected"] else "negative"]+=1
        counts["false_positives"]+=int(row["observed"] and not row["expected"])
        counts["false_negatives"]+=int(not row["observed"] and row["expected"])
    report={"version":1,"dataset_sha256":hashlib.sha256(dataset_path.read_bytes()).hexdigest(),"core_sha256":binary_hash,"source_binary_stable":binary_hash==hashlib.sha256(source.read_bytes()).hexdigest(),"model":args.model,"model_configuration":model_config,"context_tokens":selected["contextLength"],"generation":{"max_output_tokens":1400,"timeout_ms":120000,"reasoning_effort":"none"},"cases":rows,"classes":classes,"pass":len(rows)==len(dataset["cases"]) and all(r["pass"] for r in rows),"limitations":"Small regression sample; no universal project/domain accuracy claim"}
    report["pass"] &= report["source_binary_stable"]
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 0 if report["pass"] else 1

if __name__=="__main__":sys.exit(main())
