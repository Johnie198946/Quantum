"""Local acceptance fixture: real image/PCM routes, isolated storage and fixed test owner."""
import os
import tempfile
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
root=tempfile.mkdtemp(prefix='image-studio-local-')
os.environ['AI_LAB_HOME']=root
os.environ['AI_LAB_GENERATED_ARTIFACT_ROOT']=root+'/images'
os.environ['DATABASE_URL']='sqlite+aiosqlite:///'+root+'/test.db'
from fastapi import FastAPI, Header, HTTPException
from backend.api.auth import require_auth
from backend.api.tenant import current_tenant
from backend.api.capabilities import router as capabilities
from backend.api.documents import router as documents
app=FastAPI()
async def fixture_owner(authorization: str = Header('')):
 if authorization!='Bearer image-studio-local-fixture':
  raise HTTPException(401)
 current_tenant.set('image-studio-test')
 return {'tenant_key':'image-studio-test','user_id':'alice','sub':'alice'}
app.dependency_overrides[require_auth]=fixture_owner
app.include_router(capabilities)
app.include_router(documents)
@app.get('/health')
def health():return {'status':'ok','fixture':'image-studio-local'}
if __name__=='__main__':
 import uvicorn
 uvicorn.run(app,host='127.0.0.1',port=8897)
