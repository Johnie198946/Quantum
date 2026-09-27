import os,time,json,uuid,statistics,math,hashlib,concurrent.futures
from pathlib import Path
from datetime import datetime,timezone
from types import SimpleNamespace
import httpx
from backend.services.knowledge_policy import KnowledgePolicy,mint_capability
from backend.services.travel_plan import build_travel_plan,validate_travel_document
base='http://'+os.environ['HERMES_BRIDGE_BIND_ADDRESS']+':9118'
headers={'X-Hermes-Internal-Token':os.environ['HERMES_BRIDGE_INTERNAL_TOKEN']}
root=Path('/var/lib/quantumn-hermes/.hermes/cache/travel-performance-20260927');root.mkdir(exist_ok=True)
rows=[]
def sample(i):
 tenant='travel-draft-perf-'+str(i%2);user='travel-perf-user-'+str(i%2);run='wfr_draftperf_'+uuid.uuid4().hex[:16]
 policy=KnowledgePolicy(tenant_key=tenant,org_id='',plan_id='',plan_status='active',wallet=frozenset(),entitled_yellow=frozenset(),effective_categories=frozenset(),policy_version='travel-acceptance-v1',entitlement_stale=False)
 cap=mint_capability(policy,subject_id=run,entry_point='workflow',user_id=user,ttl_seconds=600)
 marker='PRIVATE-'+uuid.uuid4().hex[:8]
 document={'schema_version':2,'destination':'日本','stops':[{'id':'hotel','name':'用户已定旅馆','address':'用户附件地址','latitude':35.68,'longitude':139.76}], 'actions':[{'id':'rest','day_id':'day-1','title':'温泉休息','kind':'rest','place_id':'hotel','start':'2030-01-03T10:00:00+09:00','end':'2030-01-03T12:00:00+09:00','timezone':'Asia/Tokyo','status':'planned'}],'journal':marker,'sources':[]}
 text=json.dumps(document,ensure_ascii=False)
 goal='局部行程草案验收：已有确认行程见附件。只将rest标题改为安静泡汤，其他字段原样保留，尤其journal。不得搜索、新增活动或来源；只输出完整JSON。'
 plan=build_travel_plan(SimpleNamespace(requirements_snapshot={'scenario_id':'travel-planning'},title='局部草案性能验收',description=goal),plan_id=run,knowledge_scope=[])
 node=plan['nodes'][1];node['parameters'].pop('approval_gate');node['parameters']['allow_network']=False;node['parameters']['max_tokens']=3000
 plan['nodes']=[node];plan['edges']=[]
 body=dict(tenant_id=tenant,execution_id=run,idempotency_key=run,goal=goal,deliverable='仅修改标题的旅行JSON',plan=plan,allow_network=False,knowledge_scope=[],max_tokens=6000,knowledge_capability=cap,knowledge_policy_version=policy.policy_version,agent_config=dict(id='main_agent',allowed_tools=[],allow_network=False),source_document=dict(source_id='doc_'+uuid.uuid4().hex,source_revision=1,content_hash=hashlib.sha256(text.encode()).hexdigest(),filename='confirmed-itinerary.json',content_type='application/json',text=text))
 start=time.monotonic()
 try:
  with httpx.Client(base_url=base,headers=headers,trust_env=False,timeout=30) as c:
   r=c.post('/v1/workflow-runs',json=body);r.raise_for_status();ack=time.monotonic()-start
   deadline=time.monotonic()+180
   while time.monotonic()<deadline:
    r=c.get('/v1/workflow-runs/'+run);r.raise_for_status();data=r.json()
    if data['status'] not in ('queued','running'):break
    time.sleep(.5)
   if data['status'] in ('running','queued'):c.post('/v1/workflow-runs/'+run+'/cancel')
   assert data['status']=='awaiting_review',str(data.get('error') or data['status'])
   output=validate_travel_document(json.loads(data['nodes']['travel_itinerary']['output']))
   assert len(output['actions'])==1 and output['actions'][0]['id']=='rest' and output['actions'][0]['title']=='安静泡汤'
   assert output['journal']==marker
   assert datetime.fromisoformat(output['actions'][0]['start'].replace('Z','+00:00'))==datetime.fromisoformat(document['actions'][0]['start'])
   assert not any(e.get('type')=='tool_start' for e in data.get('events',[]))
   return {'sample':i,'execution_id':run,'status':'passed','ack_s':round(ack,3),'elapsed_s':round(time.monotonic()-start,3),'usage':data.get('usage',{}),'private_marker_preserved':True,'external_calls':0}
 except Exception as e:return {'sample':i,'execution_id':run,'status':'failed','elapsed_s':round(time.monotonic()-start,3),'error':str(e)[:300]}
for i in range(0,30,2):
 if datetime.now(timezone.utc)>=datetime(2026,9,27,11,31,tzinfo=timezone.utc):raise RuntimeError("publication_window_stop")
 with httpx.Client(base_url=base,headers=headers,trust_env=False,timeout=10) as c:c.get('/health').raise_for_status()
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  for r in pool.map(sample,[i,i+1]):
   rows.append(r);print(json.dumps(r,ensure_ascii=False),flush=True);(root/'itinerary.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
 if sum(r['status']=='failed' for r in rows)>=3:raise RuntimeError('three_failures_stop_load')
 time.sleep(2)
def stats(key):
 a=sorted(r[key] for r in rows if r['status']=='passed');return {'n':len(a),'p50_s':round(statistics.median(a),3),'p95_nearest_rank_s':a[math.ceil(.95*len(a))-1],'max_s':max(a)} if a else {'n':0}
print(json.dumps({'summary':'completed','samples':len(rows),'failures':sum(r['status']=='failed' for r in rows),'ack':stats('ack_s'),'draft':stats('elapsed_s'),'target_draft_p50_s':5,'target_draft_p95_s':15,'scope':'production Bridge, concurrency2, independent user-scoped model sessions, supplied itinerary only, excludes client/WAN'}),flush=True)
