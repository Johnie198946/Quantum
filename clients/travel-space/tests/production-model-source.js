import {comparisonPrice,filterCandidates} from '../src/components/services/planning';
import {confirmExistingBooking} from '../src/production/bookings';
import assert from 'node:assert/strict';
import {TravelRuntime,travelRequestDescription} from '../src/production/runtime';
import {parseDiscovery,draftDays} from '../src/production/travel-preflight';
import {seedRequirements,profileFromRequirements} from '../src/components/travel-requirements';
import {documentToState,stateToDocument} from '../src/production/travel-adapter';
import {parseServiceResults,searchServices,serviceCache,routeQueryKey,resetServiceCache} from '../src/production/service-provider';
import {routeOptions} from '../src/components/services/route-model';
import {formatPrice} from '../src/components/flight/price-currency';
import {routeKML,setMapDays,project} from '../src/components/mapRoute';
import {convertMinor,DEFAULT_RATES,plannedEntries} from '../src/components/budget/budget-model';
import {travelDocument} from './production-fixture';
import {mergeTravelEdits} from '../src/production/travel-edits';
export const report={checks:[]};
const check=(name,fn)=>{fn();report.checks.push(name);};
check('server-facing travel brief is readable, preserves unknown dates and includes each note once',()=>{
 const note='上海出发，5天2人，人均8000元，日期未定';
 const text=travelRequestDescription({destination:'青森',requirements:{date:'未定',duration:5,count:2,origin:'上海',notes:[note],interests:['当地美食']},additional:note},'我要去青森');
 assert(text.startsWith('我要去青森\n'));assert(text.includes('出发日期：未定'));assert(text.includes('游玩天数：5'));assert.equal(text.split(note).length,2);assert(!text.includes('"duration"'));assert(!text.includes('interestsDecided'));
});
let handler;
globalThis.window={webkit:{messageHandlers:{quantum:{postMessage:body=>handler(body)}}}};
const snapshot=()=>({workflow:{id:'workflow-one',status:'completed'},execution:{id:'execution-one',status:'completed'},artifact:{id:'artifact-one',contentHash:'a'.repeat(64)},artifacts:[],content:JSON.stringify(travelDocument)});
const polling=new TravelRuntime();let pollingReads=0;
handler=async()=>{pollingReads++;return {...snapshot(),workflow:{id:'workflow-one',status:'ready'},execution:{id:'execution-one',status:'queued'},artifact:null,content:null};};
await polling.refresh('workflow-one');await new Promise(resolve=>setTimeout(resolve,2200));
check('a ready workflow definition continues polling its queued execution',()=>assert(pollingReads>=2));polling.stop();
check('unknown dates, hours and coordinates survive document hydration',()=>{const s=documentToState(travelDocument);assert.equal(s.days[1].geo,null);assert.equal(s.days[0].items[0].time,'');assert.equal(s.days[0].date,'日期未定');assert.equal(stateToDocument(travelDocument,s.days,s.profile).actions[0].start,null);});
check('personal state cannot override authoritative actual progress',()=>{const doc=structuredClone(travelDocument);doc.client_state={version:1,profile:{tripSession:{facts:{invented:{status:'completed'}}}}};assert.deepEqual(documentToState(doc).profile.tripSession.facts,{});});
check('completed travel facts and source IDs survive round trip',()=>{const doc=structuredClone(travelDocument);Object.assign(doc.actions[0],{status:'completed',actual_end:'2026-10-01T12:00:00Z'});const state=documentToState(doc);assert.equal(state.profile.tripSession.facts['action-1'].status,'completed');assert.equal(stateToDocument(doc,state.days,state.profile).actions[0].actual_end,'2026-10-01T12:00:00Z');assert.deepEqual(stateToDocument(doc,state.days,state.profile).actions[0].source_ids,['source-1']);});
check('UTC timestamps render the destination clock and date without changing the source instant',()=>{const doc=structuredClone(travelDocument);doc.actions[0].start='2026-10-01T18:30:00Z';const state=documentToState(doc);assert.equal(state.days[0].items[0].time,'03:30');assert.equal(state.days[0].dateISO,'2026-10-02');assert.equal(stateToDocument(doc,state.days,state.profile).actions[0].start,doc.actions[0].start);});
check('service results reject untraceable and future evidence',()=>{const row={id:'x',name:'结果',geo:{lat:31,lon:120},source_url:'https://example.org/place',checked_at:'2026-10-01',price:null};assert.equal(parseServiceResults(JSON.stringify({results:[row]}),'hotel').length,1);assert.equal(parseServiceResults(JSON.stringify({results:[{...row,source_url:'javascript:alert(1)'},{...row,checked_at:'invalid'},{...row,checked_at:'2999-01-01'},{...row,price:100,priceCurrency:null}]}),'hotel').length,0);});
check('unknown service capacity, rating and price remain unknown',()=>{const row=parseServiceResults(JSON.stringify({results:[{id:'x',name:'资料',geo:{lat:31,lon:120},source_url:'https://example.org',checked_at:'2026-10-01'}]}),'hotel')[0];assert.equal(row.capacity,null);assert.equal(row.rating,null);assert.equal(row.price,null);});
check('foreign quote retains original currency without an invented FX rate',()=>{assert.match(formatPrice(15000,'CNY','JPY'),/15,000/);assert.match(formatPrice(15000,'CNY','JPY'),/汇率待确认/);assert.equal(DEFAULT_RATES.JPY,'');assert.equal(convertMinor(15000,'JPY','CNY'),null);});
check('unknown map coordinates never become a plotted destination',()=>{const s=documentToState(travelDocument);setMapDays(s.days);assert(Number.isNaN(project(s.days[1].geo).x));const xml=routeKML(s.days);assert.equal((xml.match(/<Placemark>/g)||[]).length,1);assert(!xml.includes('<LineString>'));});
check('real route schedules are not shifted to the requested departure',()=>{serviceCache.routes=[{id:'r',mode:'火车',date:'2026-10-01',departure:'09:00',arrival:'09:30',duration:30,price:20,priceCurrency:'JPY',queryKey:routeQueryKey({from:{lat:31,lon:120},to:{lat:31.1,lon:120.1},date:'2026-10-01',time:'09:00'}),stops:[{name:'A',time:'09:00'},{name:'B',time:'09:30'}]}];const args={mode:'火车',date:'2026-10-01',time:'10:00',from:{lat:31,lon:120},to:{lat:31.1,lon:120.1}};assert.equal(routeOptions(args).length,0);assert.equal(routeOptions({...args,time:'09:00'}).length,1);assert.equal(routeOptions({...args,from:null}).length,0);});
const queued=new TravelRuntime();queued.publish({snapshot:snapshot()});let rev=1;const calls=[];
handler=async body=>{calls.push(body);assert.equal(body.hash,String(rev===1?'a':rev).repeat(64));await new Promise(r=>setTimeout(r,5));rev++;return {id:'artifact-'+rev,contentHash:String(rev).repeat(64)};};
await Promise.all([queued.enqueue('saveState',{state:{version:1}}),queued.enqueue('progress',{actionId:'action-1',progress:'in_progress'})]);
check('serialized mutations use the preceding receipt hash and unique IDs',()=>{assert.equal(calls.length,2);assert.notEqual(calls[0].requestId,calls[1].requestId);assert.equal(calls[1].artifactId,'artifact-2');});
let release;queued.queue=new Promise(r=>{release=r;});const oldWrite=queued.enqueue('saveState',{state:{version:1}});queued.generation++;queued.publish({snapshot:{...snapshot(),workflow:{id:'workflow-two',status:'completed'}}});release();await assert.rejects(oldWrite,/任务已切换/);report.checks.push('queued edits do not move into another task');
const recovered=new TravelRuntime();const draft={version:1,_workflowId:'workflow-one',_artifactHash:'a'.repeat(64),entries:{'day-1':'我的草稿'},profile:{},days:[]};
handler=async body=>body.operation==='bootstrap'?{workflows:[snapshot().workflow],draft}:snapshot();let restored;recovered.documentListeners.add(s=>{restored=s;});await recovered.boot();
check('recovery rebinds to an owned server task before merging personal draft',()=>{assert.equal(recovered.state.snapshot.workflow.id,'workflow-one');assert.equal(restored.entries['day-1'],'我的草稿');assert.equal(restored.days[1].geo,null);});
recovered.stop();queued.stop();

