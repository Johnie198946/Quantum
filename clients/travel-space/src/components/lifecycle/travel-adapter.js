// Boundary for backend/services/travel_plan.py schema v2. Workflow owns validation,
// revisions and persistence; this adapter neither invokes APIs nor exports private journals.
import {activityId,isoDate,localEpoch,offsetTimestamp,PROGRESS_STATUSES} from './trip-model.js';

const clone=value=>JSON.parse(JSON.stringify(value));
const owns=(value,key)=>Object.prototype.hasOwnProperty.call(value,key);
const kinds=new Set(['experience','transport','meal','hotel','rest','photography']);
const statuses=new Set(PROGRESS_STATUSES);
const actionKeys=['id','day_id','title','kind','place_id','start','end','timezone','status','actual_start','actual_end','locked','details','booking_reference','from_place_id','to_place_id','source_ids'];
const privateKeys=['budgetLedger','journalRecords','journalChats','readerAnnotations','entries','tripSession'];
const localStamp=(value,zone)=>{
 if(!offsetTimestamp(value))return null;
 if(!zone)return value.slice(0,16);
 try{const parts=Object.fromEntries(new Intl.DateTimeFormat('sv-SE',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date(value)).map(p=>[p.type,p.value]));return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;}catch{return null;}
};
const clock=(value,zone)=>localStamp(value,zone)?.slice(11,16)||'';
function zoneKnown(zone){try{new Intl.DateTimeFormat('en',{timeZone:zone});return typeof zone==='string'&&!!zone;}catch{return false;}}
function checkDocument(document){
 if(!document||document.schema_version!==2||typeof document.destination!=='string'||!document.destination.trim())throw new Error('需要有效的 travel_plan v2 文档。');
 const lists=['stops','actions','sources','photo_references'];for(const key of lists){if(owns(document,key)&&!Array.isArray(document[key]))throw new Error(key+' 必须是列表。');const ids=new Set();for(const item of document[key]||[]){if(!item||typeof item.id!=='string'||!item.id.trim()||ids.has(item.id))throw new Error('旅行文档编号缺失或重复。');ids.add(item.id);}}
 const places=new Set((document.stops||[]).map(item=>item.id)),sources=new Set((document.sources||[]).map(item=>item.id));
 for(const stop of document.stops||[]){const lat=stop.latitude??null,lng=stop.longitude??null;if((lat===null)!==(lng===null)||lat!==null&&(!Number.isFinite(lat)||!Number.isFinite(lng)||Math.abs(lat)>90||Math.abs(lng)>180))throw new Error('地点需要一对有效坐标，或保留未知。');if((stop.source_ids||[]).some(id=>!sources.has(id)))throw new Error('地点引用了未知来源。');}
 for(const action of document.actions||[]){
  if(Object.keys(action).some(key=>!actionKeys.includes(key))||typeof action.day_id!=='string'||!action.day_id.trim()||typeof action.title!=='string'||!action.title.trim()||!kinds.has(action.kind)||!statuses.has(action.status||'planned'))throw new Error('活动不符合 travel_plan v2 字段。');
  if(!zoneKnown(action.timezone||'UTC'))throw new Error('活动时区未知。');
  for(const key of ['start','end','actual_start','actual_end'])if(action[key]!=null&&!offsetTimestamp(action[key]))throw new Error('旅行时间需要有效的 UTC 偏移。');
  for(const [start,end] of [['start','end'],['actual_start','actual_end']])if(action[start]&&action[end]&&Date.parse(action[end])<Date.parse(action[start]))throw new Error('到达时间不能早于出发时间。');
  if(action.status==='in_progress'&&!action.actual_start||action.status==='completed'&&!action.actual_end)throw new Error('实际进度缺少实际时间。');
  if(['place_id','from_place_id','to_place_id'].some(key=>action[key]&&!places.has(action[key]))||(action.source_ids||[]).some(id=>!sources.has(id)))throw new Error('活动引用了未知地点或来源。');
 }
 for(const photo of document.photo_references||[])if(!sources.has(photo.source_id)||photo.place_id&&!places.has(photo.place_id))throw new Error('照片引用了未知地点或来源。');
 return document;
}

export function importTravelDocument(document){
 const original=clone(checkDocument(document)),byDay=new Map(),places=new Map((original.stops||[]).map(stop=>[stop.id,stop]));
 for(const action of original.actions||[]){
  if(!byDay.has(action.day_id))byDay.set(action.day_id,[]);
  byDay.get(action.day_id).push({...action,journalId:action.id,time:clock(action.start,action.timezone),endTime:clock(action.end,action.timezone),description:action.details||''});
 }
 const days=[...byDay].map(([id,items],index)=>{
  const first=items[0],dated=items.find(item=>offsetTimestamp(item.start)),dateISO=dated?localStamp(dated.start,dated.timezone)?.slice(0,10)||null:null,stop=places.get(first.place_id)||places.get(first.from_place_id);
  return {id,order:index+1,name:first.title,place:stop?.name||original.destination,date:dateISO?Number(dateISO.slice(5,7))+'月'+Number(dateISO.slice(8,10))+'日':'日期未定',dateISO,timezone:first.timezone||'UTC',geo:stop?.latitude!=null&&stop?.longitude!=null?{lat:stop.latitude,lon:stop.longitude}:null,items};
 });
 const profileFields={destination:original.destination,travelDocument:original};
 if(owns(original,'budget'))profileFields.budget=original.budget;
 if(owns(original,'companions'))profileFields.count=original.companions==null?'':original.companions+'人';
 if(owns(original,'style'))profileFields.pace=original.style;
 // Preserve the original date_range verbatim. A year is never inferred from display labels.
 if(owns(original,'date_range'))profileFields.travelDateRange=original.date_range;
 return {profileFields,days};
}

