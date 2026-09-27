import json,time,statistics,math,uuid
from pathlib import Path
import httpx
c=json.loads(Path('/tmp/travel-perf-client-config.json').read_text())
base='/api/v1/workflow-executions/client-travel-execution'
rows=[]
with httpx.Client(base_url='http://127.0.0.1:8856',headers={'Authorization':'Bearer '+c['token']},timeout=15) as h:
 def artifacts():
  r=h.get(base+'/artifacts');r.raise_for_status();return r.json()
 def latest():
  a=max(artifacts(),key=lambda x:x.get('metadata',{}).get('travel_revision',0))
  r=h.get(base+'/artifacts/'+a['id']+'/content');r.raise_for_status();return a,json.loads(r.json()['content'])
 for mode,delay,lose in [('baseline',0,False),('slow_response',.35,False),('lost_response_retry',.35,True)]:
  for i in range(30):
   a,d=latest();before=len(artifacts());title=mode+'-'+str(i);d['actions'][0]['title']=title
   payload={'artifact_id':a['id'],'expected_hash':a['content_hash'],'request_id':'perf-'+uuid.uuid4().hex,'reason':'isolated synthetic weak network acceptance','proposed':d}
   headers={'X-Acceptance-Delay':str(delay),'X-Acceptance-Lose-Response':'1' if lose else '0'}
   start=time.monotonic();r=h.post(base+'/travel-revisions',json=payload,headers=headers)
   if lose:
    assert r.status_code==503,r.text
    r=h.post(base+'/travel-revisions',json=payload,headers={'X-Acceptance-Delay':str(delay)})
   r.raise_for_status();elapsed=time.monotonic()-start;receipt=r.json()
   recovered,document=latest()
   assert receipt['id']==recovered['id'] and document['actions'][0]['title']==title
   assert document['journal']==d['journal'] and document['actions'][0]['start']==d['actions'][0]['start']
   assert len(artifacts())==before+1,'retry created extra version'
   old=h.get(base+'/artifacts/'+a['id']+'/content');old.raise_for_status()
   assert json.loads(old.json()['content'])['actions'][0]['title']!=title,'historical version mutated'
   row={'mode':mode,'sample':i,'elapsed_s':round(elapsed,4),'passed':True,'versions_added':1}
   rows.append(row);print(json.dumps(row),flush=True)
 for mode in ('baseline','slow_response','lost_response_retry'):
  v=sorted(r['elapsed_s'] for r in rows if r['mode']==mode)
  print(json.dumps({'summary':mode,'n':len(v),'p50_s':round(statistics.median(v),4),'p95_s':v[math.ceil(.95*len(v))-1],'max_s':max(v),'failures':0,'scope':'loopback real API/SQLite; deterministic server delay/lost-response injection; excludes actual mobile radio/WAN/UI'}),flush=True)