let releaseQuery;const beforeWeather={...serviceCache.weather};handler=()=>new Promise(resolve=>{releaseQuery=resolve;});let current=true;
const query=searchServices('weather',{dayId:'day-1'},()=>current);current=false;releaseQuery({answer:JSON.stringify({results:[{id:'weather',name:'晴',source_url:'https://example.org/weather',checked_at:'2026-10-01'}]}),hasActions:false});await assert.rejects(query,/行程已切换/);assert.deepEqual(serviceCache.weather,beforeWeather);report.checks.push('stale service queries cannot replace another trip weather');
const approving=new TravelRuntime();approving.publish({snapshot:snapshot()});let releaseApproval;handler=()=>new Promise(resolve=>{releaseApproval=resolve;});const approval=approving.approvePlan();await assert.rejects(approval,/等待服务端计划/);
approving.publish({snapshot:{...snapshot(),plan:{contentHash:'plan-hash',activationRevision:2}}});const lateApproval=approving.approvePlan();approving.generation++;approving.publish({snapshot:{...snapshot(),workflow:{id:'workflow-two'}}});releaseApproval({});await assert.rejects(lateApproval,/行程已切换/);assert.equal(approving.state.snapshot.workflow.id,'workflow-two');report.checks.push('late approval cannot refresh a different active workflow');approving.stop();

