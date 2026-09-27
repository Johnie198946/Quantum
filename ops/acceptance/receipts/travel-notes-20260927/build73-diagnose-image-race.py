import asyncio,json
from sqlalchemy import select,text
from backend.db import SessionLocal
from backend.models.workflow import WorkflowDefinition,WorkflowPlanVersion,WorkflowPlanningJob
async def main():
 async with SessionLocal() as db:
  await db.execute(text('SET TRANSACTION READ ONLY'))
  rows=(await db.execute(select(WorkflowDefinition).where(WorkflowDefinition.created_by=='image-release-acceptance-c5331384d0f8'))).scalars().all()
  for w in rows:
   plans=(await db.execute(select(WorkflowPlanVersion).where(WorkflowPlanVersion.workflow_id==w.id))).scalars().all()
   jobs=(await db.execute(select(WorkflowPlanningJob).where(WorkflowPlanningJob.workflow_id==w.id))).scalars().all()
   print(json.dumps({'workflow_id':w.id,'status':w.status,'active_plan_id':w.active_plan_id,'plans':[{'id':p.id,'version':p.version,'created_at':str(p.created_at)} for p in plans],'planning_jobs':[{'id':j.id,'status':j.status,'plan_id':j.plan_id,'attempt':j.attempt} for j in jobs]}))
asyncio.run(main())
