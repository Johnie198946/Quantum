import os,time,json,uuid,statistics,math,concurrent.futures
from pathlib import Path
import httpx
base='http://'+os.environ['HERMES_BRIDGE_BIND_ADDRESS']+':9118'
headers={'X-Hermes-Internal-Token':os.environ['HERMES_BRIDGE_INTERNAL_TOKEN'],'X-Tenant-ID':'travel-release-acceptance','X-User-ID':'travel-release-check'}
root=Path('/var/lib/quantumn-hermes/.hermes/cache/travel-performance-20260927');root.mkdir(exist_ok=True)
rows=[]
def stats(xs):
 s=sorted(xs);return {'n':len(s),'p50_s':round(statistics.median(s),3),'p95_nearest_rank_s':round(s[math.ceil(.95*len(s))-1],3),'max_s':round(max(s),3)} if s else {'n':0}
def emit(r):
 rows.append(r);print(json.dumps(r,ensure_ascii=False),flush=True)
 (root/'clarification.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
def read(i):
 with httpx.Client(base_url=base,headers=headers,trust_env=False,timeout=15) as c:
  t=time.monotonic();r=c.get('/v1/workflow-runs/wfr_cloud_maps_671946da0bcc');r.raise_for_status()
  assert r.json()['status']=='awaiting_review'
  d=c.get('/v1/workflow-runs/wfr_cloud_maps_671946da0bcc',headers={'X-Hermes-Internal-Token':'invalid-acceptance-token'});assert d.status_code in (401,403)
  return time.monotonic()-t
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:times=list(pool.map(read,range(30)))
emit({'phase':'workflow_read_and_invalid_internal_token_deny','concurrency':4,'stats':stats(times),'failures':0})
def clarify(i):
 tenant='travel-perf-tenant-'+str(i%2)
 transcript=[{'role':'user','content':'想去日本安静温泉，不要热门地方。'},{'role':'assistant','content':'计划几月出发、几天？'},{'role':'user','content':'明年一月，五天，从上海出发。'}]
 if i%3==1: transcript.append({'role':'user','content':'两位成人，不自驾，每晚住宿预算人民币2500元，喜欢私汤。'})
 if i%3==2: transcript += [{'role':'user','content':'喜欢安静，不购物，希望留出两小时休息。'}]*9
 body={'tenant_id':tenant,'workflow_id':'perf-'+uuid.uuid4().hex,'goal':'日本小众温泉旅行，帮助收敛想法。样本 '+str(i),'transcript':transcript}
 t=time.monotonic()
 try:
  with httpx.Client(base_url=base,headers=headers,trust_env=False,timeout=75) as c:
   r=c.post('/v1/workflows/clarify',json=body);r.raise_for_status();v=r.json()
   assert v['truth']=='LIVE' and not v['simulation'] and v['status'] in ['question','READY']
   return {'phase':'clarification','sample':i,'concurrency':2,'transcript_messages':len(transcript),'elapsed_s':round(time.monotonic()-t,3),'status':'passed','decision':v['status'],'usage':v.get('usage',{})}
 except Exception as e:return {'phase':'clarification','sample':i,'elapsed_s':round(time.monotonic()-t,3),'status':'failed','error':str(e)[:240]}
for i in range(0,30,2):
 with httpx.Client(base_url=base,headers=headers,trust_env=False,timeout=10) as c: c.get('/health').raise_for_status()
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  for r in pool.map(clarify,[i,i+1]):emit(r)
 if sum(r.get('status')=='failed' for r in rows)>=3:raise RuntimeError('three_failures_stop_load')
 time.sleep(2.1)
values=[r['elapsed_s'] for r in rows if r.get('phase')=='clarification' and r.get('status')=='passed']
emit({'phase':'summary','clarification':stats(values),'failures':sum(r.get('status')=='failed' for r in rows),'target_p50_s':3,'target_p95_s':8,'scope':'production Bridge HTTP; 30 real model calls at concurrency 2; fixed test network; no UI/TTFT metric'})