const offlineRuntime=new TravelRuntime();offlineRuntime.publish({snapshot:snapshot(),offline:true});offlineRuntime.artifactHash='a'.repeat(64);const offlineCalls=[];handler=async body=>{offlineCalls.push(body);return {saved:true};};
await assert.rejects(offlineRuntime.persist({version:1,entries:{'day-1':'断网中的原话'}}),/当前离线/);assert.deepEqual(offlineCalls.map(c=>c.operation),['draft']);assert.equal(offlineCalls[0].state._workflowId,'workflow-one');assert.equal(offlineRuntime.recoveryDraft.entries['day-1'],'断网中的原话');report.checks.push('offline edits preserve an owned native draft before blocking server mutations');offlineRuntime.stop();

const bookingRuntime=new TravelRuntime();bookingRuntime.publish({snapshot:snapshot()});bookingRuntime.document=structuredClone(travelDocument);let sentBooking;handler=async body=>{if(body.operation==='snapshot')return {...snapshot(),artifact:{id:'booked-artifact',contentHash:'b'.repeat(64)},content:JSON.stringify(bookingRuntime.document)};sentBooking=body;return {id:'booked-artifact',contentHash:'b'.repeat(64)};};await confirmExistingBooking('action-1','CONFIRM-123',bookingRuntime);assert.deepEqual(sentBooking.confirmedBookings,{'action-1':'CONFIRM-123'});assert.equal(JSON.parse(sentBooking.content).actions[0].booking_reference,'CONFIRM-123');assert.equal(bookingRuntime.document.actions[0].booking_reference,'CONFIRM-123');await assert.rejects(confirmExistingBooking('action-1','OTHER',bookingRuntime),/已有订单/);report.checks.push('explicit existing order association uses canonical confirmed bookings and cannot silently replace it');bookingRuntime.stop();

check('mixed service currencies require a confirmed exchange rate for budget comparison',()=>{const row={price:100,priceCurrency:'JPY'};assert.equal(comparisonPrice(row,{currency:'CNY'}),null);assert.equal(comparisonPrice(row,{currency:'CNY',budgetLedger:{baseCurrency:'CNY',rates:{JPY:'0.05'}}}),5);assert.equal(comparisonPrice({price:10,priceCurrency:'CNY'},{currency:'CNY'}),10);});

