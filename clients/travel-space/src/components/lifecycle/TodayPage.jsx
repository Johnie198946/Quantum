import React,{useEffect,useId,useMemo,useRef,useState} from 'react';
import {AnimatePresence,motion,useReducedMotion} from 'motion/react';
import {useTravel} from '../../TravelContext';
import {Icon,Primary,Disclosure,spring} from '../UI';
import JournalWeather from '../journal/JournalWeather';
import {journalServices} from '../journal/journal-model';
import {normalizeSession,statusOf,currentAction,summaryFacts,stableTripItems} from './trip-model';
import {photoAmbientColor} from '../photo-ambient';
import RecordCards from '../journal/RecordCards';
import {changeHistory} from './lifecycle-model';
import './lifecycle-today.css';

const terminal=new Set(['completed','skipped','cancelled']);
const labels={planned:'待开始',delayed:'已延误',in_progress:'进行中',completed:'已完成',skipped:'已跳过',cancelled:'已取消'};
const icons={transport:'car',meal:'dining',hotel:'bed',photography:'image',rest:'leaf',experience:'pin'};
function zoneOf(profile,day,action){
 const zone=action?.timezone||day.timezone||profile.tripSession?.timeZone||profile.timezone||'';
 if(!zone)return '';try{new Intl.DateTimeFormat('zh-CN',{timeZone:zone});return zone;}catch{return '';}
}
function clockOf(value,zone){
 if(!value)return '';
 if(/^([01]\d|2[0-3]):[0-5]\d$/.test(value))return value;
 const date=new Date(value);if(!Number.isFinite(date.getTime()))return '';
 if(!zone)return value.match(/T(\d{2}:\d{2})/)?.[1]||'';
 try{return new Intl.DateTimeFormat('zh-CN',{timeZone:zone,hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(date);}catch{return '';}
}
function locationOf(profile,action){
 const stops=Array.isArray(profile.travelDocument?.stops)?profile.travelDocument.stops:[];
 const stop=stops.find(value=>value.id===action?.place_id);
 const point=stop||action?.geo;
 const latitude=point?.latitude??point?.lat,longitude=point?.longitude??point?.lon;
 const valid=typeof latitude==='number'&&typeof longitude==='number'&&Number.isFinite(latitude)&&Number.isFinite(longitude)&&Math.abs(latitude)<=90&&Math.abs(longitude)<=180;
 return {name:stop?.name||'',address:stop?.address||action?.address||'',url:valid?'https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(latitude+','+longitude):null};
}
function DayPicker({days,active,onChange}){
 const reduced=useReducedMotion(),id=useId(),buttons=useRef([]);
 function select(index){const day=days[index];if(!day)return;onChange?.(day.id);buttons.current[index]?.focus();buttons.current[index]?.scrollIntoView({block:'nearest',inline:'nearest',behavior:'auto'});}
 function keys(event,index){let next=index;if(event.key==='ArrowRight')next=(index+1)%days.length;else if(event.key==='ArrowLeft')next=(index+days.length-1)%days.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=days.length-1;else return;event.preventDefault();select(next);}
 return <nav className="today-day-picker" aria-label="选择旅行日期">{days.map((day,index)=><button type="button" key={day.id} ref={node=>{buttons.current[index]=node;}} aria-pressed={String(day.id)===String(active)} aria-label={'第'+(index+1)+'天，'+(day.date||'日期待确认')+'，'+(day.place||day.name||'安排')} onClick={()=>select(index)} onKeyDown={event=>keys(event,index)}>{String(day.id)===String(active)&&<motion.span className="today-day-pill" layoutId={'today-day-'+id} transition={reduced?{duration:0}:spring}/>}<strong>DAY {String(index+1).padStart(2,'0')}</strong><small>{day.date||'日期待确认'}</small></button>)}</nav>;
}
function mealOf(action){return ['早餐','午餐','晚餐'].find(meal=>(action.title||'').includes(meal))||'';}
function ActionDetails({profile,day,action}){
 const location=locationOf(profile,action),meal=mealOf(action),isMeal=action.kind==='meal'||!!meal;
 const restaurants=Object.values(profile.servicePlan?.restaurant||{}).filter(record=>record&&String(record.dayId)===String(day.id)&&(!meal||(record.key||'').endsWith('-'+meal)||(record.name||'').includes(meal)));
 return <div className="today-inline-details"><p>{action.description||action.details||'还没有备注。'}</p>{isMeal&&<div className="today-meal-details">{restaurants.length?restaurants.map((record,index)=>{const restaurantLocation=locationOf(profile,record);return <div key={record.key||index}><strong>{record.name||'餐厅名称待补充'}</strong><p><Icon name="clock" size={13}/>{record.time||action.time||'用餐时间待确认'}</p><p>{record.status==='recorded'?'已录入预订':record.status==='todo'?'待预订':'已加入安排'}{record.reference?' · '+record.reference:''}</p><p><Icon name="pin" size={13}/>{record.address||location.address||'餐厅地址待补充'}</p>{restaurantLocation.url&&restaurantLocation.url!==location.url&&<a href={restaurantLocation.url} target="_blank" rel="noreferrer" className="today-navigation"><Icon name="pin" size={14}/>导航到餐厅<Icon name="expand" size={12}/></a>}{record.source==='demo'&&<small>参考方案</small>}</div>;}):<p>餐厅与预订信息还未补齐。</p>}</div>}{(location.address||location.name)&&<p className="today-inline-address"><Icon name="pin" size={13}/>{location.address||location.name}</p>}{location.url&&<a href={location.url} target="_blank" rel="noreferrer" className="today-navigation"><Icon name="pin" size={14}/>导航到这里<Icon name="expand" size={12}/></a>}</div>;
}
function ActionHero({profile,day,action,changeTarget,phase,onProgress,onRecord,onChange}){
 const [ambient,setAmbient]=useState([201,209,199]);
 const status=statusOf(profile,action),zone=zoneOf(profile,day,action),fact=profile.tripSession?.facts?.[action.journalId]||action;
 const time=clockOf(action.start||action.time,zone),end=clockOf(action.end||action.endTime,zone),location=locationOf(profile,action);
 const canRecord=phase==='during'&&!terminal.has(status),running=status==='in_progress',image=action.image||day.image;
 return <article className={'glass today-next-action'+(image?' has-full-photo':'')} style={{'--today-photo-color':ambient.join(',')}} aria-label={'当前安排：'+action.title}>
  {image&&<figure><img src={image} alt="" onLoad={event=>setAmbient(photoAmbientColor(event.currentTarget))}/></figure>}
  <div className="today-next-copy"><header><p className="eyebrow">{running?'THIS MOMENT':'NEXT ALONG THE WAY'}</p></header><h2>{action.title||'安排待补充'}</h2><p className="today-action-time"><Icon name="clock" size={15}/>{time?time+(end?' — '+end:''):'计划时间待确认'}</p>{(action.description||action.details)&&<p className="today-action-detail">{action.description||action.details}</p>}
   {(location.name||location.address)&&<p className="today-action-location"><Icon name="pin" size={15}/>{location.address||location.name}{location.url&&<a href={location.url} target="_blank" rel="noreferrer">导航<Icon name="expand" size={12}/></a>}</p>}
   {fact.actual_start&&<p className="today-actual-time">实际开始 {clockOf(fact.actual_start,zone)||fact.actual_start}{fact.actual_end?' · 实际结束 '+(clockOf(fact.actual_end,zone)||fact.actual_end):''}</p>}
   {canRecord&&<div className="today-progress-actions"><Primary type="button" icon="check" onClick={()=>onProgress?.(day,action,running?'completed':'in_progress')}>{running?'这项已完成':'开始这项安排'}</Primary><button type="button" onClick={()=>onProgress?.(day,action,running?'cancelled':'skipped')}>{running?'取消这项':'跳过这项'}</button>{!running&&status!=='delayed'&&<button type="button" onClick={()=>onProgress?.(day,action,'delayed')}>记录延误</button>}</div>}
   <div className="today-action-links"><button type="button" onClick={()=>onRecord?.(day,action)}><Icon name="image" size={15}/>留一段真实记录</button>{changeTarget&&phase!=='after'&&<button type="button" onClick={()=>onChange?.(day,changeTarget)}><Icon name="sliders" size={15}/>调整余下安排</button>}</div>
  </div>
 </article>;
}
function Materials({profile,day,days}){
 const groups=journalServices(day,days,profile).filter(group=>group.rows.length||day.journalServices?.[group.kind]);
 const sources=Array.isArray(profile.travelDocument?.sources)?profile.travelDocument.sources:[];
 return <section className="today-materials"><header className="today-section-title"><h2>资料，放在手边。</h2></header>{groups.length?<div className="today-material-list">{groups.map(group=><Disclosure key={group.kind} title={group.label+' · '+(group.rows.length?group.rows.length+' 项':'自己的补充')}><div className="today-material-details">{group.rows.map(row=><div key={row.kind+'-'+row.key}><strong>{row.name}</strong><p>{row.time||'时间待确认'} · {row.state}</p>{row.reference&&<small>用户录入凭据：{row.reference}</small>}{row.source==='demo'&&<small>参考方案</small>}</div>)}{day.journalServices?.[group.kind]&&<p>{day.journalServices[group.kind]}</p>}</div></Disclosure>)}</div>:<p className="today-quiet-note">还没有当天票据或预订记录。</p>}{sources.length>0&&<Disclosure title={'旅行来源 · '+sources.length}><div className="today-material-details">{sources.map((source,index)=><div key={source.id||index}><strong>{source.title||'资料来源'}</strong>{/^https?:\/\//.test(source.url||'')&&<a href={source.url} target="_blank" rel="noreferrer">查看原文<Icon name="expand" size={12}/></a>}<small>{source.checked_at?'核验时间 '+source.checked_at:'核验时间待补充'}</small></div>)}</div></Disclosure>}</section>;
}
function Changes({day}){
 const revisions=changeHistory(day);
 if(!revisions.length)return null;
 return <section className="today-changes" aria-label="当天真实调整记录"><header className="today-section-title"><h2>这一天，怎样变了。</h2><span>{revisions.length} 次</span></header><ol>{revisions.map(revision=><li className="glass" key={revision.id}><header><small>{Number.isFinite(Number(revision.at))?new Date(revision.at).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}):'时间未提供'}</small>{revision.undone&&<small>已撤销</small>}</header>{revision.changes.map(change=><p key={change.id}><span>{change.before?(change.before.time||'')+' '+change.before.title:'新增安排'}</span><Icon name="chevron" size={12}/><strong>{change.after?(change.after.time||'')+' '+change.after.title:'已移除'}</strong></p>)}</li>)}</ol></section>;
}
export default function TodayPage({onRecord,onChange,onBudget,onEnd,onPlan,onProgress,onDayChange,onBegin}){
 const {profile,days,entries,storageAvailable}=useTravel(),reduced=useReducedMotion(),[expanded,setExpanded]=useState(null);
 const session=useMemo(()=>normalizeSession(profile,days),[profile,days]),facts=useMemo(()=>summaryFacts(profile,days),[profile,days]);
 const day=days.find(value=>String(value.id)===String(session.activeDayId))||days[0];
 const items=useMemo(()=>day?stableTripItems(day):[],[day]),action=day?currentAction(profile,day):null;
 useEffect(()=>setExpanded(null),[day?.id]);
 if(!day)return <div className="lifecycle-today today-empty"><Icon name="calendar" size={28}/><h1>先留下一份安排。</h1><p>旅行生成后，每天的时间与地点会收在这里。</p><Primary type="button" onClick={onPlan}>查看旅行计划</Primary></div>;
 const index=days.findIndex(value=>value.id===day.id),remaining=items.filter(item=>!terminal.has(statusOf(profile,item))),history=items.filter(item=>terminal.has(statusOf(profile,item)));
 const adjustable=remaining.filter(item=>['planned','delayed'].includes(statusOf(profile,item))&&!item.locked),changeTarget=adjustable.find(item=>item.journalId===action?.journalId)||adjustable[0];
 const zone=zoneOf(profile,day,action),weatherDay={...day,place:day.place||profile.destination||'旅行区域'},records=profile.journalRecords?.[day.id]||[];
 const timelineRow=item=>{const status=statusOf(profile,item),time=clockOf(item.start||item.time,zoneOf(profile,day,item)),open=expanded===item.journalId;return <li key={item.journalId}><button type="button" className={'glass today-timeline-row'+(action?.journalId===item.journalId?' is-current':'')} aria-expanded={open} aria-controls={'today-details-'+item.journalId} aria-label={'查看'+item.title+'，'+(time||'时间待确认')+'，'+labels[status]} onClick={()=>setExpanded(open?null:item.journalId)}><span className="today-timeline-time">{time||'未定'}<Icon name={icons[item.kind]||(mealOf(item)?'dining':'pin')} size={13}/></span><span className="today-timeline-copy"><strong>{item.title||'安排待补充'}</strong><small>{labels[status]}{item.locked?' · 已锁定':''}</small></span><motion.span aria-hidden="true" animate={{rotate:open?90:0}} transition={reduced?{duration:0}:spring}><Icon name="chevron" size={14}/></motion.span></button><AnimatePresence initial={false}>{open&&<motion.div id={'today-details-'+item.journalId} className="today-inline-wrap" initial={reduced?false:{height:0,opacity:0}} animate={{height:'auto',opacity:1}} exit={{height:0,opacity:0}} transition={reduced?{duration:0}:{duration:.2}}><ActionDetails profile={profile} day={day} action={item}/></motion.div>}</AnimatePresence></li>;};
 return <motion.div className="lifecycle-today" initial={reduced?false:{opacity:0,y:6}} animate={{opacity:1,y:0}} transition={reduced?{duration:0}:spring}>
  <header className="today-intro"><p className="eyebrow">ALONG THE JOURNEY</p><h1>{session.phase==='before'?'出发后，一步一步走。':session.phase==='after'?'回到那天，再看一眼。':'今天，慢慢走。'}</h1><p>{profile.destination} · {facts.completed}/{facts.total} 项已记录完成</p></header>
  <DayPicker days={days} active={day.id} onChange={onDayChange}/>
  <header className="today-current-day"><div><p>DAY {String(index+1).padStart(2,'0')} · {day.date||'日期待确认'}</p><h2>{day.place||day.name||'当天安排'}</h2></div><span>{zone||'当地时区待确认'}</span></header>
  {session.phase==='before'&&<div className="glass today-before-hint"><p>先开始这趟旅行，再记下真实发生的进度。</p><Primary type="button" icon="check" onClick={onBegin}>开始旅行</Primary></div>}
  <JournalWeather key={String(day.id)} day={weatherDay}/>
  {action?<ActionHero key={action.journalId} profile={profile} day={day} action={action} changeTarget={changeTarget} phase={session.phase} onProgress={onProgress} onRecord={onRecord} onChange={onChange}/>:<div className="glass today-finished"><Icon name={items.length?'check':'calendar'} size={22}/><h2>{items.length?'这一天的进度，已收好。':'这一天，还留着空白。'}</h2><button type="button" onClick={()=>items.length?onRecord?.(day):onPlan?.()}>{items.length?'补一段记录':'查看安排'}<Icon name="chevron" size={14}/></button></div>}
  <section className="today-remaining"><header className="today-section-title"><h2>余下的安排</h2><span>{remaining.length} 项</span></header>{remaining.length?<ol>{remaining.map(timelineRow)}</ol>:<p className="today-quiet-note">当天没有待进行的安排。</p>}</section>
  {history.length>0&&<Disclosure title={'已留下的进度 · '+history.length+' 项'}><ol className="today-history today-completed-rows">{history.map(timelineRow)}</ol></Disclosure>}
  <Changes day={day}/>
  <section className="today-quick-actions" aria-label="沿途快捷操作"><button type="button" className="glass" onClick={()=>onRecord?.(day,action)}><Icon name="image" size={18}/><strong>记录碎片</strong></button><button type="button" className="glass" disabled={session.phase==='after'||!adjustable.length} onClick={()=>onChange?.(day,changeTarget)}><Icon name="sliders" size={18}/><strong>调整余下</strong></button><button type="button" className="glass" onClick={()=>onBudget?.('账目')}><Icon name="mic" size={18}/><strong>一句话记账</strong></button></section>
  <section className="today-fragments"><header className="today-section-title"><h2>今天，留下的碎片。</h2><span>{records.length} 段</span></header>{records.length||entries?.[day.id]?<RecordCards records={records} legacy={entries?.[day.id]} dayId={day.id} ReaderText={({text})=><span>{text}</span>}/>:<p className="today-quiet-note">还没有记录，遇见想留下的时刻就说一句。</p>}</section>
  <Materials profile={profile} day={day} days={days}/>
  {session.phase==='during'&&<div className="today-finish-control"><Primary type="button" icon="check" onClick={onEnd}>结束这趟旅行</Primary></div>}{storageAvailable===false&&<p className="today-storage-warning" role="status">本机空间不足，最新修改暂未保存，请先保留文字。</p>}
 </motion.div>;
}
