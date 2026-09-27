import os,pathlib,pwd,subprocess,json
pid=subprocess.check_output(['systemctl','show','hermes-bridge.service','-p','MainPID','--value'],text=True).strip()
current=dict(x.split('=',1) for x in pathlib.Path('/proc/'+pid+'/environ').read_text().split('\0') if '=' in x)
u=pwd.getpwnam('quantumn-hermes'); root=pathlib.Path('/tmp/travel-cloud-browser-r3pqziwo')
env={k:current[k] for k in ('HTTP_PROXY','HTTPS_PROXY','NO_PROXY','LANG') if k in current}
env.update(HOME=str(root),HERMES_HOME=str(root/'hermes'),PATH=str(root/'runtime/node_modules/.bin')+':/var/lib/quantumn-hermes/.hermes/node/bin:/usr/bin:/bin',AGENT_BROWSER_EXECUTABLE_PATH=str(root/'.agent-browser/browsers/chrome-154.0.8037.57/chrome'),AGENT_BROWSER_PROXY=current.get('HTTPS_PROXY',''),HERMES_BROWSER_TIMEOUT='25',LD_LIBRARY_PATH=str(root/'libs/usr/lib/x86_64-linux-gnu'))
code='''import sys,json,time
sys.path.insert(0,"/var/lib/quantumn-hermes/.hermes/hermes-agent")
from tools.browser_tool import browser_navigate,browser_snapshot,cleanup_browser
from tools.browser_tool_install import check_browser_requirements
print("requirements",check_browser_requirements(),flush=True)
task="travel-maps-cloud-acceptance"
try:
 for url in ("https://www.google.com/maps/search/?api=1&query=Tokyo+Station&hl=en", "https://www.google.com/maps/dir/?api=1&origin=Tokyo+Station&destination=Shinjuku+Station&travelmode=transit&hl=en"):
  t=time.monotonic(); result=browser_navigate(url,task_id=task); print("navigate",result,flush=True)
  snap=browser_snapshot(task_id=task); print("snapshot",snap,flush=True)
  print("seconds",round(time.monotonic()-t,2),flush=True)
finally: cleanup_browser(task_id=task)
'''
r=subprocess.run(['/var/lib/quantumn-hermes/bridge-worker-venv/bin/python','-c',code],env=env,cwd=root,user=u.pw_uid,group=u.pw_gid,timeout=110,capture_output=True,text=True)
(root/'maps-result.txt').write_text(r.stdout+'\n'+r.stderr)
print(r.stdout[-14000:]); print(r.stderr[-2000:]);print('exit',r.returncode)