const discoveryRow={id:'place-one',name:'景点一',source_url:'https://example.org/place',checked_at:'2026-10-12',lat:null,lon:null};
check('discovery rejects unsafe/future sources, deduplicates IDs and keeps unknown coordinates',()=>{
 const result=parseDiscovery(JSON.stringify({places:[discoveryRow,discoveryRow,{...discoveryRow,id:'bad',source_url:'javascript:alert(1)'},{...discoveryRow,id:'future',checked_at:'2100-01-01'}]}));
 assert.equal(result.places.length,1);assert.equal(result.places[0].geo,null);assert.equal(result.places[0].imageSource,'风景示意');
 assert.throws(()=>parseDiscovery(JSON.stringify({places:Array.from({length:31},()=>discoveryRow)})),/格式/);
});
check('preparation days preserve the requested duration without inventing times, dates or actual progress',()=>{
 const rows=draftDays({destination:'青森',duration:5},parseDiscovery(JSON.stringify({places:[discoveryRow]})).places);
 assert.equal(rows.length,5);assert(rows.every(d=>d.provisional&&d.dateISO===null));assert.equal(rows[0].items[0].time,'');assert(rows.every(d=>d.geo===null));assert.equal(rows[0].items[0].actual_start,undefined);
});
check('human budget extraction preserves thousands and explicit foreign currency',()=>{
 const r=seedRequirements('从上海出发，5天，2人，人均预算8,000美元，日期未定');
 const p=profileFromRequirements({currency:'人民币'},r);assert.equal(p.amount,'8000');assert.equal(p.currency,'美元');assert.equal(p.duration,5);assert.equal(r.date,null);
});
const beforePlan=new TravelRuntime(),preflightOps=[];handler=async body=>{preflightOps.push(body.operation);return {answer:JSON.stringify({places:[discoveryRow]}),hasActions:false};};
await beforePlan.discover({destination:'青森',requirements:{notes:[]}},'我要去青森');assert.deepEqual(preflightOps,['ask']);assert.equal(beforePlan.state.snapshot,null);report.checks.push('preflight discovery makes no workflow creation, approval or execution request');beforePlan.stop();
const lateDiscovery=new TravelRuntime();let releaseDiscovery;handler=()=>new Promise(resolve=>{releaseDiscovery=resolve;});const pendingDiscovery=lateDiscovery.discover({destination:'青森'},'我要去青森');lateDiscovery.generation++;releaseDiscovery({answer:JSON.stringify({places:[discoveryRow]}),hasActions:false});await assert.rejects(pendingDiscovery,/已切换/);assert.equal(lateDiscovery.state.discovery,undefined);report.checks.push('late discovery cannot replace another active trip');lateDiscovery.stop();

const convergence=new TravelRuntime();handler=async()=>({answer:JSON.stringify({summary:'用户需求',question:'',ready:true}),hasActions:false});
assert.equal((await convergence.converge({destination:'青森',requirements:{}},'我要去青森',[{role:'user',text:'我要去青森'}])).ready,false);
assert.equal((await convergence.converge({destination:'青森',requirements:{origin:'上海',duration:5,count:2}},'我要去青森')).ready,true);
assert.equal((await convergence.converge({destination:'青森',requirements:{}},'其他都未定，先规划',[{role:'user',text:'其他都未定，先规划'}])).ready,true);
report.checks.push('model readiness cannot fill missing user conditions without explicit open-condition consent');convergence.stop();

const approvalGate=new TravelRuntime();let prematureCalls=0;handler=async()=>{prematureCalls++;return {};};
for(const status of ['running','queued','failed','cancelled']) {
 approvalGate.state.snapshot={workflow:{id:'same-trip'},execution:{id:'same-execution',status,errorMessage:'上游成果超过限制'},artifact:{id:'approved-draft',contentHash:'a'.repeat(64)}};
 await assert.rejects(approvalGate.approveOutput());
}
assert.equal(prematureCalls,0);report.checks.push('stage-approved drafts cannot send final adoption during writing, failure or cancellation');approvalGate.stop();

check('server daily titles, practical guidance and budget estimates survive hydration without becoming bookings or actual visits',()=>{
 const doc={...structuredClone(travelDocument),days:[{id:'day-1',title:'抵达与慢行',journal:'晚到时保留入住缓冲'}],practical_guidance:[{title:'季节接驳',details:'先核对运营日期'}],budget_breakdown:[{category:'stay',value:'待日期确定后核价'}]};
 const state=documentToState(doc);assert.equal(state.days[0].name,'抵达与慢行');assert.equal(state.days[0].summary,'晚到时保留入住缓冲');assert.deepEqual(state.profile.practicalGuidance,doc.practical_guidance);assert.deepEqual(state.profile.budgetBreakdown,doc.budget_breakdown);
 const output=stateToDocument(doc,state.days,state.profile);assert.deepEqual(output.practical_guidance,doc.practical_guidance);assert(output.actions.every(a=>a.status==='planned'&&!a.booking_reference));
});

