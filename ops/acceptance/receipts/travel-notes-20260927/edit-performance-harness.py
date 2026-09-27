import json,time,statistics,math,uuid
from pathlib import Path
import httpx
c=json.load(open('/tmp/travel-client-test-config.json'))
path='/api/v1/workflow-executions/client-travel-execution'
with httpx.Client(base_url='http://127.0.0.1:8846',headers={'Authorization':'Bearer '+c['token']},timeout=20) as h:
 def latest():
  r=h.get(path+'/artifacts');r.raise_for_status()
  a=max(r.json(),key=lambda a:a.get('metadata',{}).get('travel_revision',0))
  r=h.get(path+'/artifacts/'+a['id']+'/content');r.raise_for_status()
  return a,json.loads(r.json()['content'])
 reads=[];saves=[]
 for i in range(20):
  t=time.monotonic();a,d=latest();reads.append(time.monotonic()-t)
  d['actions'][0]['title']='Performance round '+str(i)
  t=time.monotonic();r=h.post(path+'/travel-revisions',json={'artifact_id':a['id'],'expected_hash':a['content_hash'],'request_id':'perf-'+uuid.uuid4().hex,'reason':'synthetic local latency acceptance','proposed':d});r.raise_for_status();saves.append(time.monotonic()-t)
  saved=r.json();read=h.get(path+'/artifacts/'+saved['id']+'/content');read.raise_for_status();assert json.loads(read.json()['content'])['actions'][0]['title']==d['actions'][0]['title']
 def stats(values):
  a=sorted(values);return {'n':len(a),'p50_ms':round(statistics.median(a)*1000,2),'p95_nearest_rank_ms':round(a[math.ceil(.95*len(a))-1]*1000,2),'max_ms':round(max(a)*1000,2)}
 print(json.dumps({'scope':'actual loopback HTTP with isolated SQLite and synthetic owner; each read is artifacts list + content; save is revision POST, all saves read back; excludes WAN and UI overhead','reads':stats(reads),'saves':stats(saves),'status':'passed'}))
