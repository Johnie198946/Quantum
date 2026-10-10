#!/usr/bin/env bash
set -euo pipefail
SHA=$1
BEFORE=dcbcf0551016fcb361678c8a43dfd764137f928b
HASH=$2
PAYLOAD_HASH=$3
OLD_IMAGE=sha256:80de6d1507d2a9107c7109e83d94fdc4f66746cd7bfcdfd0dcbf2506b9bae1af
CANDIDATE=ai-lab-platform-api:quansyn-feishu-$SHA
umask 077
if [ "${QUANSYN_DEPLOY_LOCK_FD:-}" != "8" ]; then exec 8>/run/lock/ai-lab-platform-update.lock; fi
[ "$(readlink /proc/$$/fd/8)" = /run/lock/ai-lab-platform-update.lock ]
flock -n 8
[ "$(cat /opt/ai-lab-platform/.deployed-sha)" = "$BEFORE" ]
POINT=$(mktemp -d /opt/ai-lab-shared/rollbacks/quansyn-feishu-20261010.XXXXXX)
printf '%s\n' "$POINT" > /tmp/quansyn-feishu-20261010-point
readlink -f /opt/ai-lab-platform > "$POINT/release-before.txt"
printf '%s\n' "$BEFORE" > "$POINT/sha-before.txt"
cp -a /opt/ai-lab-shared/offline-images.attested "$POINT/offline-images.attested.before"
systemctl show system-authen.slice -p MemoryHigh -p MemoryMax -p MemorySwapMax > "$POINT/authen-before.txt"
python3 - "$POINT" "$OLD_IMAGE" <<'PY'
import sqlite3,json,subprocess,pathlib,sys
p=pathlib.Path(sys.argv[1]);rows=[]
for n in ['api','workflow-worker','planning-worker','agent-evaluation-worker','frontend']:
 c=json.loads(subprocess.check_output(['docker','inspect','ai-lab-platform-'+n+'-1']))[0]
 assert c['Image']==(sys.argv[2] if n!='frontend' else 'sha256:b0872402aa3395342c3ee0e25c0f73db21aef4aad22160c13f008ca95cf48241'),n
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
[ "$(sha256sum /tmp/quansyn-feishu-payload.tar.gz | cut -d' ' -f1)" = "$PAYLOAD_HASH" ]
python3 - "$STAGE" "$SHA" <<'PYBUILD'
import pathlib,json,hashlib,sys,shutil,tarfile
r=pathlib.Path(sys.argv[1]);sha=sys.argv[2]
payload=r/'upload-payload';payload.mkdir()
with tarfile.open('/tmp/quansyn-feishu-payload.tar.gz') as t:t.extractall(payload,filter='data')
c=r/'image-context';c.mkdir();shutil.copyfile(payload/'api.Dockerfile',c/'Dockerfile')
shutil.copyfile(payload/'quansyn.py',c/'quansyn.py');(c/'quansyn.py').chmod(0o644)
f=r/'frontend-context';f.mkdir()
shutil.copyfile(payload/'default.conf',f/'default.conf');shutil.copyfile(payload/'frontend.Dockerfile',f/'Dockerfile')
(f/'default.conf').chmod(0o644)
PYBUILD
systemd-analyze verify "$STAGE/ops/systemd/quantum-runtime.slice"
DOCKER_BUILDKIT=0 docker build --pull=false --network=none --memory=256m -t "$CANDIDATE" "$STAGE/image-context"
FRONT_CANDIDATE=ai-lab-platform-frontend:quansyn-$SHA
DOCKER_BUILDKIT=0 docker build --pull=false --network=none --memory=256m -t "$FRONT_CANDIDATE" "$STAGE/frontend-context"
docker run --rm --network=none --add-host taskboard:127.0.0.1 --add-host api:127.0.0.1 --add-host host.docker.internal:127.0.0.1 --volumes-from ai-lab-platform-frontend-1:ro --entrypoint nginx "$FRONT_CANDIDATE" -t
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