check('unknown coordinates do not replace a known daily place name with a long province title',()=>{
 const doc=structuredClone(travelDocument);doc.destination='日本青森县（青森市、八甲田、奥入濑溪流）';doc.stops[0].latitude=null;doc.stops[0].longitude=null;
 const state=documentToState(doc);assert.equal(state.days[0].place,'第一处风景');assert.equal(state.days[0].geo,null);
});

check('transport intent and user-entered bookings are included without claiming purchases',()=>{
 const text=travelRequestDescription({destination:'青森',servicePlan:{hotel:{'day-1':{name:'住宿一',status:'recorded',reference:'USER-123',dateISO:'2026-11-01',price:15000,priceCurrency:'JPY'}},flights:{outbound:{name:'航班意向',status:'todo',time:'08:30'}}}},'我要去青森');
 assert(text.includes('USER-123'));assert(text.includes('15000'));assert(text.includes('JPY'));assert(text.includes('已有预订（用户录入）'));assert(text.includes('待预订'));assert(text.includes('不执行购票/预约'));
});
check('user reorder survives canonical export while actual facts remain unchanged',()=>{
 const state=documentToState(travelDocument);const output=stateToDocument(travelDocument,state.days.slice().reverse(),state.profile);
 assert.deepEqual(output.actions.map(a=>a.id),['action-2','action-1']);assert(output.actions.every(a=>a.status==='planned'));
});
check('sourced places with unknown coordinates survive query and show unknown distance',()=>{
 const row={id:'unknown-geo',name:'有地址的酒店',source_url:'https://example.org/place',checked_at:'2026-10-01',geo:null};
 serviceCache.candidates=parseServiceResults(JSON.stringify({results:[row]}),'hotel');
 const found=filterCandidates('hotel',{lat:40,lon:140},{radius:3},{currency:'JPY',interests:[]},null,null,2);
 assert.equal(found.length,1);assert.equal(found[0].geo,null);assert(!Number.isFinite(found[0].distance));
});
const scopedRoutes=new TravelRuntime();const routeArgs={mode:'火车',from:{lat:40,lon:140},to:{lat:40.1,lon:140.1},fromName:'青森',toName:'弘前',date:'2026-11-01',time:'09:00'};
handler=async()=>({answer:JSON.stringify({results:[{id:'train-one',name:'公开线路',source_url:'https://example.org/train',checked_at:'2026-10-01',mode:'火车',date:'2026-11-01',departure:'09:00',duration:30,price:null,stops:[{name:'青森',time:'09:00'},{name:'弘前',time:'09:30'}]}]}),hasActions:false});
await searchServices('route',routeArgs);
check('unknown route price remains unknown and endpoint changes cannot reuse a cached schedule',()=>{assert.equal(routeOptions(routeArgs)[0].price,null);assert.equal(routeOptions(routeArgs)[0].distance,null);assert.equal(routeOptions({...routeArgs,toName:'八甲田'}).length,0);});
let releaseStale;handler=()=>new Promise(r=>{releaseStale=r;});const staleSearch=searchServices('route',routeArgs);resetServiceCache();releaseStale({answer:'{"results":[]}',hasActions:false});await assert.rejects(staleSearch,/行程已切换/);report.checks.push('a reset blocks stale queries even without a caller-provided task guard');scopedRoutes.stop();
const lostCreate=new TravelRuntime();const createBodies=[];handler=async body=>{if(body.operation==='create'){createBodies.push(body);if(createBodies.length===1)throw Error('response lost');return {workflow:{id:'recovered-create'}};}if(body.operation==='snapshot')return {workflow:{id:'recovered-create',status:'draft'},clarification:{session:{phase:'clarifying'}}};return {saved:true};};
await assert.rejects(lostCreate.prepare({destination:'青森'},'我要去青森'),/response lost/);await lostCreate.prepare({destination:'青森'},'我要去青森');assert.equal(createBodies[0].requestId,createBodies[1].requestId);report.checks.push('a lost create response is retried with the same durable request identity');lostCreate.stop();
const boundStart=new TravelRuntime();boundStart.publish({snapshot:{workflow:{id:'ready-trip'},plan:{contentHash:'e'.repeat(64),activationRevision:7}}});const starts=[];handler=async body=>{if(body.operation==='start'){starts.push(body);throw Error('lost response');}return {};};await assert.rejects(boundStart.start());await assert.rejects(boundStart.start());assert.equal(starts[0].requestId,starts[1].requestId);assert.equal(starts[0].hash,'e'.repeat(64));assert.equal(starts[0].revision,7);report.checks.push('execution retries preserve request identity and the confirmed hash/revision');boundStart.stop();
const reopening=new TravelRuntime();const reopened=[];reopening.documentListeners.add(state=>reopened.push(state));handler=async body=>({workflow:{id:body.workflowId,title:'另一个旅行 · 旅行计划',uiKind:'travel',status:'agent_ready',description:'这次的需求'},draft:{_workflowId:body.workflowId,profile:{destination:'另一个旅行',flowCheckpoint:'services'},days:[],entries:{mine:'本任务原话'}}});await reopening.open('other-trip');assert.equal(reopened[0].profile.destination,'另一个旅行');assert.equal(reopened[0].entries.mine,'本任务原话');assert.equal(reopening.profile.destination,'另一个旅行');report.checks.push('opening an unfinished task restores only its bound draft');reopening.stop();

