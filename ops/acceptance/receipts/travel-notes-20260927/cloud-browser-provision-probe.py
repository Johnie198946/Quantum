import os,pathlib,pwd,subprocess,tempfile,json
pid=subprocess.check_output(['systemctl','show','hermes-bridge.service','-p','MainPID','--value'],text=True).strip()
current=dict(x.split('=',1) for x in pathlib.Path('/proc/'+pid+'/environ').read_text().split('\0') if '=' in x)
u=pwd.getpwnam('quantumn-hermes')
root=pathlib.Path(tempfile.mkdtemp(prefix='travel-cloud-browser-'))
os.chown(root,u.pw_uid,u.pw_gid)
env={k:current[k] for k in ('HTTP_PROXY','HTTPS_PROXY','NO_PROXY','LANG') if k in current}
env.update(HOME=str(root),HERMES_HOME=str(root/'hermes'),PATH='/var/lib/quantumn-hermes/.hermes/node/bin:/usr/bin:/bin',PLAYWRIGHT_BROWSERS_PATH=str(root/'chromium'),XDG_CACHE_HOME=str(root/'cache'),npm_config_cache=str(root/'npm-cache'),AGENT_BROWSER_PROXY=current.get('HTTPS_PROXY',''))
print(json.dumps({'probe_root':str(root),'mode':'isolated_server_no_personal_profile'}),flush=True)
def run(argv,timeout=240):
 r=subprocess.run(argv,env=env,cwd=root,user=u.pw_uid,group=u.pw_gid,capture_output=True,text=True,timeout=timeout)
 print(json.dumps({'command':argv[:3],'code':r.returncode,'stdout':r.stdout[-3500:],'stderr':r.stderr[-1500:]}),flush=True)
 if r.returncode: raise SystemExit(r.returncode)
run(['npm','install','--prefix',str(root/'runtime'),'--ignore-scripts','--no-audit','--no-fund','agent-browser@0.26.0'])
binary=str(root/'runtime/node_modules/.bin/agent-browser')
run([binary,'--version'])
run([binary,'install'],timeout=480)
print(json.dumps({'ready_for_hermes_probe':str(root)}),flush=True)
