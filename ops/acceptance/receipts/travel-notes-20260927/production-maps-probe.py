import sys,json,time,uuid,statistics,math,re
from pathlib import Path
from scripts import hermes_bridge
sys.path.insert(0,'/var/lib/quantumn-hermes/.hermes/hermes-agent')
from tools.browser_tool import browser_navigate,browser_snapshot
from tools.browser_tool_lifecycle import cleanup_browser
root=Path('/var/lib/quantumn-hermes/.hermes/cache/travel-performance-20260927');root.mkdir(exist_ok=True)
rows=[]
url='https://www.google.com/maps/dir/?api=1&origin=Tokyo+Station&destination=Shinjuku+Station&travelmode=transit&hl=en'
for pair in range(15):
 task='travel-perf-'+uuid.uuid4().hex[:12]
 try:
  for state in ['cold','warm']:
   begin=time.monotonic()
   try:
    nav=json.loads(browser_navigate(url,task_id=task))
    if not nav.get('success'):raise RuntimeError(str(nav.get('error','navigation_failed'))[:160])
    page=''
    for attempt in range(5):
     snap=json.loads(browser_snapshot(task_id=task));page=snap.get('snapshot','')
     if 'Tokyo' in page and 'Shinjuku' in page and ('min' in page or 'Chūō' in page):break
     time.sleep(1)
    assert 'Tokyo' in page and 'Shinjuku' in page and ('min' in page or 'Chūō' in page),'route_facts_missing'
    result={'sample':len(rows),'state':state,'elapsed_s':round(time.monotonic()-begin,3),'status':'passed','snapshot_chars':len(page)}
   except Exception as e:result={'sample':len(rows),'state':state,'elapsed_s':round(time.monotonic()-begin,3),'status':'failed','error':str(e)[:240]}
   rows.append(result);print(json.dumps(result),flush=True);(root/'browser.json').write_text(json.dumps(rows,indent=2))
   if sum(r['status']=='failed' for r in rows)>=3:raise RuntimeError('three_failures_stop_load')
   time.sleep(2)
 finally:cleanup_browser(task_id=task)
def stats(items):
 a=sorted(x['elapsed_s'] for x in items if x['status']=='passed');return {'n':len(items),'successes':len(a),'failures':len(items)-len(a),'p50_s':round(statistics.median(a),3) if a else None,'p95_nearest_rank_s':a[math.ceil(.95*len(a))-1] if a else None}
print(json.dumps({'summary':stats(rows),'cold':stats([r for r in rows if r['state']=='cold']),'warm':stats([r for r in rows if r['state']=='warm']),'scope':'actual server native browser; public current transit; cold browser context/warm navigation; no model/UI/dated-route benchmark'}),flush=True)
