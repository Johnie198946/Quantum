import {normalizeSession,stableTripItems} from './trip-model.js';

export const preparationCategories=[{id:'documents',title:'证件与随身物品',icon:'bag'},{id:'bookings',title:'预订与接驳',icon:'ticket'},{id:'conditions',title:'天气与待确认信息',icon:'sun'}];
const text=value=>typeof value==='string'?value.trim():'';
const hash=value=>{let result=2166136261;for(const character of JSON.stringify(value)){result^=character.codePointAt(0);result=Math.imul(result,16777619);}return (result>>>0).toString(16);};
const questionText=value=>text(value)||text(value?.question)||text(value?.text)||text(value?.title);
const categoryOf=value=>/证件|护照|签证|入境|保险|药|行李/.test(value)?'documents':/预订|预约|接驳|班次|航班|机场|车站|渡轮|船|住宿|餐厅|餐饮|票|交通/.test(value)?'bookings':'conditions';

// Suggestions are reminders about this plan; booked or paid flags never complete a reminder.
export function preparationMemos(profile={},days=[]){
 const checks=normalizeSession(profile,days).checks,states=checks.preparationStates||{},rows=[];
 const add=(category,value,key,question=false)=>{const title=text(value);if(!title)return;const id='need-'+key+'-'+hash(title);if(!rows.some(row=>row.id===id))rows.push({id,category,text:title,source:'trip',question,done:typeof states[id]==='boolean'?states[id]:!checks.preparationStates&&!!checks.preparation?.[category]});};
 if(text(profile.destination))add('documents','确认前往'+profile.destination+'需携带的证件与随身物品','destination');
 for(const [kind,group] of Object.entries(profile.servicePlan||{})){
  if(!['flights','transport','hotel','restaurant','activity'].includes(kind)||!group||Array.isArray(group))continue;
  for(const [key,record] of Object.entries(group))if(record&&typeof record==='object'){
   const name=text(record.name)||text(record.title)||({flights:'航班',transport:'交通',hotel:'住宿',restaurant:'餐厅',activity:'体验'}[kind]);
   add('bookings','核对'+name+(text(record.time)?' · '+record.time:'')+'的时间、地点与凭据',kind+'-'+key);
  }
 }
 for(const day of days){
  const items=stableTripItems(day);
  for(const item of items){
   if(item.kind==='transport'||/前往|接驳|机场|车站|渡轮/.test(item.title||''))add('bookings','确认'+(item.title||'交通安排')+'的出发地点与衔接时间',String(day.id)+'-'+item.journalId);
   if(/散步|徒步|登山|森林|火山|观景|海边/.test((item.title||'')+' '+(item.description||item.details||'')))add('conditions','查看'+(item.title||day.place||'当天活动')+'当天的天气与开放情况',String(day.id)+'-'+item.journalId);
  }
 }
 for(const question of Array.isArray(profile.travelDocument?.open_questions)?profile.travelDocument.open_questions:[]){const value=questionText(question);add(categoryOf(value),value,'question-'+(question?.id||hash(value)),true);}
 for(const memo of Array.isArray(checks.preparationMemos)?checks.preparationMemos:[])if(preparationCategories.some(category=>category.id===memo.category)&&text(memo.text)&&text(memo.id)&&!rows.some(row=>row.id===memo.id))rows.push({...memo,text:text(memo.text),source:'user',done:!!memo.done});
 return preparationCategories.map(category=>({...category,memos:rows.filter(row=>row.category===category.id)}));
}

export function updatePreparation(profile,days,ids,done){
 const session=normalizeSession(profile,days),checks=session.checks,selected=new Set(ids),states={...checks.preparationStates};
 const categories=preparationMemos(profile,days);
 for(const category of categories)for(const memo of category.memos){if(typeof states[memo.id]!=='boolean')states[memo.id]=memo.done;if(selected.has(memo.id))states[memo.id]=!!done;}
 const memos=(checks.preparationMemos||[]).map(memo=>selected.has(memo.id)?{...memo,done:!!done}:memo);
 const preparation={...checks.preparation};
 for(const category of categories)if(category.memos.some(memo=>selected.has(memo.id)))preparation[category.id]=category.memos.length>0&&category.memos.every(memo=>selected.has(memo.id)?!!done:memo.done);
 return {...profile,tripSession:{...session,checks:{...checks,preparationStates:states,preparationMemos:memos,preparation}}};
}

export function addPreparationMemo(profile,days,category,value,{id=globalThis.crypto?.randomUUID?.(),now=Date.now()}={}){
 if(!preparationCategories.some(row=>row.id===category)||!text(value))throw new Error('选择分类并填写备忘。');
 const session=normalizeSession(profile,days),memos=session.checks.preparationMemos||[];
 if(memos.length>=100)throw new Error('已保存100条备忘，请先整理现有项目。');
 if(!id||memos.some(memo=>memo.id===id))throw new Error('这条备忘的编号已存在。');
 const preparationStates={...session.checks.preparationStates};for(const group of preparationMemos(profile,days))for(const memo of group.memos)if(typeof preparationStates[memo.id]!=='boolean')preparationStates[memo.id]=memo.done;
 return {...profile,tripSession:{...session,checks:{...session.checks,preparationStates,preparation:{...session.checks.preparation,[category]:false},preparationMemos:[...memos,{id,category,text:text(value).slice(0,500),source:'user',done:false,at:now}]}}};
}