function zonedTimestamp(date,time,zone){
 const epoch=localEpoch(date,time,zone);if(epoch===null)return null;
 const wall=Date.parse(date+'T'+time+':00Z'),offset=(wall-epoch)/60000,sign=offset<0?'-':'+',absolute=Math.abs(offset);
 return date+'T'+time+':00'+sign+String(Math.floor(absolute/60)).padStart(2,'0')+':'+String(absolute%60).padStart(2,'0');
}
function plannedTime(item,day,key,displayKey,original){
 const raw=item[key]??null,display=item[displayKey];
 if(owns(item,displayKey)){
  if(!display)return null;
  const zone=item.timezone||day.timezone||original.timezone;const base=localStamp(original.start||original.end,zone)?.slice(0,10);
  if(display===clock(raw,zone)&&(!day.dateISO||day.dateISO===base||day.dateISO===localStamp(raw,zone)?.slice(0,10)))return raw;
  let date=isoDate(day.dateISO)?day.dateISO:offsetTimestamp(raw)?localStamp(raw,zone)?.slice(0,10):null;
  if(isoDate(day.dateISO)&&isoDate(base)&&offsetTimestamp(raw)){const difference=(Date.parse(localStamp(raw,zone).slice(0,10)+'T12:00:00Z')-Date.parse(base+'T12:00:00Z'))/86400000;date=new Date(Date.parse(date+'T12:00:00Z')+difference*86400000).toISOString().slice(0,10);}
  if(!date)return null;
  const timestamp=zonedTimestamp(date,display,item.timezone||day.timezone||original.timezone||'UTC');
  if(timestamp===null)throw new Error('日期、时间或时区无法确定，请先补齐计划时间。');
  return timestamp;
 }
 return raw;
}
export function exportTravelDocument(profile,days,original=profile.travelDocument){
 const source=clone(checkDocument(original)),document={...source};for(const key of privateKeys)delete document[key];
 for(const [frontend,backend] of [['destination','destination'],['budget','budget'],['pace','style'],['travelDateRange','date_range']])if(owns(profile,frontend))document[backend]=profile[frontend];
 if(owns(profile,'count')){const raw=profile.count,value=typeof raw==='number'?raw:/^\s*\d+\s*(?:人)?\s*$/.test(raw||'')?Number(String(raw).replace(/人/g,'').trim()):null;if(value===null&&raw)throw new Error('同行人数需要明确的整数。');if(value!==null&&(!Number.isInteger(value)||value<1||value>1000))throw new Error('同行人数超出旅行文档范围。');document.companions=value;}
 const old=new Map((source.actions||[]).map(action=>[action.id,action])),items=[];
 for(const day of days)for(const [index,item] of (day.items||[]).entries()){
  const id=activityId(day,item,index),previous=old.get(id),defaults={id,day_id:String(day.id),title:item.title,kind:'experience',place_id:null,start:null,end:null,timezone:item.timezone||day.timezone||'UTC',status:'planned',actual_start:null,actual_end:null,locked:false,details:'',booking_reference:'',from_place_id:null,to_place_id:null,source_ids:[]},action={...(previous||defaults)};
  const values={...item,id,day_id:String(day.id),status:statuses.has(item.status)?item.status:action.status||'planned',details:owns(item,'description')?item.description:item.details??action.details,start:plannedTime(item,day,'start','time',action),end:plannedTime(item,day,'end','endTime',action)};
  for(const key of actionKeys)if(owns(values,key)&&(owns(action,key)||JSON.stringify(values[key])!==JSON.stringify(defaults[key])))action[key]=clone(values[key]);
  // Local facts are exported only as explicit user progress; journals and ledger never enter the plan.
  const fact=profile.tripSession?.facts?.[id];if(fact){action.status=fact.status;action.actual_start=fact.actual_start??null;action.actual_end=fact.actual_end??null;}
  items.push(action);
 }
 // Keep canonical action order when no structural changes were made by the user.
 const grouped=new Map();for(const action of source.actions||[]){if(!grouped.has(action.day_id))grouped.set(action.day_id,[]);grouped.get(action.day_id).push(action.id);}
 const unchanged=JSON.stringify(items.map(a=>a.id))===JSON.stringify([...grouped.values()].flat());
 const rank=new Map((source.actions||[]).map((action,index)=>[action.id,index]));document.actions=unchanged?items.slice().sort((a,b)=>rank.get(a.id)-rank.get(b.id)):items;
 if(Array.isArray(source.days))document.days=days.map(day=>{const metadata=source.days.find(d=>String(d.id)===String(day.id))||{id:String(day.id)};return {...metadata,...(day.name!==undefined?{title:day.name}:{})};});
 return checkDocument(document);
}
