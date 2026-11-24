"""Exercise the packaged supervised Python worker against a synthetic loopback provider."""
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def worker_smoke(programs):
    posts = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_GET(self):
            if self.path!='/v1/models':
                self.send_error(404)
                return
            body=json.dumps({'data':[{'id':'distribution-fixture'}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def do_POST(self):
            value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            posts.append(value)
            schema=value.get('response_format',{}).get('json_schema',{}).get('name')
            if schema=='mission_plan':
                content=json.dumps({'summary':'Installed JSON check fixture','artifacts':[{'path':'installed.json','purpose':'Installed check receipt'}],'checks':[{'kind':'json_validate','entrypoint':'installed.json'}],'tasks':[]})
            elif schema=='mission_generate':
                content=json.dumps({'artifacts':[{'path':'installed.json','content':'{"installed":true,"checked":true}'}]})
            elif schema=='mission_review':
                content=json.dumps({'approved':True,'reason':'Synthetic fixture matches the exact objective and native check passed.'})
            else:
                content=json.dumps({'candidates':[]}) if 'response_format' in value else 'distribution-worker-ok'
            body=json.dumps({'choices':[{'message':{'role':'assistant','content':content}}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    provider=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=provider.serve_forever,daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='synapse-installed-worker-') as temporary:
            root=Path(temporary)
            workspace=root/'workspace'
            workspace.mkdir()
            environment={key:value for key,value in os.environ.items() if not key.startswith('SYNAPSE_') and key not in ('PYTHONPATH','PYTHONHOME')}
            environment.update(SYNAPSE_PYTHON_EXECUTABLE=str(programs/'runtime/python.exe'),PYTHONDONTWRITEBYTECODE='1')
            environment['SYNAPSE_CHECK_PYTHON_EXECUTABLE']=str(programs/'check-runtime/runtime/python.exe')
            for key in ('PYTHONPATH','PYTHONHOME','SYNAPSE_MANAGE_LOCAL_MODELS','SYNAPSE_LMS_EXECUTABLE'):
                environment.pop(key,None)
            child=subprocess.Popen([programs/'synapse-backend.exe','--state-dir',root/'state','--workspace',workspace],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',cwd=root,env=environment)
            replies=queue.Queue()
            reader=threading.Thread(target=lambda:[replies.put(line) for line in child.stdout],daemon=True)
            reader.start()
            index=0
            def call(command,identifier=None):
                nonlocal index
                index+=1
                identifier=identifier or f'worker-{index}'
                child.stdin.write(json.dumps({'version':1,'request_id':identifier,'command':command})+'\n')
                child.stdin.flush()
                try:
                    response=json.loads(replies.get(timeout=15))
                except queue.Empty:
                    raise RuntimeError('Packaged worker/Core timed out')
                if not response.get('ok'):
                    raise RuntimeError(f'Packaged worker/Core rejected command: {response}')
                return response['result']
            try:
                call({'type':'model_register','model':{'id':'distribution-fixture','provider':'lm_studio','endpoint':f'http://127.0.0.1:{provider.server_port}','capabilities':['chat'],'memory_bytes':1024}})
                call({'type':'project_register','scope':'project:distribution','root':str(workspace)})
                call({'type':'chat_create','chat_id':'fixture','title':'Fixture','scope':'project:distribution'})
                call({'type':'conversation_start','chat_id':'fixture','model_id':'distribution-fixture','content':'Distribution synthetic worker probe'},'distribution-job')
                deadline=time.monotonic()+20
                while time.monotonic()<deadline:
                    result=call({'type':'job_get','job_id':'distribution-job'})
                    if result['status']!='running':
                        if result['status']!='succeeded':
                            raise RuntimeError(f'Packaged worker failed: {result}')
                        break
                    time.sleep(.025)
                else:
                    raise RuntimeError('Packaged worker job deadline exceeded')
                if not posts or posts[0]['model']!='distribution-fixture':
                    raise RuntimeError('Synthetic provider did not receive packaged worker request')
                print('Installed Core supervised bundled Python worker against synthetic loopback provider; no model loaded.')
                planned=call({'type':'input_submit','input':{'chat_id':'fixture','intent':'mission','scope':'project:distribution','content':'Create installed.json containing exactly {"installed":true,"checked":true}; validate with json_validate.','model_id':'distribution-fixture','review_model_id':'distribution-fixture'}})
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    job=call({'type':'job_get','job_id':planned['job_id']})
                    if job['status']!='running':
                        if job['status']!='succeeded':
                            raise RuntimeError('Installed fixture planner failed: '+str(job.get('error')))
                        break
                    time.sleep(.025)
                else:
                    raise RuntimeError('Installed fixture planner timed out')
                plan=call({'type':'mission_plan_get','mission_id':planned['mission_id']})
                if (workspace/'installed.json').exists():
                    raise RuntimeError('Installed fixture wrote before approval')
                call({'type':'mission_approve','mission_id':planned['mission_id'],'contract_digest':plan['mission']['contract_digest']})
                call({'type':'mission_execute','mission_id':planned['mission_id']})
                deadline=time.monotonic()+60
                while time.monotonic()<deadline:
                    result=call({'type':'mission_run_get','mission_id':planned['mission_id']})
                    if result['status'] in ('integrated','failed','cancelled','recovery_required'):
                        if result['status']!='integrated':
                            raise RuntimeError('Installed native-check mission failed: '+str(result.get('error')))
                        break
                    time.sleep(.025)
                else:
                    raise RuntimeError('Installed native-check mission timed out')
                if json.loads((workspace/'installed.json').read_text())!={'installed':True,'checked':True}:
                    raise RuntimeError('Installed mission output mismatch')
                print('Installed Core planned, generated, LPAC-validated, reviewed and integrated a real JSON artifact using bundled checker runtime.')
            finally:
                child.kill()
                child.wait(timeout=10)
                reader.join(timeout=2)
                child.stdin.close()
                child.stdout.close()
                child.stderr.close()
    finally:
        provider.shutdown()
        provider.server_close()
        thread.join(timeout=2)

