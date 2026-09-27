import pathlib,subprocess,pwd,os
pid=subprocess.check_output(['systemctl','show','hermes-bridge.service','-p','MainPID','--value'],text=True).strip()
env=dict(x.split('=',1) for x in pathlib.Path('/proc/'+pid+'/environ').read_text().split('\0') if '=' in x)
u=pwd.getpwnam('quantumn-hermes')
code=r'''
import os,json,time,hashlib,uuid
from pathlib import Path
from types import SimpleNamespace
import httpx
from backend.services.knowledge_policy import KnowledgePolicy,mint_capability
from backend.services.travel_plan import build_travel_plan
root=Path('/var/lib/quantumn-hermes/.hermes/cache/travel-production-d228c06d');root.mkdir(parents=True,exist_ok=True)
tenant='travel-release-acceptance';user='travel-release-check'
run='wfr_cloud_maps_'+uuid.uuid4().hex[:12]
policy=KnowledgePolicy(tenant_key=tenant,org_id='',plan_id='',plan_status='active',wallet=frozenset(),entitled_yellow=frozenset(),effective_categories=frozenset(),policy_version='travel-acceptance-v1',entitlement_stale=False)
cap=mint_capability(policy,subject_id=run,entry_point='workflow',user_id=user,ttl_seconds=600)
goal='云端旅行验收：只查询 Google Maps 东京站的真实地址，以及东京站至新宿站 2026年9月28日当地日本时间09:00出发的公共交通。必须用服务器 browser_navigate 和 browser_snapshot；日期用网页 Depart at 控件确认。仅输出实际读到的站点地址、路线名称、出发/到达时间、时长与价格和来源链接；页面无法确认时明确缺口。不要搜索餐厅、酒店或其他地区，不使用私人收藏，不预约。'
plan=build_travel_plan(SimpleNamespace(requirements_snapshot={'scenario_id':'travel-planning'},title='云端 Maps 验收',description=goal),plan_id='maps-acceptance',knowledge_scope=[])
plan['nodes']=plan['nodes'][:1];plan['edges']=[]
body=dict(tenant_id=tenant,execution_id=run,idempotency_key=run,goal=goal,deliverable='Google Maps 实际地点与指定日期公交查询证据',plan=plan,allow_network=True,knowledge_scope=[],max_tokens=16000,knowledge_capability=cap,knowledge_policy_version=policy.policy_version,agent_config=dict(id='main_agent',allowed_tools=['web_search','web_extract','browser_navigate'],allow_network=True))
headers={'X-Hermes-Internal-Token':os.environ['HERMES_BRIDGE_INTERNAL_TOKEN'],'X-Tenant-ID':tenant,'X-User-ID':user}
base='http://'+os.environ.get('HERMES_BRIDGE_BIND_ADDRESS','172.17.0.1')+':9118'
with httpx.Client(base_url=base,headers=headers,trust_env=False,timeout=30) as c:
 start=time.monotonic();r=c.post('/v1/workflow-runs',json=body);r.raise_for_status();print('workflow_started',r.json(),flush=True)
 deadline=time.monotonic()+360
 while time.monotonic()<deadline:
  r=c.get('/v1/workflow-runs/'+run);r.raise_for_status();data=r.json()
  if data['status'] not in ('running','queued'):break
  time.sleep(3)
 (root/'workflow.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
 tools=sorted({e.get('tool') for e in data.get('events',[]) if e.get('tool')})
 print(json.dumps({'status':data['status'],'error':data.get('error'),'elapsed':round(time.monotonic()-start,2),'tools':tools,'nodes':data.get('nodes')},ensure_ascii=False),flush=True)
 assert data['status']=='awaiting_review',data.get('error')
 assert 'browser_navigate' in tools and 'browser_snapshot' in tools,tools
'''
r=subprocess.run(['/var/lib/quantumn-hermes/bridge-worker-venv/bin/python','-c',code],env=env,cwd='/opt/ai-lab-platform',user=u.pw_uid,group=u.pw_gid,timeout=650)
raise SystemExit(r.returncode)
