"""Run inside the deployed API container. Uses a separate short-lived acceptance identity."""
import base64,hashlib,io,json,os,time,uuid
import httpx,jwt
from PIL import Image
from backend.api.auth import AUTHEN_JWT_SECRET,AUTHEN_JWT_ISSUER,AUTHEN_JWT_AUDIENCE
from backend.api.agreement import CURRENT_AGREEMENT_VERSION
from pathlib import Path
fixture=json.loads(Path('/tmp/image-functional-fixture.json').read_text())
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
r=c.post('capabilities/proposals',json={'capability_id':'media.process','input':{'source_artifact_id':document['source_id'],'format':'jpg','aspect_ratio':'16:9'},'session_id':'image-release-'+fixture['release_sha'][:12],'request_id':str(uuid.uuid4()),'idempotency_key':str(uuid.uuid4())});r.raise_for_status();proposal=r.json();assert proposal['status']!='failed',proposal.get('error')
p=next(e['payload'] for e in proposal['events'] if 'proposal_id' in e.get('payload',{}));assert p['input']['format']=='jpg' and p['input']['aspect_ratio']=='16:9'
r=c.post('capabilities/confirm',json={'proposal_id':p['proposal_id'],'confirmation_token':p['confirmation_token'],'session_id':p['input']['source_client_session_id']});r.raise_for_status();confirmed=r.json();assert confirmed['status']=='completed',confirmed.get('error')
w=next(e['payload']['workflow']['id'] for e in confirmed['events'] if 'workflow' in e.get('payload',{}))
print(json.dumps({'release_sha':fixture['release_sha'],'upload_download':'passed','invalid_input_422':'passed','cross_owner_404':'passed','native_jpeg_download':'passed','native_jpeg_sha256':hashlib.sha256(native).hexdigest(),'dimensions':im.size,'document_original_and_private_note':'passed','document_image_workflow':'passed','pcm_confirm_workflow':'passed','workflow_id':w,'test_user':user,'model_calls':0,'scope':'server HTTP upload/download and PCM workflow creation; native processing separately verified on iPhone'}))
# Exercise the travel reference formats through the final deployed authenticated API.
formats=[('csv','text/csv',b'\xef\xbb\xbfname,address\nStation,Tokyo\n'),('json','application/json',b'{"data":"ordinary file","content_type":"reference","extracted_text":"not an OCR envelope"}'),('txt','text/plain',b'Private travel reference'),('md','text/markdown',b'# Travel\nPrivate reference')]
for ext,mime,data in formats:
 r=c.post('documents',content=data,headers={'Content-Type':mime,'X-File-Name':'reference.'+ext,'X-File-Opt-Out':'true'});r.raise_for_status();doc=r.json()
 assert doc['status']=='ready' and doc['note_id'] and doc['contribution_status']=='excluded'
 r=c.get('documents/'+doc['source_id']+'/download');r.raise_for_status();assert r.content==data
 text=c.get('documents/'+doc['source_id']+'/text');text.raise_for_status();assert text.text==data.decode('utf-8-sig').strip()
 assert other.get('documents/'+doc['source_id']+'/download').status_code==404
 print(json.dumps({'reference_format':ext,'original_and_text':'passed','private_note':'passed','cross_owner_404':'passed','shared_compile':'opted_out_for_smoke','model_calls':0}))
