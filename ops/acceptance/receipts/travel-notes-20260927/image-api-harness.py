import asyncio, hashlib, io, json, time, uuid
from pathlib import Path
import httpx, jwt
from PIL import Image
from datetime import datetime, timezone, timedelta
async def main():
 c=json.loads(Path('/tmp/travel-full-client-config.json').read_text());started=time.monotonic()
 content=json.dumps({'stops':[], 'photo_references':[{'anchor':'overview','image_url':'https://www.python.org/static/community_logos/python-logo.png','caption':'Public transport fixture, not travel photography'}]})
 body={'note_id':'acceptance-public-image','request_id':uuid.uuid4().hex,'title':'Public image API acceptance','content':content,'source_hash':hashlib.sha256(content.encode()).hexdigest(),'mode':'auto','travel':True}
 async with httpx.AsyncClient(base_url='http://127.0.0.1:8847/api/v1/me/knowledge-notes',headers={'Authorization':'Bearer '+c['token']},timeout=50) as client:
  r=await client.post('/illustrations/generate',json=body);assert r.status_code==202,r.text
  data=r.json();run=data['run_id']
  for _ in range(120):
   r=await client.get('/illustrations/'+run);assert r.status_code==200,r.text;data=r.json()
   if data['status'] in ('completed','failed','cancelled'):break
   await asyncio.sleep(1)
  assert data['status']=='completed',data
  assert len(data['assets'])==1,data
  asset=data['assets'][0];r=await client.get('/illustrations/'+run+'/assets/0');assert r.status_code==200,r.text
  assert hashlib.sha256(r.content).hexdigest()==asset['sha256']
  im=Image.open(io.BytesIO(r.content));assert im.format=='JPEG'
  other=jwt.encode({'iss':'Unified Auth Platform','aud':'ai-lab-platform','token_use':'access','sub':'other-acceptance-user','principal_type':'human','amr':['test_interactive'],'exp':datetime.now(timezone.utc)+timedelta(minutes=10)},'travel-platform-test',algorithm='HS256')
  denied=await client.get('/illustrations/'+run+'/assets/0',headers={'Authorization':'Bearer '+other});assert denied.status_code==404,denied.text
  print(json.dumps({'status':'passed','elapsed_seconds':round(time.monotonic()-started,2),'asset_count':len(data['assets']),'sha256':asset['sha256'],'bytes':len(r.content),'dimensions':im.size,'other_owner_status':denied.status_code,'scope':'actual platform API -> existing durable worker -> public download -> private media readback; Python logo is transport fixture, not travel photography'}))
asyncio.run(main())
