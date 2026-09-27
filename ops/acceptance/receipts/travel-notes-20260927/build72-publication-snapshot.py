"""Read-only published-edition and media inventory; no database or content writes."""
import hashlib,json,sqlite3,sys
from pathlib import Path
root=Path('/opt/ai-lab-platform/data/runtime/publications').resolve()
with sqlite3.connect((root/'publication.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
 db.row_factory=sqlite3.Row
 rows=db.execute('SELECT * FROM editions WHERE publication_id=?',('publication-6d65e4fff6f4ae7734d1585c3a05a80a',)).fetchall()
 assert len(rows)==1, 'publication must have exactly one edition'
 r=dict(rows[0]);bundle=json.loads(r['bundle_json']);plan=bundle['illustration_plan']
 digest=hashlib.file_digest((root/r['body_ref']).open('rb'),'sha256').hexdigest()
 assert digest==r['content_hash']==plan['body_sha256']=='076cbb867c99609ea8ff09322ffcdf5f391990a6df7960c7f708f6776d5c5c9f'
 assert r['state']=='published' and r['actual_release_at'], 'publication must remain published'
 snapshot={'publication_id':r['publication_id'],'count':len(rows),'state':r['state'],'release_at':r['release_at'],'actual_release_at':r['actual_release_at'],'body_sha256':digest,'bundle_sha256':hashlib.sha256(r['bundle_json'].encode()).hexdigest(),'media':{}}
 assert len(plan['illustrations'])==3 and len(bundle['assets'])==5
 for asset in bundle['assets']:
  receipt=asset['receipt']
  evidence=db.execute('SELECT private_ref FROM evidence WHERE artifact_id=?',(receipt['artifact_id'],)).fetchone()
  assert evidence, 'missing media receipt'
  path=(root/evidence['private_ref']).resolve();assert path.is_relative_to(root), 'media outside publication root'
  actual=hashlib.file_digest(path.open('rb'),'sha256').hexdigest();assert actual==receipt['sha256']
  snapshot['media'][asset['role']]={'artifact_id':receipt['artifact_id'],'sha256':actual,'private_ref':evidence['private_ref']}
 assert len(snapshot['media'])==5
 if len(sys.argv)>1:
  before=json.loads(Path(sys.argv[1]).read_text())
  assert snapshot==before, 'published edition or media changed during deployment'
 print(json.dumps(snapshot,ensure_ascii=False,sort_keys=True))
