import subprocess,json,hashlib,sqlite3,urllib.request
from pathlib import Path
expected='d228c06d6865bdbca9329f264acfe4cf0e8fc5f7'
release=Path('/opt/ai-lab-platform').resolve()
assert (release/'.deployed-sha').read_text().strip()==expected
print('release',release,'sha',expected)
for name in ['api','workflow-worker','planning-worker','agent-evaluation-worker','frontend','taskboard','postgres','redis']:
 x=json.loads(subprocess.check_output(['docker','inspect',f'ai-lab-platform-{name}-1']))[0]
 health=x['State'].get('Health',{}).get('Status');assert x['State']['Running'] and health=='healthy',(name,health)
 rev=x['Config']['Labels'].get('org.opencontainers.image.revision')
 if name in ['api','workflow-worker','planning-worker','agent-evaluation-worker']:assert rev==expected,(name,rev)
 quota=[v for v in x['Config']['Env'] if v.startswith('QUANTUM_MONTHLY_TOKEN_LIMIT=')]
 print(json.dumps({'service':name,'health':health,'revision':rev,'quota':quota}))
for service in ['hermes-bridge.service','hermes-chat-worker.service']:
 assert subprocess.check_output(['systemctl','is-active',service],text=True).strip()=='active'
 pid=subprocess.check_output(['systemctl','show',service,'-p','MainPID','--value'],text=True).strip()
 env=dict(v.split('=',1) for v in Path('/proc/'+pid+'/environ').read_text().split('\0') if '=' in v)
 print(service,'active','quota',env.get('QUANTUM_MONTHLY_TOKEN_LIMIT','unset'))
 if service=='hermes-bridge.service':bridge='http://'+env['HERMES_BRIDGE_BIND_ADDRESS']+':9118/health'
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for url in ['http://127.0.0.1:8000/ready',bridge,'https://t-react.com/health']:
 with opener.open(url,timeout=20) as r: print('health',url,r.status,r.read().decode()[:1000])
backup=Path('/opt/ai-lab-shared/rollbacks/chat-travel-pcm-d228c06d6865')
for basename in ['database-before','publication-before','publication-files-before']:
 line=(backup/(basename+'.sha256')).read_text();digest,path=line.strip().split(None,1)
 actual=hashlib.sha256(Path(path.strip()).read_bytes()).hexdigest();assert digest==actual
 print('backup_hash',basename,digest)
with sqlite3.connect((backup/'publication-before.sqlite3').as_uri()+'?mode=ro',uri=True) as db:assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
root=release/'data/runtime/publications'
with sqlite3.connect((root/'publication.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
 db.row_factory=sqlite3.Row
 rows=db.execute('SELECT * FROM editions WHERE publication_id=?',('publication-6d65e4fff6f4ae7734d1585c3a05a80a',)).fetchall();assert len(rows)==1
 r=dict(rows[0]);bundle=json.loads(r['bundle_json']);plan=bundle['illustration_plan']
 digest=hashlib.sha256((root/r['body_ref']).read_bytes()).hexdigest()
 assert digest==r['content_hash']==plan['body_sha256']=='076cbb867c99609ea8ff09322ffcdf5f391990a6df7960c7f708f6776d5c5c9f'
 assert r['state']=='staged' and r['actual_release_at'] is None
 print('publication',json.dumps({'count':len(rows),'state':r['state'],'release_at':r['release_at'],'actual_release_at':r['actual_release_at'],'body_sha256':digest,'plan_keys':list(plan)}))
print('joint_verification=passed')
