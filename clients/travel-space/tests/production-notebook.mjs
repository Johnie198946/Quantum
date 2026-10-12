import {chromium,webkit} from '@playwright/test';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {installFixture,travelDocument} from './production-fixture.js';
const out=process.env.QUANTUM_QA_OUT||'/private/tmp/travel-notes-pcm-chat-20261013/notebook';await mkdir(out,{recursive:true});
const report={checks:[],errors:[]};
for(const [engine,type] of [['chromium',chromium],['webkit',webkit]]){
 const browser=await type.launch({headless:true,...(engine==='chromium'?{channel:'chrome'}:{})});
 const context=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'});const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));
 const open=async document=>{
  await context.addInitScript({content:`const travelDocument=${JSON.stringify(document)};(${installFixture.toString()})();fixture.openNote=true;`});
  await page.goto(process.env.QUANTUM_QA_URL||'http://127.0.0.1:4274');await page.locator('.notebook-screen').waitFor();
 };
 await open({...travelDocument,client_state:{version:1,saved:true,noteTitle:'自己的青森手记',entries:{'day-1':'保留自己的原话'}}});
 assert.equal(await page.locator('.notebook-cover').count(),1);assert.equal(await page.locator('.clarification-sheet,.workflow-native-plan,.review-rail').count(),0);
 report.checks.push({engine,check:'cloud note opens the approved template without original Chat execution'});
 await page.getByRole('button',{name:'打开这趟旅行',exact:true}).click();await page.getByRole('button',{name:'开始这趟旅行',exact:true}).click();await page.locator('.lifecycle-today').waitFor();
 assert.equal(await page.evaluate(()=>fixture.doc.client_state.profile.tripSession.phase),'during');report.checks.push({engine,check:'saved note starts a trip through its own persisted state'});
 await page.waitForTimeout(1400);await page.getByRole('button',{name:'开始这项安排',exact:true}).click();await page.getByRole('button',{name:'这项已完成',exact:true}).waitFor();
 assert.equal(await page.evaluate(()=>fixture.doc.actions[0].status),'in_progress');report.checks.push({engine,check:'note-bound actual progress comes from a server receipt'});
 await page.screenshot({path:out+'/'+engine+'-saved-note-trip.png'});await context.close();
 const emptyContext=await browser.newContext({viewport:{width:390,height:844}}),empty=await emptyContext.newPage();empty.on('pageerror',e=>report.errors.push(e.message));
 await empty.addInitScript({content:`const travelDocument=${JSON.stringify({...travelDocument,actions:[],stops:[],client_state:{version:1,saved:true}})};(${installFixture.toString()})();fixture.openNote=true;`});
 await empty.goto(process.env.QUANTUM_QA_URL||'http://127.0.0.1:4274');await empty.locator('.notebook-cover').waitFor();assert.equal(await empty.getByRole('button',{name:'打开这趟旅行',exact:true}).count(),0);
 await empty.getByRole('navigation',{name:'手记章节'}).getByRole('button',{name:'旅行日记'}).click();await empty.getByText('还没有每天的安排。已有旅行文字保留在实用附录中。',{exact:true}).waitFor();
 report.checks.push({engine,check:'legacy notes without itinerary render without inventing days or visits'});await emptyContext.close();await browser.close();
}
await writeFile(out+'/report.json',JSON.stringify(report,null,2));assert.deepEqual(report.errors,[]);console.log(JSON.stringify({checks:report.checks.length,errors:report.errors.length}));
