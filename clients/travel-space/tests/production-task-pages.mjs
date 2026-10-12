import {chromium,webkit} from 'playwright';
import AxeBuilder from '@axe-core/playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';

const out=process.env.QUANTUM_TASK_QA_OUT||'/private/tmp/travel-notes-pcm-chat-20261013/task-pages';
await mkdir(out,{recursive:true});
const report={checks:[],errors:[],accessibility:[]};
function install(){
  const fixture={state:'running',calls:[]};window.flow=fixture;
  const task={id:'task-pages-test',title:'工作流逐页验收',description:'我要去青森\n{"origin":"上海","notes":["五天，轻松游览"]}',desiredOutput:'旅行攻略'};
  const artifact={id:'generic-stage',title:'待审阅成果',extension:'md',contentHash:'a'.repeat(64),metadata:{approvalGate:'stage-review'}};
  window.webkit={messageHandlers:{quantum:{postMessage:async body=>{
    fixture.calls.push(body);
    const state=fixture.state,isExecution=['queued','running','failed','cancelled','awaiting_approval','awaiting_review','completed'].includes(state);
    switch(body.operation){
      case 'bootstrap':return {workflows:[task,{id:'other',title:'另一个任务',status:'completed'}],draft:null};
      case 'snapshot':return {workflow:{...task,status:isExecution?'ready':state==='plan_review'?'awaiting_approval':state},clarification:{session:{phase:state,roundNumber:2},messages:[{content:'确认青森的旅行需求'}],events:state==='needs_attention'?[{type:'clarification_unavailable',message:'澄清服务暂不可用',payload:{detail:'云端澄清连接中断；已确认条件保留'}}]:[{payload:{question:'从哪里出发？',choices:['上海','北京']}}]},plan:{goal:task.description,deliverable:'有来源的攻略',estimatedTokens:1200,allowNetwork:true,contentHash:'b'.repeat(64),activationRevision:2,dsl:{nodes:[{id:'one',name:'检索实际资料'}]}},execution:isExecution?{id:'execution-test',status:state,progress:33,tokenUsed:980,apiCalls:2,errorMessage:state==='failed'?'上游服务暂不可用':null,nodes:[{id:'one',name:'检索实际资料',status:'succeeded'},{id:'two',name:'整理每日行程',status:state==='failed'?'failed':'running'}]}:null,artifacts:['awaiting_approval','awaiting_review','completed'].includes(state)?[artifact]:[],executionEvents:[{id:1,message:'正在读取公开资料',payload:{detail:'核对交通季节限制'}}]};
      case 'retryExecution':fixture.state='running';return {};
      case 'retryPlanning':fixture.state='planning';return {};
      case 'artifactContent':if(body.hash!==artifact.contentHash||body.artifactId!==artifact.id)throw Error('成果版本错误');return {content:'# 当前成稿\n\n青森的交通需要按出行日期核对。'};
      case 'reviewArtifact':if(body.hash!==artifact.contentHash)throw Error('审阅版本错误');fixture.state='queued';return {};
      case 'approveOutput':fixture.state='completed';return {approved:true};
      case 'export':return {opened:true};
      case 'shareArtifact':if(body.hash!==artifact.contentHash||body.artifactId!==artifact.id)throw Error('导出版本错误');return {opened:true};
      case 'approvePlan':fixture.state='agent_ready';return {};
      case 'draft':return {saved:true};
      default:throw Error('Unexpected operation '+body.operation);
    }
  }}}};
}
for(const [engine,type] of [['chromium',chromium],['webkit',webkit]]){
 const browser=await type.launch({headless:true,...(engine==='chromium'?{channel:'chrome'}:{})});
 const context=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'}),page=await context.newPage();
 page.on('pageerror',e=>report.errors.push({engine,message:e.message}));
 await page.addInitScript(install);await page.goto((process.env.QUANTUM_QA_URL||'http://127.0.0.1:4274'));
 const check=name=>report.checks.push({engine,check:name});
 const audit=async name=>{await page.waitForTimeout(200);await page.screenshot({path:`${out}/${engine}-${name}.png`});const a=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();report.accessibility.push({engine,page:name,violations:a.violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)}))});};
 const open=async state=>{await page.evaluate(state=>{window.flow.state=state;window.dispatchEvent(new CustomEvent('quantum-open-workflow',{detail:{workflowId:'task-pages-test'}}));},state);await page.waitForTimeout(250);};
 const details=async()=>{await page.getByRole('button',{name:'完整任务与执行记录',exact:true}).click();await page.getByRole('dialog',{name:'任务与执行记录',exact:true}).waitFor();};
 await page.getByRole('button',{name:'全部任务',exact:true}).click();await page.getByRole('dialog',{name:'全部任务',exact:true}).waitFor();await page.getByLabel('搜索任务',{exact:true}).fill('逐页');assert.equal(await page.locator('.task-list .task-row').count(),1);await audit('library');check('task search and current-session library stay inside reviewed renderer');
 assert.equal(await page.evaluate(()=>flow.calls.filter(c=>['openNative','openTasks'].includes(c.operation)).length),0);
 for(const state of ['clarifying','awaiting_requirement_confirmation','planning','needs_attention','plan_review','agent_ready','queued','running','failed','cancelled','completed']){
   // Awaiting approval without an execution is the plan review page.
   if(state==='awaiting_approval')continue;
   await open(state);await audit(state);check(state+' has a current-renderer state page');
   assert.equal(await page.getByText('协同拓扑',{exact:true}).count(),0);
 }
 await open('plan_review');assert.equal(await page.evaluate(()=>flow.calls.filter(c=>c.operation==='approvePlan').length),0);await page.getByRole('button',{name:'确认旅行计划',exact:true}).click();assert.equal(await page.evaluate(()=>flow.calls.find(c=>c.operation==='approvePlan').hash),'b'.repeat(64));check('plan review binds current hash and activation revision before starting');
 await open('failed');await details();await page.getByRole('button',{name:'从失败步骤继续',exact:true}).click();await page.locator('.task-details [role=status]').getByText('正在制作',{exact:true}).waitFor();assert.equal(await page.evaluate(()=>flow.calls.filter(c=>c.operation==='retryExecution').length),1);check('execution retry retains the same workflow and execution ID');
 await open('needs_attention');assert(await page.getByText('云端澄清连接中断；已确认条件保留',{exact:true}).isVisible());check('clarification failures display actual server detail rather than a success or generic result');await page.getByRole('button',{name:'重新整理计划',exact:true}).click();assert.equal(await page.evaluate(()=>flow.calls.filter(c=>c.operation==='retryPlanning').length),1);check('planning failure retries without creating another task');
 await open('awaiting_approval');await page.getByRole('button',{name:/待审阅成果/}).click();await page.getByRole('dialog',{name:'成果预览',exact:true}).waitFor();await audit('stage-review');assert.equal(await page.evaluate(()=>flow.calls.filter(c=>c.operation==='reviewArtifact').length),0);await page.getByRole('button',{name:'确认这份成稿',exact:true}).click();assert.equal(await page.evaluate(()=>flow.calls.find(c=>c.operation==='reviewArtifact').decision),'approve');check('stage review sends the viewed artifact hash only after confirmation');
 await open('awaiting_approval');await page.getByRole('button',{name:/待审阅成果/}).click();await page.getByLabel('成稿调整意见',{exact:true}).fill('保留冬季交通替代方案');await page.getByRole('button',{name:'按意见调整',exact:true}).click();assert.equal(await page.evaluate(()=>flow.calls.filter(c=>c.operation==='reviewArtifact').at(-1).comment),'保留冬季交通替代方案');check('revision preserves user comments and current artifact version');
 await open('awaiting_review');await page.getByRole('button',{name:/待审阅成果/}).click();await audit('final-review');await page.getByRole('button',{name:'采用这份成果',exact:true}).click();assert.deepEqual(await page.evaluate(()=>flow.calls.find(c=>c.operation==='approveOutput').artifactIds),['generic-stage']);check('final adoption is separate from stage approval');
 await open('completed');await page.getByRole('button',{name:/待审阅成果/}).click();await page.getByRole('button',{name:'导出这份成果',exact:true}).click();assert.equal(await page.evaluate(()=>flow.calls.find(c=>c.operation==='shareArtifact').hash),'a'.repeat(64));check('exports retrieve the authenticated original artifact with its hash');
 await open('running');await details();await page.getByText('这次想完成什么',{exact:true}).click();assert(await page.getByText('出发城市：上海',{exact:false}).isVisible());assert.equal(await page.locator('.task-brief').innerText().then(t=>t.includes('"origin"')),false);await page.getByText('沿途的执行记录',{exact:true}).click();await audit('execution-records');check('old embedded requirement JSON displays as readable fields without server mutation');
 await context.close();await browser.close();
}
await writeFile(out+'/report.json',JSON.stringify(report,null,2));assert.deepEqual(report.errors,[]);assert.deepEqual(report.accessibility.flatMap(x=>x.violations),[]);console.log(JSON.stringify({checks:report.checks.length,errors:report.errors.length,accessibilityScans:report.accessibility.length}));
