#!/usr/bin/env bash
set -euo pipefail
SHA=01161f7603d7b3bea0a0c082cbf67862e35bf066
BEFORE=a9c1bfe97ebb17a7c21ecfe47e43812b4e9cb07b
HASH=dbc7660b6bc39fa4cfb0d17b12241933b623ecb2f27b599c990f832505c37f38
OLD_IMAGE=sha256:969792a6912e16e8e7bf866d1bb057d899b91f8f87156c60f96c886004aacd46
CANDIDATE=ai-lab-platform-api:quansyn-01161f7603d7
umask 077
if [ "${QUANSYN_DEPLOY_LOCK_FD:-}" != "8" ]; then exec 8>/run/lock/ai-lab-platform-update.lock; fi
[ "$(readlink /proc/$$/fd/8)" = /run/lock/ai-lab-platform-update.lock ]
flock -n 8
[ "$(cat /opt/ai-lab-platform/.deployed-sha)" = "$BEFORE" ]
POINT=$(mktemp -d /opt/ai-lab-shared/rollbacks/quansyn-20261009.XXXXXX)
printf '%s\n' "$POINT" > /tmp/quansyn-20261009-point
readlink -f /opt/ai-lab-platform > "$POINT/release-before.txt"
printf '%s\n' "$BEFORE" > "$POINT/sha-before.txt"
cp -a /opt/ai-lab-shared/offline-images.attested "$POINT/offline-images.attested.before"
systemctl show system-authen.slice -p MemoryHigh -p MemoryMax -p MemorySwapMax > "$POINT/authen-before.txt"
python3 - "$POINT" "$OLD_IMAGE" <<'PY'
import sqlite3,json,subprocess,pathlib,sys
p=pathlib.Path(sys.argv[1]);rows=[]
for n in ['api','workflow-worker','planning-worker','agent-evaluation-worker','frontend']:
 c=json.loads(subprocess.check_output(['docker','inspect','ai-lab-platform-'+n+'-1']))[0]
 assert c['Image']==(sys.argv[2] if n!='frontend' else 'sha256:4acbdfcc0a24306ef110d793a68a60c7e4e1af9db2bbb8a8a8ad927ddc91a7ba'),n
 ref=c['Config']['Image'];assert ref=='ai-lab-platform-'+n+':offline'
 assert subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',ref],text=True).strip()==c['Image']
 rows.append(ref+' '+c['Image'])
(p/'images-before.txt').write_text('\n'.join(rows)+'\n')
with sqlite3.connect('file:/opt/ai-lab-platform/data/hermes_chat_runs.sqlite3?mode=ro',uri=True) as source:
 assert source.execute("SELECT COUNT(*) FROM chat_runs WHERE status IN ('running','queued','stalled')").fetchone()[0]==0,'active chat: wait'
 with sqlite3.connect(p/'chat-runs-before.sqlite3') as target:
  source.backup(target);assert target.execute('PRAGMA quick_check').fetchone()[0]=='ok'
print('rollback_point='+str(p))
PY
docker exec ai-lab-platform-postgres-1 sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$POINT/postgres-before.dump"
[ -s "$POINT/postgres-before.dump" ]
ARCHIVE=/opt/ai-lab-shared/offline-source/ai-lab-platform-$SHA.tar.gz
install -m 0600 /tmp/ai-lab-platform-$SHA.tar.gz "$ARCHIVE"
[ "$(sha256sum "$ARCHIVE" | cut -d' ' -f1)" = "$HASH" ]
STAGE=$(mktemp -d /opt/ai-lab-shared/offline-source/quansyn-stage.XXXXXX)
tar xzf "$ARCHIVE" --strip-components=1 -C "$STAGE"
CHANGED=0
cleanup() {
 rc=$?
 trap - EXIT
 if [ "$rc" != 0 ] && [ "$CHANGED" = 1 ] && [ "$(cat /opt/ai-lab-platform/.deployed-sha)" = "$BEFORE" ]; then
  while read -r ref image; do docker tag "$image" "$ref"; done < "$POINT/images-before.txt"
  cp -a "$POINT/offline-images.attested.before" /opt/ai-lab-shared/offline-images.attested
 fi
 rm -rf "$STAGE"
 exit "$rc"
}
trap cleanup EXIT
python3 - "$STAGE" "$SHA" <<'PY'
import pathlib,json,hashlib,sys,shutil,tarfile
r=pathlib.Path(sys.argv[1]);sha=sys.argv[2]
c=r/'image-context';c.mkdir()
for d in ['backend','config','scripts']:shutil.copytree(r/d,c/d)
(c/'Dockerfile').write_text('FROM sha256:969792a6912e16e8e7bf866d1bb057d899b91f8f87156c60f96c886004aacd46\nUSER root\nRUN rm -rf /app/backend /app/config /app/scripts\nCOPY backend /app/backend\nCOPY config /app/config\nCOPY scripts /app/scripts\nUSER ailab\nLABEL org.opencontainers.image.revision='+sha+'\n')
e={}
for d in ['backend','config','scripts']:
 for p in (r/d).rglob('*'):
  if p.is_file():e[str(p.relative_to(r))]=hashlib.sha256(p.read_bytes()).hexdigest()
