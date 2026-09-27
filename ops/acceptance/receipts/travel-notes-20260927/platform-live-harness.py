from importlib.metadata import version
assert version("openai") == "2.24.0", "Use requirements-bridge-worker.lock runtime (OpenAI 2.24.0)"
import os,tempfile,secrets,json,time,asyncio,threading,socket
from pathlib import Path
root=Path(tempfile.mkdtemp(prefix='travel-platform-live-'))
def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
bp,ap=port(),port()
for k,v in {'AI_LAB_HOME':str(root/'vault'),'DATABASE_URL':'sqlite+aiosqlite:///'+str(root/'db.sqlite'),'AUTHEN_JWT_SECRET':'travel-platform-test','HERMES_TENANT_SANDBOX_ROOT':str(root/'sandboxes'),'HERMES_TEMPLATE_SKILLS_DIR':str(root/'templates'),'HERMES_WORKFLOW_RUNS_FILE':str(root/'runs.json'),'HERMES_WORKFLOW_PLANNING_RUNS_FILE':str(root/'planning.json'),'HERMES_BRIDGE_INTERNAL_TOKEN':secrets.token_hex(24),'KNOWLEDGE_CAPABILITY_SECRET':secrets.token_hex(32),'HERMES_BRIDGE_URL':f'http://127.0.0.1:{bp}/v1/chat','KNOWLEDGE_GATEWAY_URL':f'http://127.0.0.1:{ap}/api/internal/knowledge/search'}.items():os.environ[k]=v
(root/'vault').mkdir()
from scripts import hermes_bridge as b
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
async def owner(user):return {'tenant_key':'travel-platform','is_super_admin':False,'categories':set()}
async def notadmin(user):return False
auth.tenant_resolver=owner;auth._is_super_admin=notadmin
async def accepted(payload=Depends(auth.require_auth)):return payload
app.dependency_overrides[require_current_agreement]=accepted
asyncio.run(init_db())
servers=[]
for application,p in [(app,ap),(b.app,bp)]:
 s=uvicorn.Server(uvicorn.Config(application,host='127.0.0.1',port=p,lifespan='off',log_level='error'));servers.append(s);threading.Thread(target=s.run,daemon=True).start()
 while not s.started:time.sleep(.02)
token=jwt.encode({'iss':'Unified Auth Platform','aud':'ai-lab-platform','token_use':'access','sub':'test-user','principal_type':'human','amr':['test_interactive'],'exp':datetime.now(timezone.utc)+timedelta(hours=1)},'travel-platform-test',algorithm='HS256')
async def main():
 start=time.monotonic()
 async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{ap}',headers={'Authorization':'Bearer '+token},timeout=90) as c:
  async def call(method,path,body=None):
   r=await c.request(method,'/api/v1/'+path,json=body);assert r.status_code<300,(path,r.status_code,r.text);return r.json()
  goal='2030年1月3日日本一日安静温泉旅行。仅查日本秘汤守护协会官网和一个候选区域，最多3个事项，两小时休息，未知地址和时间留空，不预约，不查询账号。'
  w=await call('POST','workflows',{'title':'旅行完整平台验收','description':goal,'output_kind':'travel'});wid=w['workflow']['id'];base='workflows/'+wid
  for answer in ['2030年1月3日，一人，不确定城市','温泉和放空，不去人多的地方','仅官方网页，不预约，最多3个安排，未知留空']:
   result=await call('POST',base+'/clarification/respond',{'response':answer})
  await call('POST',base+'/clarification/respond',{'intent':'confirm'})
  assert await process_next_once()
  plan=await call('GET',base+'/plan');print('platform plan '+plan['id'],flush=True)
  await call('POST',base+'/approve-plan',{'request_id':'platform-live-approve'})
  execution=await call('POST',base+'/start',{'request_id':'platform-live-start'});eid=execution['id'];path='workflow-executions/'+eid
  approved=False
  while time.monotonic()-start<600:
   async with SessionLocal() as db:await sync_execution(eid,db)
   status=await call('GET',path)
   if status['status']=='failed':raise AssertionError(status)
   if status['status']=='awaiting_approval':
    arts=await call('GET',path+'/artifacts');a=next(a for a in arts if a.get('metadata',{}).get('approval_gate'))
    body=await call('GET',path+'/artifacts/'+a['id']+'/content');validate_travel_document(json.loads(body['content']))
    await call('POST',path+'/review-stage',{'artifact_id':a['id'],'expected_hash':a['content_hash'],'artifact_version':a['metadata']['artifact_version'],'decision':'approve','comment':'接受测试行程'})
    approved=True;print('platform gate approved',flush=True)
   if status['status']=='awaiting_review':break
   await asyncio.sleep(1)
  assert status['status']=='awaiting_review',status
  arts=await call('GET',path+'/artifacts');a=next(a for a in arts if a.get('metadata',{}).get('render_type')=='travel_plan_v2' and not a.get('metadata',{}).get('approval_gate'))
  body=await call('GET',path+'/artifacts/'+a['id']+'/content');doc=validate_travel_document(json.loads(body['content']))
  assert approved
  print(json.dumps({'status':'passed','elapsed_seconds':round(time.monotonic()-start,2),'root':str(root),'actions':len(doc['actions']),'scope':'actual platform HTTP clarification + planning + approve + start + dispatch + real Hermes research + stage approval + persisted notebook readback; isolated synthetic auth; no iOS'},ensure_ascii=False),flush=True)
try:asyncio.run(main())
finally:
 for s in servers:s.should_exit=True