check('three-way adoption preserves final prose and facts while applying user changes',()=>{
 const base=structuredClone(travelDocument),edited=structuredClone(base),final=structuredClone(base);edited.actions[0].title='用户调整名称';edited.actions.reverse();final.journal='最终手记';final.actions[0].status='completed';final.actions[0].actual_end='2026-10-01T12:00:00Z';const merged=mergeTravelEdits(base,edited,final);
 assert.equal(merged.journal,'最终手记');assert.equal(merged.actions[1].title,'用户调整名称');assert.equal(merged.actions[1].status,'completed');assert.equal(merged.actions[1].actual_end,'2026-10-01T12:00:00Z');assert.equal(base.actions[0].title,'第一处风景');
 final.actions[0].title='另一个设备的名称';assert.throws(()=>mergeTravelEdits(base,edited,final),/新的变化/);
});
const adoptingEdits=new TravelRuntime();let adoptedDoc=structuredClone(travelDocument),adoptedHash='a'.repeat(64),adoptedId='before-adopt',adoptedStatus='awaiting_review',editRevision=1;const adoptionCalls=[];
adoptingEdits.document=structuredClone(travelDocument);adoptingEdits.artifactHash=adoptedHash;const adoptedSnapshot=()=>({workflow:{id:'edited-trip',status:adoptedStatus==='completed'?'completed':'ready'},execution:{id:'edited-execution',status:adoptedStatus},artifact:{id:adoptedId,contentHash:adoptedHash},content:JSON.stringify(adoptedDoc)});adoptingEdits.publish({snapshot:adoptedSnapshot()});
handler=async body=>{adoptionCalls.push(body);if(body.operation==='snapshot')return adoptedSnapshot();if(body.operation==='approveOutput'){adoptedStatus='completed';adoptedDoc.journal='采用后的服务端文字';adoptedHash='b'.repeat(64);adoptedId='final-adopt';return {};}if(body.operation==='revise'||body.operation==='saveState'){assert.equal(body.hash,adoptedHash);if(body.operation==='revise')adoptedDoc=JSON.parse(body.content);else adoptedDoc.client_state=body.state;adoptedHash=String(++editRevision).repeat(64);adoptedId='edited-'+editRevision;return {id:adoptedId,contentHash:adoptedHash};}return {saved:true};};
const editState=documentToState(travelDocument);editState.days.reverse();editState.entries={'day-1':'采用前自己的原话'};await adoptingEdits.captureEdits(editState);await adoptingEdits.approveOutput();assert.deepEqual(adoptedDoc.actions.map(a=>a.id),['action-2','action-1']);assert.equal(adoptedDoc.client_state.entries['day-1'],'采用前自己的原话');assert.equal(adoptingEdits.pendingEdits,null);assert.equal(adoptionCalls.filter(c=>c.operation==='revise').length,1);report.checks.push('adoption submits user reorder and writing only after final approval and verified revision receipts');adoptingEdits.stop();
const failingDiscovery=new TravelRuntime();handler=async()=>{throw Error('实际检索失败');};await assert.rejects(failingDiscovery.discover({destination:'青森'},'我要去青森'),/实际检索失败/);assert.equal(failingDiscovery.state.error,'实际检索失败');report.checks.push('discovery keeps the actual backend failure without losing the error in its recovery path');failingDiscovery.stop();
const incompatibleServer=new TravelRuntime();incompatibleServer.preparedDescription='旧的需求';incompatibleServer.publish({snapshot:{workflow:{id:'bound-old',description:'旧的需求',status:'agent_ready'}}});handler=async body=>body.operation==='snapshot'?{workflow:{id:'bound-old',description:'旧的需求',status:'awaiting_approval'}}:{};await assert.rejects(incompatibleServer.prepare({destination:'青森'},'新的需求'),/服务端未保存/);assert.equal(incompatibleServer.state.snapshot.workflow.id,'bound-old');report.checks.push('an older server that ignores full replan inputs cannot start the old brief as a new trip');incompatibleServer.stop();
const noDeviceDraft=new TravelRuntime();let freshState;noDeviceDraft.documentListeners.add(s=>{freshState=s;});handler=async body=>({workflow:{id:body.workflowId,title:'另一个旅行 · 旅行计划',uiKind:'travel',status:'agent_ready',description:'后台确认条件'},draft:null});await noDeviceDraft.open('without-local-draft');assert.deepEqual(freshState.days,[]);assert.equal(freshState.profile.flowCheckpoint,'preferences');assert.equal(freshState.profile.additional,'后台确认条件');report.checks.push('a task without a local preparation draft returns to requirement review without fabricated days or an empty transport crash');noDeviceDraft.stop();

