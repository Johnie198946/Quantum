from importlib.metadata import version
assert version("openai") == "2.24.0", "Use requirements-bridge-worker.lock runtime (OpenAI 2.24.0)"
import os,tempfile,secrets,json,time,asyncio,threading,socket,subprocess,sys
from pathlib import Path
root=Path(os.environ['TRAVEL_ACCEPTANCE_ROOT']) if os.environ.get('TRAVEL_ACCEPTANCE_ROOT') else Path(tempfile.mkdtemp(prefix='travel-platform-live-'))
def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
bp,ap=port(),8847
for k,v in {'AI_LAB_HOME':str(root/'vault'),'DATABASE_URL':'sqlite+aiosqlite:///'+str(root/'db.sqlite'),'AUTHEN_JWT_SECRET':'travel-platform-test','HERMES_TENANT_SANDBOX_ROOT':str(root/'sandboxes'),'HERMES_TEMPLATE_SKILLS_DIR':str(root/'templates'),'HERMES_WORKFLOW_RUNS_FILE':str(root/'runs.json'),'HERMES_WORKFLOW_PLANNING_RUNS_FILE':str(root/'planning.json'),'HERMES_BRIDGE_INTERNAL_TOKEN':secrets.token_hex(24),'HERMES_CHAT_RUN_DB':str(root/'chat-runs.sqlite'),'HERMES_DURABLE_CHAT_WORKER':'true','CHAT_BLOCK_CURSOR_SECRET':secrets.token_hex(32),'KNOWLEDGE_CAPABILITY_SECRET':secrets.token_hex(32),'HERMES_BRIDGE_URL':f'http://127.0.0.1:{bp}/v1/chat','HERMES_BRIDGE_NOTE_ILLUSTRATION_URL':f'http://127.0.0.1:{bp}/v1/note-illustrations','KNOWLEDGE_GATEWAY_URL':f'http://127.0.0.1:{ap}/api/internal/knowledge/search'}.items():os.environ[k]=v
(root/'vault').mkdir(exist_ok=True)
from scripts import hermes_bridge as b
from scripts.chat_run_store import DurableChatRunStore
b.session_runtime._chat_run_store=DurableChatRunStore(root/"chat-runs.sqlite")
from backend.main import app
from backend.db import init_db,SessionLocal
from backend.services.workflow_planning import process_next_once
from backend.services.workflow_executor import sync_execution
from backend.services.travel_plan import validate_travel_document
import backend.api.auth as auth
from backend.api.agreement import require_current_agreement
from fastapi import Depends
import uvicorn,httpx,jwt
from datetime import datetime,timezone,timedelta
async def owner(user):return {'tenant_key':'xFusion_MO_Tenant','is_super_admin':False,'categories':set()}
async def notadmin(user):return False
auth.tenant_resolver=owner;auth._is_super_admin=notadmin
async def accepted(payload=Depends(auth.require_auth)):return payload
app.dependency_overrides[require_current_agreement]=accepted
asyncio.run(init_db())
servers=[]
for application,p in [(app,ap),(b.app,bp)]:
 s=uvicorn.Server(uvicorn.Config(application,host='127.0.0.1',port=p,lifespan='off',log_level='error'));servers.append(s);threading.Thread(target=s.run,daemon=True).start()
 while not s.started:time.sleep(.02)
token=jwt.encode({'iss':'Unified Auth Platform','aud':'ai-lab-platform','token_use':'access','sub':'demo-user','principal_type':'human','amr':['test_interactive'],'exp':datetime.now(timezone.utc)+timedelta(hours=1)},'travel-platform-test',algorithm='HS256')

Path('/tmp/travel-full-client-config.json').write_text(json.dumps({'token':token,'port':ap,'root':str(root)}))
async def planning():
 while True:
  await process_next_once()
  await asyncio.sleep(1)
async def workers():
 from backend.services.workflow_executor import worker_loop
 await asyncio.gather(planning(),worker_loop(1))
worker_log=open(root/'durable-worker.log','w')
worker=subprocess.Popen([sys.executable,'-m','scripts.chat_run_worker'],stdout=worker_log,stderr=subprocess.STDOUT)
print('READY full client local server',flush=True)
try:asyncio.run(workers())
finally:
 for s in servers:s.should_exit=True
 worker.terminate();worker.wait(timeout=10);worker_log.close()
