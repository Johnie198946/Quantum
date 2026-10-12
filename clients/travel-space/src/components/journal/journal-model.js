import {normalizePlan,reservations,recordState} from '../services/planning';
import {notesForDay} from '../trail-notes';

export const timeValue=value=>/^([01]\d|2[0-3]):[0-5]\d$/.test(value||'')?Number(value.slice(0,2))*60+Number(value.slice(3)):NaN;
export const itemKey=(day,item,index)=>item.journalId||item.action_id||item.id||`${day.id}-item-${index}`;
export const stableItems=day=>day.items.map((item,index)=>({...item,journalId:itemKey(day,item,index)}));
const comparable=item=>item&&JSON.stringify([item.time,item.endTime||'',item.title,item.description||'']);
export function scheduleIssues(items){
 const issues=[];
 for(const [index,item] of items.entries()){
  if(!item.title?.trim())issues.push(`安排${index+1}需要填写名称。`);
  if(!Number.isFinite(timeValue(item.time)))issues.push(`安排${index+1}需要有效开始时间。`);
  if(item.endTime&&(!Number.isFinite(timeValue(item.endTime))||timeValue(item.endTime)<=timeValue(item.time)))issues.push(`安排${index+1}的结束时间应晚于开始。`);
 }
 const ordered=[...items].sort((a,b)=>timeValue(a.time)-timeValue(b.time));
 for(let i=1;i<ordered.length;i++)if(timeValue(ordered[i].time)<timeValue(ordered[i-1].endTime||ordered[i-1].time)+15)issues.push(`“${ordered[i-1].title}”与“${ordered[i].title}”之间至少留15分钟。`);
 if(!items.length)issues.push('至少保留一项安排；可以填写自由休息。');
 return [...new Set(issues)];
}
export function reviseDay(day,nextItems,{source='整体编辑',reason='调整当天安排',id=globalThis.crypto?.randomUUID?.()||String(Date.now()),now=Date.now()}={}){
 const before=stableItems(day),after=nextItems.map((item,index)=>({...item,journalId:item.journalId||`${day.id}-new-${id}-${index}`,title:item.title.trim()})).sort((a,b)=>timeValue(a.time)-timeValue(b.time));
 const keys=new Set([...before,...after].map(x=>x.journalId)),changes=[];
 for(const key of keys){const a=before.find(x=>x.journalId===key),b=after.find(x=>x.journalId===key);if(comparable(a)!==comparable(b))changes.push({key,before:a||null,after:b||null});}
 if(!changes.length)return {...day,items:after};
 return {...day,items:after,journalRevisions:[...(day.journalRevisions||[]),{id,source,reason,at:now,beforeItems:before,afterItems:after,changes,undone:false}]};
}
export const latestRevision=day=>[...(day.journalRevisions||[])].reverse().find(r=>!r.undone);
export function undoDayRevision(day){const revision=latestRevision(day);if(!revision||JSON.stringify(stableItems(day))!==JSON.stringify(revision.afterItems))return null;return {...day,items:revision.beforeItems,journalRevisions:day.journalRevisions.map(r=>r.id===revision.id?{...r,undone:true}:r)};}
export function journalServices(day,days,profile){
 const plan=normalizePlan(profile.servicePlan),notes=notesForDay(day),all=reservations(plan).filter(r=>r.dayId===day.id),overrides=day.journalServices||{};
 return [['transport','交通','car','路程与衔接',notes.transport],['hotel','住宿','bed','今晚，在哪里休息',notes.stay],['restaurant','饮食','dining','一天的三顿饭',notes.food],['activity','特色玩法','ticket','留一点特别的体验',notes.play]].map(([kind,label,icon,heading,fallback])=>{
  const rows=all.filter(r=>r.kind===kind||(kind==='transport'&&r.kind==='flight')).map(r=>({...r,state:recordState(r,day,days,plan)}));
  return {kind,label,icon,heading,rows,text:overrides[kind]||fallback||label+'安排尚未补充。',custom:!!overrides[kind],missingMeals:kind==='restaurant'?['早餐','午餐','晚餐'].filter(meal=>!rows.some(r=>String(r.key||'').endsWith('-'+meal)||r.name.includes(meal))):[]};
 });
}
export function notesDraft(text,existing=''){
 if(/^(请|帮我)?(整理笔记|整理一下|只整理我说过的内容[，,]保留原来的记录)[。！]?$/u.test(text.trim()))return existing.trim();
 const clean=text.trim().replace(/^(请|帮我)?(整理成笔记|整理笔记|记一下|记录一下|帮我记录)[：:\s]*/,'').replace(/\n{3,}/g,'\n\n').replace(/[，,]?想把这一刻记下来[。！]?$/,'。');
 if(!clean)return '';
 return [existing.trim(),clean].filter(Boolean).join('\n\n');
}
export function itinerarySuggestion(text,day,targetKey){
 const items=stableItems(day),times=text.match(/(?:[01]?\d|2[0-3]):[0-5]\d/g)||[];
 const normalizeTime=t=>t.length===4?'0'+t:t;
 const matched=items.find(x=>text.includes(x.title))||items.find(x=>times.length>1&&x.time===normalizeTime(times[0]));
 const before=matched||items.find(x=>x.journalId===targetKey)||items.at(-1);
 const replacement=text.match(/(?:换成|改成|改为|换为)\s*(.+)/)?.[1]?.replace(/[。；;].*$/,'').replace(/(?:[01]?\d|2[0-3]):[0-5]\d/g,'').replace(/^(的|去|到|为|\s)+/,'').trim();
 const rest=/轻松|休息|慢一点|不爬|不想走|减少|留白/.test(text);
 if(!before||!replacement&&!times.length&&!rest)return null;
 return {before,after:{...before,time:times.length?normalizeTime(times.at(-1)):before.time,endTime:'',title:replacement||(rest?'自由休息':before.title),description:rest?'留出自由时间，停留位置与交通另行确认。':before.description,status:'待开始'},reason:text.trim()};
}
export function pendingDay(day,proposal){return {...day,items:stableItems(day).map(x=>x.journalId===proposal.before.journalId?proposal.after:x)};}
export function formatRevisionDate(value){return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value));}