for n in ['requirements.lock','requirements-build.lock']:e[n]=hashlib.sha256((r/n).read_bytes()).hexdigest()
p=r/'image-files.json';p.write_text(json.dumps(e));p.chmod(0o644)
f=r/'frontend-context';f.mkdir()
with tarfile.open('/tmp/quansyn-frontend-dist.tar.gz') as t:t.extractall(f,filter='data')
for p in (f/'dist').rglob('*'):p.chmod(0o755 if p.is_dir() else 0o644)
(f/'dist').chmod(0o755)
shutil.copyfile('/tmp/quansyn-dist-hashes.json',r/'dist-hashes.json');(r/'dist-hashes.json').chmod(0o644)
(f/'Dockerfile').write_text("FROM sha256:4acbdfcc0a24306ef110d793a68a60c7e4e1af9db2bbb8a8a8ad927ddc91a7ba\nUSER root\nRUN find /usr/share/nginx/html -mindepth 1 -maxdepth 1 ! -name web-dashboard -exec rm -rf {} +\nCOPY dist /usr/share/nginx/html\nUSER nginx\nLABEL org.opencontainers.image.revision="+sha+'\n')
PY
systemd-analyze verify "$STAGE/ops/systemd/quantum-runtime.slice"
DOCKER_BUILDKIT=0 docker build --pull=false --network=none --memory=256m -t "$CANDIDATE" "$STAGE/image-context"
docker run --rm --network=none --read-only --cpus=1 --memory=128m -v "$STAGE/image-files.json:/tmp/image-files.json:ro" "$CANDIDATE" python -c 'import pathlib,json,hashlib; e=json.load(open("/tmp/image-files.json")); bad=[n for n,h in e.items() if not (pathlib.Path("/app")/n).is_file() or hashlib.sha256((pathlib.Path("/app")/n).read_bytes()).hexdigest()!=h];print("candidate_runtime_files",len(e),"mismatches",bad);assert not bad'
[ "$(sha256sum /tmp/quansyn-frontend-dist.tar.gz | cut -d' ' -f1)" = c803eabb2da834970fd29bafa3596c6c711fd54b913f64acf04f5342363410c3 ]
python3 - "$STAGE" <<'CHECK'
import pathlib,json,sys
r=pathlib.Path(sys.argv[1]);e=json.loads((r/'dist-hashes.json').read_text());p=r/'dist.sha256';p.write_text(''.join(h+'  /usr/share/nginx/html/'+n+'\n' for n,h in e.items()));p.chmod(0o644)
CHECK
FRONT_CANDIDATE=ai-lab-platform-frontend:quansyn-$SHA
DOCKER_BUILDKIT=0 docker build --pull=false --network=none --memory=256m -t "$FRONT_CANDIDATE" "$STAGE/frontend-context"
docker run --rm --network=none --read-only --memory=128m -v "$STAGE/dist.sha256:/tmp/dist.sha256:ro" --entrypoint sh "$FRONT_CANDIDATE" -c 'sha256sum -c /tmp/dist.sha256 >/dev/null && test -s /usr/share/nginx/html/index.html && test -s /usr/share/nginx/html/quansyn/logo.png && test -d /usr/share/nginx/html/web-dashboard'
python3 - <<'PY'
import sqlite3
with sqlite3.connect('file:/opt/ai-lab-platform/data/hermes_chat_runs.sqlite3?mode=ro',uri=True) as c:
 assert c.execute("SELECT COUNT(*) FROM chat_runs WHERE status IN ('running','queued','stalled')").fetchone()[0]==0,'new chat: defer deployment'
PY
CHANGED=1
while read -r ref image; do if [ "$ref" = ai-lab-platform-frontend:offline ]; then docker tag "$FRONT_CANDIDATE" "$ref"; else docker tag "$CANDIDATE" "$ref"; fi; done < "$POINT/images-before.txt"
python3 - "$POINT" <<'PY'
import pathlib,json,subprocess,os,sys
p=pathlib.Path('/opt/ai-lab-shared/offline-images.attested');before=p.read_text().splitlines();services={'api','workflow-worker','planning-worker','agent-evaluation-worker','frontend'};out=[]
for line in before:
 name,old=line.split('=',1)
 if name in services:
  image=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}','ai-lab-platform-'+name+':offline'],text=True).strip()
  out.append(name+'='+image)
 else:out.append(line)
tmp=p.with_suffix('.quansyn.tmp');tmp.write_text('\n'.join(out)+'\n');tmp.chmod(0o600);os.replace(tmp,p)
PY
AI_LAB_DEPLOY_LOCK_FD=8 AI_LAB_EXPECTED_CURRENT_SHA="$BEFORE" AI_LAB_SOURCE_ARCHIVE="$ARCHIVE" AI_LAB_SOURCE_ARCHIVE_SHA256="$HASH" bash "$STAGE/scripts/update.sh" "$SHA" </dev/null
[ "$(cat /opt/ai-lab-platform/.deployed-sha)" = "$SHA" ]
printf '%s\n' 'deployment_finished=true' "rollback_point=$POINT"
