import {chromium,webkit} from '@playwright/test';
import {writeFile,mkdir} from 'node:fs/promises';
import AxeBuilder from '@axe-core/playwright';
import assert from 'node:assert/strict';
import {installFixture,travelDocument} from './production-fixture.js';
const out=process.env.QUANTUM_QA_OUT||'/private/tmp/travel-notes-pcm-chat-20261013/ui';
await mkdir(out,{recursive:true});
const report={checks:[],errors:[],screenshots:[],accessibility:[]};
for(const [engine,type] of (process.env.QUANTUM_SKIP_WEBKIT?[['chromium',chromium]]:[['chromium',chromium],['webkit',webkit]])){
 const browser=await type.launch({headless:true,...(engine==='chromium'?{channel:'chrome'}:{})});
 for(const width of [375,390,430]){
  const context=await browser.newContext({viewport:{width,height:844},reducedMotion:'reduce'});const page=await context.newPage();
  page.on('pageerror',e=>report.errors.push({engine,width,message:e.message}));
  await page.addInitScript({content:`const travelDocument=${JSON.stringify({...travelDocument,client_state:{version:1,saved:true}})};(${installFixture.toString()})();`});
  await page.goto((process.env.QUANTUM_QA_URL||'http://127.0.0.1:4274'));
  await page.getByRole('button',{name:'旅行测试任务'}).waitFor();
  assert.equal(await page.locator('.review-rail,.status-bar,.home-indicator,.root-tabs').count(),0);
  report.checks.push({engine,width,check:'production chrome removed and real workflow list loaded'});
  await page.screenshot({path:`${out}/${engine}-${width}-workflow.png`});
  const audit=async screen=>{const a=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();report.accessibility.push({engine,width,screen,violations:a.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)}))});};
  await audit('workflow');
  await page.getByRole('button',{name:'旅行测试任务'}).click();
  await page.locator('.notebook-screen').waitFor();
  await page.waitForTimeout(450);
  assert.equal(await page.getByText('鹿儿岛',{exact:true}).count(),0);
  const text=await page.locator('body').innerText();
  assert(text.includes('测试旅行')||text.includes('旅行手记'));
  report.checks.push({engine,width,check:'travel v2 hydrates notebook without sample destination'});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
  assert.equal(overflow,false);
  report.checks.push({engine,width,check:'no page overflow'});
  await page.screenshot({path:`${out}/${engine}-${width}-notebook.png`});await audit('notebook');
  await page.getByRole('navigation',{name:'手记章节'}).getByRole('button').nth(1).click();
  await page.getByRole('group',{name:'旅行日记日期'}).waitFor();
  await page.getByRole('group',{name:'旅行日记日期'}).getByRole('button').nth(1).click();
  report.checks.push({engine,width,check:'daily notebook day selection is interactive'});
  await page.screenshot({path:`${out}/${engine}-${width}-diary.png`});await audit('diary');
  await page.waitForTimeout(1200);
  const writes=await page.evaluate(()=>window.fixture.calls.filter(c=>c.operation==='saveState'));
  assert(writes.every(write=>!write.state.profile.travelDocument));
  report.checks.push({engine,width,check:'client state avoids recursive artifact embedding'});
  await context.close();
 }
 await browser.close();
}
await writeFile(out+'/report.json',JSON.stringify(report,null,2));
assert.deepEqual(report.errors,[]);
assert.deepEqual(report.accessibility.flatMap(a=>a.violations),[]);
console.log(JSON.stringify({checks:report.checks.length,errors:report.errors.length,report:out+'/report.json'}));