check('transport billing unit beats legacy currency inference and unknown quotes never become zero',()=>{
 const profile={count:'2人',servicePlan:{transport:{car:{name:'整车',kind:'transport',price:100,priceCurrency:'CNY',people:2,priceUnit:'／车'},person:{name:'单程',kind:'transport',price:100,priceCurrency:'CNY',people:2,priceUnit:'／人'},unknown:{name:'待核价',kind:'transport',price:null,priceCurrency:'JPY',people:2,priceUnit:'／人'}}}};
 const rows=plannedEntries(profile);assert.equal(rows.find(r=>r.title==='整车').amount,'100.00');assert.equal(rows.find(r=>r.title==='单程').amount,'200.00');assert.equal(rows.find(r=>r.title==='待核价').amount,'');
});

handler=async()=>({hasActions:false,answer:JSON.stringify({results:[{id:'unpriced-flight',name:'公开班次',source_url:'https://example.org/flight',checked_at:'2026-10-01',date:'2026-11-01',time:'08:30',arrivalDate:'2026-11-01',arrival:'12:30',duration:180,from:'上海',to:'青森',price:null,stops:null}]})});await searchServices('flight',{origin:'上海',destination:'青森',date:'2026-11-01'});assert.equal(serviceCache.flights.length,1);assert.equal(serviceCache.flights[0].price,null);assert.equal(serviceCache.flights[0].stops,null);report.checks.push('an unpriced public flight schedule remains selectable without invented fare or transfer count');

check('unselected day alternatives remain references and survive notebook edits without becoming trip days',()=>{
 const source={...structuredClone(travelDocument),days:[{id:'day-1',title:'当前安排',selected:true},{id:'day-2',title:'备选安排',selected:false}]};
 const state=documentToState(source);assert.equal(state.days.length,1);assert.equal(state.profile.alternativeDays[0].id,'day-2');
 const exported=stateToDocument(source,state.days,state.profile);assert.deepEqual(exported.actions.find(a=>a.day_id==='day-2'),source.actions[1]);assert.equal(exported.days.find(d=>d.id==='day-2').selected,false);
});
