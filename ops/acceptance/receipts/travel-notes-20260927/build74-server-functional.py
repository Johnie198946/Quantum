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
r=c.put('me/agreement-acceptance',json={'agreement_version':CURRENT_AGREEMENT_VERSION,'idempotency_key':str(uuid.uuid4()),'source':'ios'});r.raise_for_status()
raw=base64.b64decode(fixture['original']);native=base64.b64decode(fixture['native_jpeg'])
r=c.post('documents/images',content=raw);r.raise_for_status();source=r.json()
r=c.get(source['download_path']);r.raise_for_status();assert r.content==raw
bad=c.post('documents/images',content=b'not-an-image');assert bad.status_code==422
r=c.post('documents/images',content=native);r.raise_for_status();output=r.json()
r=c.get(output['download_path']);r.raise_for_status();assert r.content==native
im=Image.open(io.BytesIO(r.content));assert im.format=='JPEG' and im.size==(656,369)
other=client(user+'-other');r=other.put('me/agreement-acceptance',json={'agreement_version':CURRENT_AGREEMENT_VERSION,'idempotency_key':str(uuid.uuid4()),'source':'ios'});r.raise_for_status();assert other.get(source['download_path']).status_code==404
# Reuse a single private document original for the photo-upload contract.
# Opt out of shared compilation so this smoke check does not start a model run.
r=c.post('documents',headers={'X-File-Name':'acceptance.png','X-File-Opt-Out':'true'},json={'data':fixture['original'],'content_type':'image/png','extracted_text':'Synthetic acceptance fixture text'})
r.raise_for_status();document=r.json();assert document['status']=='ready' and document['note_id']==document['source_id'];assert document['contribution_status']=='excluded'
r=c.get('documents/'+document['source_id']+'/download');r.raise_for_status();assert r.content==raw
assert other.get('documents/'+document['source_id']+'/download').status_code==404
invocation={'capability_id':'media.process','input':{'source_artifact_id':document['source_id'],'format':'jpg','aspect_ratio':'16:9','source_client_session_id':'image-release-'+fixture['release_sha'][:12]},'idempotency_key':'image-release-'+uuid.uuid4().hex}
r=c.post('capabilities/invoke',json=invocation);r.raise_for_status();result=r.json();assert result['status']=='completed',result.get('error')
assert not any(e['type']=='capability.proposal' for e in result['events'])
workflow=next(e['payload']['workflow'] for e in result['events'] if e['type']=='workflow.created')
w=workflow['id'];execution=workflow['latest_execution']['id'];assert execution
r=c.post('capabilities/invoke',json=invocation);r.raise_for_status();replay=r.json();assert replay['status']=='completed',replay.get('error')
repeated=next(e['payload']['workflow'] for e in replay['events'] if e['type']=='workflow.created')
assert repeated['id']==w and repeated['latest_execution']['id']==execution
# Read only the deletion contract; do not create or execute a delete proposal.
r=c.get('capabilities/knowledge.note.trash');r.raise_for_status();assert r.json()['confirmation']=='required'
print(json.dumps({'release_sha':fixture['release_sha'],'upload_download':'passed','invalid_input_422':'passed','cross_owner_404':'passed','native_jpeg_download':'passed','native_jpeg_sha256':hashlib.sha256(native).hexdigest(),'dimensions':im.size,'document_original_and_private_note':'passed','document_image_workflow':'passed','pcm_direct_workflow_and_replay':'passed','note_delete_confirmation_contract':'required','workflow_id':w,'test_user':user,'model_calls':0,'scope':'server HTTP upload/download and PCM workflow creation; native processing separately verified on iPhone'}))
# Exercise the travel reference formats through the final deployed authenticated API.
formats=[('csv','text/csv',b'\xef\xbb\xbfname,address\nStation,Tokyo\n'),('json','application/json',b'{"data":"ordinary file","content_type":"reference","extracted_text":"not an OCR envelope"}'),('txt','text/plain',b'Private travel reference'),('md','text/markdown',b'# Travel\nPrivate reference')]
for ext,mime,data in formats:
 r=c.post('documents',content=data,headers={'Content-Type':mime,'X-File-Name':'reference.'+ext,'X-File-Opt-Out':'true'});r.raise_for_status();doc=r.json()
 assert doc['status']=='ready' and doc['note_id'] and doc['contribution_status']=='excluded'
 r=c.get('documents/'+doc['source_id']+'/download');r.raise_for_status();assert r.content==data
 text=c.get('documents/'+doc['source_id']+'/text');text.raise_for_status();assert text.text==data.decode('utf-8-sig').strip()
 assert other.get('documents/'+doc['source_id']+'/download').status_code==404
 print(json.dumps({'reference_format':ext,'original_and_text':'passed','private_note':'passed','cross_owner_404':'passed','shared_compile':'opted_out_for_smoke','model_calls':0}))

# Only this synthetic execution is cancelled and retried. No real user's workflow is touched.
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
action=await_action()
for terminal in ('CANCELLED','FAILED'):
 previous=action
 r=c.post('capabilities/client-actions/'+previous['action_id']+'/receipt',json={'status':terminal,'result_metadata':{}});r.raise_for_status();assert r.json()['state']==terminal
 r=c.post('workflow-executions/'+execution+'/retry');r.raise_for_status();assert r.json()['status']=='queued'
 action=await_action(previous['action_id'])
 assert action['payload']['instruction_id']!=previous['payload']['instruction_id']
 r=c.post('capabilities/client-actions/'+previous['action_id']+'/receipt',json={'status':'SUCCEEDED','result_metadata':{'artifact_id':output['artifact_id']}});assert r.status_code==409
 print(json.dumps({'terminal':terminal,'retry_new_instruction_and_action':'passed','stale_success_receipt_409':'passed','execution_id':execution}),flush=True)
r=c.post('capabilities/client-actions/'+action['action_id']+'/receipt',json={'status':'SUCCEEDED','result_metadata':{'artifact_id':output['artifact_id']}});r.raise_for_status();assert r.json()['state']=='SUCCEEDED'
r=c.get('workflows/'+w);r.raise_for_status();assert r.json()['latest_execution']['status']=='completed',r.text
r=c.get('workflow-executions/'+execution+'/artifacts');r.raise_for_status()
outputs=[a for a in r.json() if a['source_kind']=='ios_native'];assert len(outputs)==1
url='workflow-executions/'+execution+'/artifacts/'+outputs[0]['id']+'/download'
r=c.get(url);r.raise_for_status();assert r.content==native
assert other.get(url).status_code==404
print(json.dumps({'new_receipt_succeeded':'passed','execution_completed':'passed','final_download_hash':hashlib.sha256(r.content).hexdigest(),'execution_id':execution,'scope':'synthetic owner only; fixture native result; no deletion'}),flush=True)