export function changeHistory(day){
 return (Array.isArray(day?.journalRevisions)?day.journalRevisions:[]).filter(revision=>Array.isArray(revision.changes)&&revision.changes.length).map(revision=>({id:revision.id,at:revision.at,undone:!!revision.undone,changes:revision.changes.map(change=>({id:change.key,before:change.before?{title:change.before.title,time:change.before.time,description:change.before.description}:null,after:change.after?{title:change.after.title,time:change.after.time,description:change.after.description}:null}))}));
}

export function tripFragments(profile={},days=[],legacy={}){
 const rows=[];
 for(const day of days){
  const records=Array.isArray(profile.journalRecords?.[day.id])?profile.journalRecords[day.id]:[];
  for(const [index,record] of records.entries())if(record.source!=='trip-summary'&&(text(record.text)||record.media?.length))rows.push({id:record.id||String(day.id)+'-record-'+index,dayId:day.id,dayLabel:day.place||day.name||'旅行当天',text:text(record.text),at:record.source==='legacy-import'?null:record.at??null,mediaCount:Array.isArray(record.media)?record.media.length:0});
  if(!records.length&&text(legacy[day.id]))rows.push({id:'legacy-'+day.id,dayId:day.id,dayLabel:day.place||day.name||'旅行当天',text:text(legacy[day.id]),at:null,mediaCount:0});
 }
 return rows;
}
export function fragmentFingerprint(profile,days,legacy={}){return 'fragments-'+hash([tripFragments(profile,days,legacy),normalizeSession(profile,days).facts,days.map(day=>[day.id,changeHistory(day)])]);}

// Extractive local proposals quote the saved sentence, including its qualifiers and uncertainty.
export function proposeTripSummary(profile,days,legacy={}){
 const fragments=tripFragments(profile,days,legacy),fields=[];
 const categories=[['highlights','想记住的时刻',/喜欢|难忘|最美|很美|值得|开心|好吃|惊喜|感动/],['notes','留给下次的提醒',/注意|提醒|排队|闭馆|没开|取消|绕路|迟到|延误|踩坑/],['nextTime','下次的小期待',/下次|再来|还想|希望|遗憾/]];
 for(const [key,label,pattern] of categories){const evidence=fragments.flatMap(fragment=>fragment.text.split(/(?<=[。！？!?\n])/u).map(value=>value.trim()).filter(value=>value&&pattern.test(value)).map(value=>({recordId:fragment.id,text:value})));if(evidence.length)fields.push({key,label,value:evidence.map(row=>row.text).join('\n'),sourceIds:[...new Set(evidence.map(row=>row.recordId))]});}
 const lines=fragments.filter(fragment=>fragment.text).map(fragment=>fragment.dayLabel+'\n'+fragment.text);
 return {version:1,fingerprint:fragmentFingerprint(profile,days,legacy),sourceIds:fragments.map(fragment=>fragment.id),fields,text:lines.join('\n\n'),mediaCount:fragments.reduce((count,fragment)=>count+fragment.mediaCount,0)};
}

export function confirmTripSummary(profile,days,legacy,proposal,value,{id=globalThis.crypto?.randomUUID?.(),now=Date.now(),factsFingerprint='',fields=proposal?.fields||[]}={}){
 if(!proposal?.sourceIds?.length)throw new Error('先保存一段真实片段，再整理总结。');
 if(proposal.fingerprint!==fragmentFingerprint(profile,days,legacy))throw new Error('原记录已有更新，请重新整理后确认。');
 if(!text(value))throw new Error('写下要保存的总结。');
 if(text(value).length>12000)throw new Error('总结超过12000字，请缩短后保存。');
 const session=normalizeSession(profile,days);
 if(session.recap?.sourceFingerprint===proposal.fingerprint&&session.recap?.text===text(value))throw new Error('这份总结已经写入手记。');
 const day=days.find(day=>String(day.id)===String(session.activeDayId))||days[0];
 if(!day||!id)throw new Error('还没有可以保存总结的旅行日期。');
 const original=Array.isArray(profile.journalRecords?.[day.id])?profile.journalRecords[day.id]:[];
 const records=original.length?original:text(legacy?.[day.id])?[{id:'legacy-'+day.id,text:legacy[day.id],media:[],at:now,source:'legacy-import'}]:[];
 if(records.length>=50)throw new Error('当天记录已满，请先整理后再保存。');
 const record={id,dayId:day.id,text:text(value),media:[],at:now,source:'trip-summary',sourceRecordIds:[...proposal.sourceIds],sourceFingerprint:proposal.fingerprint};
 const nextRecords=[...records,record];
 if(JSON.stringify(profile.journalRecords||{}).length+JSON.stringify(profile.journalChats||{}).length+JSON.stringify(record).length>1800000)throw new Error('记录空间已满，请先保留总结文字。');
 const history=Array.isArray(session.recap?.history)?session.recap.history:[];
 const oldRecap=text(session.recap?.text)&&session.recap.text!==record.text?{text:session.recap.text,updatedAt:session.recap.updatedAt||null,fields:session.recap.fields||{},sourceRecordIds:session.recap.sourceRecordIds||[]}:null;
 const nextProfile={...profile,journalRecords:{...profile.journalRecords,[day.id]:nextRecords},tripSession:{...session,recap:{...session.recap,text:record.text,updatedAt:new Date(now).toISOString(),factsFingerprint,sourceFingerprint:proposal.fingerprint,sourceRecordIds:[...proposal.sourceIds],fields:Object.fromEntries(fields.map(field=>[field.key,{value:field.value,sourceIds:[...field.sourceIds]}])),history:oldRecap?[...history,oldRecap]:history}}};
 return {profile:nextProfile,entries:{...legacy,[day.id]:nextRecords.map(record=>record.text).filter(Boolean).join('\n\n')},record};
}
