import os,tempfile,asyncio,json,secrets
from pathlib import Path
root=Path(tempfile.mkdtemp(prefix='travel-client-e2e-'))
os.environ['AI_LAB_HOME']=str(root/'vault');os.environ['DATABASE_URL']='sqlite+aiosqlite:///'+str(root/'database.sqlite');os.environ['AUTHEN_JWT_SECRET']='travel-local-test-secret'
from backend.main import app
from backend.db import init_db,SessionLocal
import backend.api.auth as auth
from backend.models.workflow import WorkflowDefinition,WorkflowPlanVersion,WorkflowExecution,WorkflowNodeRun
from backend.services.workflow_artifacts import store_artifact
from fastapi import Response
import uvicorn,jwt,httpx
from datetime import datetime,timezone,timedelta
async def owner(user):return {'tenant_key':'xFusion_MO_Tenant','is_super_admin':False,'categories':set()}
async def not_admin(user):return False
auth.tenant_resolver=owner;auth._is_super_admin=not_admin
from backend.api.agreement import require_current_agreement
from fastapi import Depends
async def accepted_fixture(payload=Depends(auth.require_auth)):return payload
app.dependency_overrides[require_current_agreement]=accepted_fixture

token=jwt.encode({'iss':'Unified Auth Platform','aud':'ai-lab-platform','token_use':'access','sub':'demo-user','principal_type':'human','amr':['test_interactive'],'exp':datetime.now(timezone.utc)+timedelta(hours=4)},'travel-local-test-secret',algorithm='HS256')
async def seed():
 await init_db()
 async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://local',headers={'Authorization':'Bearer '+token}) as c:
  r=await c.post('/api/v1/workflows',json={'title':'旅行客户端验收','description':'验证离线修改与十轮行程编辑','output_kind':'travel'})
  assert r.status_code==201,r.text
  wid=r.json()['workflow']['id']
 async with SessionLocal() as db:
  workflow=await db.get(WorkflowDefinition,wid);workflow.status='ready'
  plan=WorkflowPlanVersion(id='client-travel-plan',workflow_id=wid,version=1,dsl={'nodes':[],'edges':[]},goal='test trip',deliverable='travel')
  db.add(plan);await db.flush()
  execution=WorkflowExecution(id='client-travel-execution',workflow_id=wid,plan_id=plan.id,tenant_key='xFusion_MO_Tenant',status='completed',idempotency_key='client-travel-start')
  db.add(execution);await db.flush()
  node=WorkflowNodeRun(id='client-travel-node',execution_id=execution.id,node_id='travel_notebook',node_type='OUTPUT_FORMAT',name='旅行笔记',status='succeeded',position=0)
  db.add(node);await db.flush()
  document={'schema_version':2,'destination':'日本','stops':[{'id':'hotel','name':'测试旅馆','address':'测试地址','latitude':35.68,'longitude':139.76}], 'actions':[{'id':'rest','day_id':'day-1','title':'温泉休息','kind':'rest','place_id':'hotel','start':'2030-01-03T10:00:00+09:00','end':'2030-01-03T12:00:00+09:00','timezone':'Asia/Tokyo','status':'planned'}],'journal':'我的旅行手记','sources':[]}
  artifact=store_artifact(execution,node_run_id=node.id,kind='output',title='旅行笔记',content=json.dumps(document,ensure_ascii=False),extension='json',metadata={'render_type':'travel_plan_v2','travel_revision':0})
  db.add(artifact);await db.commit()
  Path('/tmp/travel-perf-client-config.json').write_text(json.dumps({'token':token,'artifact_id':artifact.id,'workflow_id':wid,'root':str(root)}))
@app.post('/__acceptance/network/{state}')
async def network(state:str):
 app.state.travel_offline=state=='offline';return {'offline':app.state.travel_offline}
@app.middleware('http')
async def offline(request,call_next):
 if getattr(app.state,'travel_offline',False) and not request.url.path.startswith('/__acceptance'):
  return Response('test network outage',status_code=503)
 delay = min(float(request.headers.get('X-Acceptance-Delay', '0')), 2)
 if delay: await asyncio.sleep(delay)
 response = await call_next(request)
 if request.headers.get('X-Acceptance-Lose-Response') == '1' and request.method == 'POST' and response.status_code < 300:
  return Response('injected lost response after successful commit',status_code=503)
 return response
asyncio.run(seed())
print('READY local travel acceptance on 8856',flush=True)
uvicorn.run(app,host='127.0.0.1',port=8856,lifespan='off',log_level='warning')
