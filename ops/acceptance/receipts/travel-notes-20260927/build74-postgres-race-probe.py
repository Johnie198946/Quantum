import asyncio, importlib.util, json, os, pathlib, sys, tempfile
mode=sys.argv[1]
os.environ['DATABASE_URL']=f'postgresql+asyncpg://travel_test@127.0.0.1:55474/travel_{mode}'
os.environ['AI_LAB_HOME']=tempfile.mkdtemp(prefix='travel-pg-vault-')
os.environ['AUTHEN_JWT_SECRET']='isolated-test-only'
os.environ['HERMES_BRIDGE_URL']='http://127.0.0.1:1/v1/chat'
os.environ['HERMES_BRIDGE_INTERNAL_TOKEN']='isolated-test-only'
import pytest
from sqlalchemy import select, func
from backend.db import init_db, SessionLocal, engine
from backend.services import workflow_planner as planner, workflow_planning as worker
from backend.models.workflow import WorkflowPlanVersion, WorkflowPlanningJob
spec=importlib.util.spec_from_file_location('image_test', 'tests/test_image_processing.py')
test=importlib.util.module_from_spec(spec);spec.loader.exec_module(test)
async def main():
 await init_db()
 original=planner.validate_plan_policy
 scanned=False
 observations={'mode':mode,'database':f'travel_{mode}','postgres_port':55474}
 async def interleave(*args,**kwargs):
  nonlocal scanned
  if not scanned:
   scanned=True
   async with SessionLocal() as db:
    observations['orphan_jobs']=await worker.backfill_orphaned_planning_jobs(db)
    job=await worker.claim_next(db,'isolated-race-probe')
   if job:
    await worker.process_job(job.id,'isolated-race-probe')
    async with SessionLocal() as db:
     observations['worker_status']=(await db.get(WorkflowPlanningJob,job.id)).status
  return await original(*args,**kwargs)
 planner.validate_plan_policy=interleave
 try:
  with pytest.MonkeyPatch.context() as mp:
   await test.test_upload_to_image_workflow_and_downloadable_jpeg(pathlib.Path(tempfile.mkdtemp(prefix='travel-pg-fixture-')),mp,'generated','chat')
  observations['full_image_path']='passed'
  assert mode=='fixed' and observations['orphan_jobs']==0
 except Exception as exc:
  observations['error_type']=type(exc).__name__
  observations['plan_constraint_conflict']='uq_workflow_plan_version' in str(exc)
  if mode!='old' or not observations['plan_constraint_conflict']: raise
 finally:
  async with SessionLocal() as db:
   observations['plan_count']=await db.scalar(select(func.count(WorkflowPlanVersion.id)))
   observations['job_count']=await db.scalar(select(func.count(WorkflowPlanningJob.id)))
  print(json.dumps(observations),flush=True)
  await engine.dispose()
asyncio.run(main())
