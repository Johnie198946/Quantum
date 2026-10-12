// Local lifecycle facts are separate from the itinerary, journal and expense ledger.
export const PROGRESS_STATUSES=['planned','delayed','in_progress','completed','skipped','cancelled'];
const statuses=new Set(PROGRESS_STATUSES),terminal=new Set(['completed','skipped','cancelled']);
const object=value=>value&&typeof value==='object'&&!Array.isArray(value)?value:{};
const clone=value=>JSON.parse(JSON.stringify(value));
const own=(value,key)=>Object.prototype.hasOwnProperty.call(value,key);
export const isoDate=value=>{if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;const epoch=Date.parse(value+'T12:00:00Z');return Number.isFinite(epoch)&&new Date(epoch).toISOString().slice(0,10)===value;};
export const offsetTimestamp=value=>typeof value==='string'&&isoDate(value.slice(0,10))&&/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d+)?)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.test(value)&&Number.isFinite(Date.parse(value));
const canonical=value=>statuses.has(value)?value:'planned';
export const activityId=(day,item,index=0)=>String(item.journalId||item.action_id||item.id||day.id+'-item-'+index);
export const stableTripItems=day=>(day.items||[]).map((item,index)=>({...item,journalId:activityId(day,item,index)}));
const freeze=value=>{if(value&&typeof value==='object'&&!Object.isFrozen(value)){Object.values(value).forEach(freeze);Object.freeze(value);}return value;};
function withoutPrivate(value){
 if(Array.isArray(value))return value.map(withoutPrivate).filter(item=>item!==undefined);
 if(typeof value==='string'&&/^data:/i.test(value))return undefined;
 if(!value||typeof value!=='object')return value;
 const excluded=new Set(['image','images','imageData','media','attachments','journalRecords','journalChats','readerAnnotations','budgetLedger','entries','journalRevisions','actual_start','actual_end','actualStart','actualEnd','completed','tripSession']);
 return Object.fromEntries(Object.entries(value).filter(([key])=>!excluded.has(key)).map(([key,item])=>[key,withoutPrivate(item)]).filter(([,item])=>item!==undefined));
}
function planDay(day){
 const result={};for(const key of ['id','order','date','dateISO','name','place','geo','timezone'])if(own(day,key))result[key]=withoutPrivate(day[key]);
 result.items=stableTripItems(day).map(item=>{const next=withoutPrivate(item);delete next.status;return next;});return result;
}
function baselineOf(profile,days,createdAt){return freeze({createdAt,destination:profile.destination||'',days:days.map(planDay),servicePlan:withoutPrivate(object(profile.servicePlan))});}
function factOf(value){
 if(!value||typeof value!=='object'||Array.isArray(value))return null;
 const fact=object(value),status=canonical(fact.status),start=offsetTimestamp(fact.actual_start)?fact.actual_start:null,end=offsetTimestamp(fact.actual_end)?fact.actual_end:null;
 if(status==='in_progress'&&!start||status==='completed'&&!end||start&&end&&Date.parse(end)<Date.parse(start))return null;
 return {...fact,status,actual_start:start,actual_end:end};
}
export function normalizeSession(profile={},days=[]){
 const source=object(profile.tripSession),facts={},invalidFacts=[];
 for(const [key,value] of Object.entries(object(source.facts))){const fact=factOf(value);if(fact)facts[key]=fact;else invalidFacts.push(key);}
 // Canonical backend progress is accepted; draft day.completed and Chinese labels are not visit facts.
 for(const day of days)for(const [index,item] of (day.items||[]).entries()){
  const key=activityId(day,item,index);if(!own(facts,key)&&statuses.has(item.status)&&item.status!=='planned'){
   const fact=factOf({...item,action_id:key,day_id:day.id,title:item.title});if(fact)facts[key]={action_id:key,day_id:day.id,title:item.title,status:fact.status,actual_start:fact.actual_start,actual_end:fact.actual_end};else invalidFacts.push(key);
  }
 }
 const active=days.find(day=>String(day.id)===String(source.activeDayId));
 const baseline=source.baseline&&Array.isArray(source.baseline.days)?freeze(withoutPrivate(clone(source.baseline))):null;
 return {...source,version:1,phase:['before','during','after'].includes(source.phase)?source.phase:'before',activeDayId:active?.id??days[0]?.id??null,baseline,facts,events:Array.isArray(source.events)?source.events.filter(event=>event&&typeof event.id==='string'&&offsetTimestamp(event.happened_at)).map(event=>({...event})):[],checks:{...object(source.checks),...(invalidFacts.length?{invalidFacts:[...new Set(invalidFacts)]}:{})},recap:{...object(source.recap)}};
}
function timestamp(at=Date.now()){
 let value;try{value=typeof at==='string'?at:new Date(at).toISOString();}catch{throw new Error('需要带时区的有效实际时间。');}
 if(!offsetTimestamp(value))throw new Error('需要带时区的有效实际时间。');
 if(Date.parse(value)>Date.now())throw new Error('实际时间不能在未来。');return value;
}
function uniqueItems(days){const ids=new Set();for(const day of days)for(const item of stableTripItems(day)){if(ids.has(item.journalId))throw new Error('活动编号重复，请先核对行程。');ids.add(item.journalId);}}
export function beginTrip(profile,days,at=Date.now()){
 const happenedAt=timestamp(at),nextDays=days.map(day=>({...day,items:stableTripItems(day)}));uniqueItems(nextDays);
 const session=normalizeSession(profile,nextDays);if(session.phase==='after')throw new Error('这趟旅行已经结束，请保留回顾与实际记录。');
 const next={...session,phase:'during',baseline:session.baseline||baselineOf(profile,nextDays,happenedAt),startedAt:session.startedAt||happenedAt,updatedAt:happenedAt};
 return {profile:{...profile,tripSession:next},days:nextDays};
}
export function statusOf(profile,item){
 const key=String(item.journalId||item.action_id||item.id||''),fact=factOf(object(profile.tripSession).facts?.[key]);
 if(fact)return fact.status;const imported=factOf(item);return imported?imported.status:'planned';
}
export function currentAction(profile,day){const items=stableTripItems(day);return items.find(item=>statusOf(profile,item)==='in_progress')||items.find(item=>['planned','delayed'].includes(statusOf(profile,item)))||null;}
export function recordProgress(profile,day,actionId,status,at=Date.now()){
 const happenedAt=timestamp(at),items=stableTripItems(day),item=items.find(item=>item.journalId===String(actionId));
 if(!item)throw new Error('这项活动已不存在，请重新打开这一天。');if(!statuses.has(status))throw new Error('活动状态无效。');
 const session=normalizeSession(profile,[day]);if(session.phase!=='during')throw new Error('请先开始旅行，再记录实际进度。');
 const previous=session.facts[item.journalId]||factOf(item)||{status:'planned',actual_start:null,actual_end:null};
 if(previous.status===status)throw new Error('这个状态已经记录，请勿重复。');if(terminal.has(previous.status))throw new Error('已完成、跳过或取消的实际记录不能重写。');
 if(status==='planned'&&previous.status!=='delayed'||previous.status==='in_progress'&&!['completed','cancelled'].includes(status))throw new Error('不能把已经开始的活动改成尚未开始。');
 const previousAt=[previous.actual_start,previous.actual_end,...session.events.filter(event=>event.action_id===item.journalId).map(event=>event.happened_at)].filter(offsetTimestamp).map(Date.parse);
 if(previousAt.some(value=>value>Date.parse(happenedAt)))throw new Error('实际进度时间不能早于已有记录。');
 const fact={action_id:item.journalId,day_id:day.id,title:item.title,status,actual_start:status==='in_progress'?happenedAt:previous.actual_start||null,actual_end:status==='completed'||status==='cancelled'&&previous.actual_start?happenedAt:previous.actual_end||null};
 const id=globalThis.crypto?.randomUUID?.()||'event-'+Date.now()+'-'+session.events.length;
 return {...profile,tripSession:{...session,activeDayId:day.id,facts:{...session.facts,[item.journalId]:fact},events:[...session.events,{id,action_id:item.journalId,day_id:day.id,happened_at:happenedAt,status,previous_status:previous.status}],updatedAt:happenedAt}};
}
export function finishTrip(profile,at=Date.now()){
 const happenedAt=timestamp(at),session=normalizeSession(profile,[]);if(session.phase!=='during')throw new Error('只有进行中的旅行可以结束。');
 if(session.startedAt&&Date.parse(happenedAt)<Date.parse(session.startedAt))throw new Error('结束时间不能早于开始时间。');
 return {...profile,tripSession:{...session,activeDayId:object(profile.tripSession).activeDayId??session.activeDayId,phase:'after',finishedAt:happenedAt,updatedAt:happenedAt}};
}
// Resolve a local clock only when both its calendar date and IANA timezone are known.
export function localEpoch(date,time,zone){
 if(!isoDate(date)||!/^([01]\d|2[0-3]):[0-5]\d$/.test(time||'')||typeof zone!=='string'||!zone)return null;
 try{
  const formatter=new Intl.DateTimeFormat('en-GB',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}),target=Date.parse(date+'T'+time+':00Z');let guess=target;
  for(let i=0;i<4;i++){const parts=Object.fromEntries(formatter.formatToParts(guess).filter(part=>part.type!=='literal').map(part=>[part.type,part.value]));const actual=Date.parse(parts.year+'-'+parts.month+'-'+parts.day+'T'+parts.hour+':'+parts.minute+':'+parts.second+'Z');guess+=target-actual;}
  const parts=Object.fromEntries(formatter.formatToParts(guess).filter(part=>part.type!=='literal').map(part=>[part.type,part.value]));return parts.year+'-'+parts.month+'-'+parts.day===date&&parts.hour+':'+parts.minute===time?guess:null;
 }catch{return null;}
}
function plannedAt(profile,day,item){
 const date=day.dateISO,zone=item.timezone||day.timezone||object(profile.tripSession).timeZone||profile.timezone;
 if(offsetTimestamp(item.start)){if(item.time&&item.time!==item.start.slice(11,16))return localEpoch(date||item.start.slice(0,10),item.time,zone);return Date.parse(item.start);}
 return localEpoch(date,item.time,zone);
}
function semantic(item){const result=withoutPrivate(item);delete result.actual_start;delete result.actual_end;if(result.journalId)delete result.id;return JSON.stringify(Object.keys(result).sort().map(key=>[key,result[key]]));}
export function validateRemainingChange(profile,day,nextItems){
 if(!Array.isArray(nextItems))return ['请提供完整的剩余安排。'];const issues=[],before=stableTripItems(day),after=nextItems.map((item,index)=>({...item,journalId:activityId(day,item,index)})),keys=new Set(),now=Date.now();
 for(const item of after){if(keys.has(item.journalId))issues.push('活动编号重复，不能采用这份修改。');keys.add(item.journalId);}
 const session=normalizeSession(profile,[day]);
 for(const old of before){
  const next=after.find(item=>item.journalId===old.journalId),fact=session.facts[old.journalId]||factOf(old)||{status:'planned'},status=fact.status,start=plannedAt(profile,day,old),elapsed=status==='planned'&&start!==null&&start<=now;
  if((terminal.has(status)||old.locked||elapsed)&&(!next||semantic(next)!==semantic(old))){issues.push('“'+old.title+'”已成为实际、锁定或已过时的安排，不能覆盖。');continue;}
  if(!next){if(status==='in_progress')issues.push('“'+old.title+'”已经开始，需要保留实际记录。');if(old.booking_reference)issues.push('“'+old.title+'”已有预订凭据，请先明确处理预订。');continue;}
  if(next.booking_reference!==old.booking_reference)issues.push('“'+old.title+'”的预订凭据不能随行程修改。');
  const candidateStatus=canonical(next.status),oldStatus=canonical(old.status);
  if(candidateStatus!==oldStatus||['actual_start','actual_end'].some(key=>(next[key]??null)!==(old[key]??null)))issues.push('不能通过修改计划编造“'+old.title+'”的实际进度。');
  if(status==='in_progress'){
   const frozen=['time','start','place_id','kind','day_id','locked','booking_reference','from_place_id'];
   if(frozen.some(key=>JSON.stringify(next[key])!==JSON.stringify(old[key])))issues.push('“'+old.title+'”已经开始，实际开始与出发信息需要保留。');
   const end=offsetTimestamp(next.end)?Date.parse(next.end):localEpoch(day.dateISO,next.endTime,next.timezone||day.timezone);
   if(end!==null&&end<now)issues.push('正在进行的安排不能把剩余结束时间设在过去。');
  }
  const nextStart=plannedAt(profile,day,next);if(semantic(next)!==semantic(old)&&status!=='in_progress'&&nextStart!==null&&nextStart<now)issues.push('修改后的“'+next.title+'”不能新增过去的出发时间。');
 }
 for(const item of after.filter(next=>!before.some(old=>old.journalId===next.journalId))){
  if(canonical(item.status)!=='planned'||item.actual_start||item.actual_end||item.booking_reference)issues.push('新安排不能附带编造的实际进度或预订凭据。');
  const start=plannedAt(profile,day,item);if(start!==null&&start<now)issues.push('新安排不能插入过去的出发时间。');
 }
 return [...new Set(issues)];
}
export function summaryFacts(profile={},days=[]){
 const byStatus=Object.fromEntries(PROGRESS_STATUSES.map(status=>[status,0])),seen=new Set();
 for(const day of days)for(const item of stableTripItems(day)){if(seen.has(item.journalId))continue;seen.add(item.journalId);byStatus[statusOf(profile,item)]++;}
 const recordRefs=[];for(const [dayId,records] of Object.entries(object(profile.journalRecords)))for(const [index,record] of (Array.isArray(records)?records:[]).entries())if(record&&((typeof record.text==='string'&&record.text.trim())||record.media?.length))recordRefs.push({id:record.id||dayId+'-record-'+index,dayId:days.find(day=>String(day.id)===dayId)?.id??dayId,text:record.text||'',at:record.at??null,mediaCount:Array.isArray(record.media)?record.media.length:0});
 const changed=days.filter(day=>(day.journalRevisions||[]).some(revision=>revision.changes?.length)),activeChanged=days.filter(day=>(day.journalRevisions||[]).some(revision=>!revision.undone&&revision.changes?.length));
 return {total:seen.size,completed:byStatus.completed,skipped:byStatus.skipped,cancelled:byStatus.cancelled,unfinished:byStatus.planned+byStatus.delayed+byStatus.in_progress,byStatus,records:recordRefs.length,recordDayIds:[...new Set(recordRefs.map(record=>record.dayId))],recordRefs,changedDays:changed.length,activeChangedDays:activeChanged.length,changeCount:days.reduce((count,day)=>count+(day.journalRevisions||[]).filter(revision=>revision.changes?.length).length,0)};
}
