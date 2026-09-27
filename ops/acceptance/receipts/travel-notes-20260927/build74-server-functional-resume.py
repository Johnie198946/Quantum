"""Run inside the deployed API container. Uses a separate short-lived acceptance identity."""
import base64,hashlib,io,json,os,time,uuid
import httpx,jwt
from PIL import Image
from backend.api.auth import AUTHEN_JWT_SECRET,AUTHEN_JWT_ISSUER,AUTHEN_JWT_AUDIENCE
from backend.api.agreement import CURRENT_AGREEMENT_VERSION
from pathlib import Path
fixture=json.loads(Path('/tmp/image-functional-fixture-build74.json').read_text())
user='image-release-acceptance-'+fixture['release_sha'][:12]
def client(subject):
 token=jwt.encode({'sub':subject,'iss':AUTHEN_JWT_ISSUER,'aud':AUTHEN_JWT_AUDIENCE,'token_use':'access','is_super_admin':False,'exp':int(time.time())+600},AUTHEN_JWT_SECRET,algorithm='HS256')
 return httpx.Client(base_url='http://127.0.0.1:8000/api/v1/',headers={'Authorization':'Bearer '+token},timeout=60,trust_env=False)
c=client(user)
other=client(user+'-other')
raw=base64.b64decode(fixture['original']);native=base64.b64decode(fixture['native_jpeg'])
w='wf_dda24c8a8c6031d7e4247d57e98309f3'
execution='wfr_08d12e30414940bda49eab59beb4e8f4'
import asyncio
from sqlalchemy import select,text
from backend.db import SessionLocal
from backend.models.capability_gateway import ClientActionInvocation
from backend.models.workflow import WorkflowNodeRun, WorkflowArtifact
async def previous_action():
 async with SessionLocal() as db:
  await db.execute(text('SET TRANSACTION READ ONLY'))
  rows=list((await db.scalars(select(ClientActionInvocation).where(ClientActionInvocation.user_id==user))).all())
  rows=[r for r in rows if r.request_payload.get('execution_id')==execution]
  prior=[r for r in rows if r.state=='FAILED'];assert len(prior)==1
  cancelled=[r for r in rows if r.state=='CANCELLED'];assert len(cancelled)==1
  node=await db.scalar(select(WorkflowNodeRun).where(WorkflowNodeRun.execution_id==execution))
  assert node.attempt>=3,node.attempt
  a=prior[0];old=await db.get(WorkflowArtifact,a.request_payload['instruction_id'])
  print(json.dumps({'persisted_terminals':[r.state for r in rows],'node_attempt':node.attempt,'failed_instruction':old.id,'scope':'readonly synthetic owner'}),flush=True)
  return {'action_id':a.id,'payload':a.request_payload}
previous=asyncio.run(previous_action())
def await_action(previous_id=None):
 deadline=time.monotonic()+150
 while time.monotonic()<deadline:
  response=c.post('workflow-executions/'+execution+'/image-action')
  if response.status_code==200:
   item=response.json()
   if item['action_id']!=previous_id:return item
  else:assert response.status_code==409,response.text
  time.sleep(1)
 raise AssertionError('new image action was not prepared within bounded wait')
action=await_action(previous['action_id'])
assert action['payload']['instruction_id']!=previous['payload']['instruction_id']
r=c.post('documents/images',content=native);r.raise_for_status();output=r.json()
r=c.post('capabilities/client-actions/'+previous['action_id']+'/receipt',json={'status':'SUCCEEDED','result_metadata':{'artifact_id':output['artifact_id']}});assert r.status_code==409
print(json.dumps({'terminal':'FAILED','retry_new_instruction_and_action':'passed','stale_success_receipt_409':'passed','execution_id':execution,'continued_after_external_restart':True}),flush=True)
r=c.post('capabilities/client-actions/'+action['action_id']+'/receipt',json={'status':'SUCCEEDED','result_metadata':{'artifact_id':output['artifact_id']}});r.raise_for_status();assert r.json()['state']=='SUCCEEDED'
r=c.get('workflows/'+w);r.raise_for_status();assert r.json()['latest_execution']['status']=='completed',r.text
r=c.get('workflow-executions/'+execution+'/artifacts');r.raise_for_status()
outputs=[a for a in r.json() if a['source_kind']=='ios_native'];assert len(outputs)==1
url='workflow-executions/'+execution+'/artifacts/'+outputs[0]['id']+'/download'
r=c.get(url);r.raise_for_status();assert r.content==native
assert other.get(url).status_code==404
print(json.dumps({'new_receipt_succeeded':'passed','execution_completed':'passed','final_download_hash':hashlib.sha256(r.content).hexdigest(),'execution_id':execution,'scope':'synthetic owner only; fixture native result; no deletion'}),flush=True)
