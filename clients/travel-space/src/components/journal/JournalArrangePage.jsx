import React,{useEffect,useRef,useState} from 'react';
import {AnimatePresence,motion,useReducedMotion} from 'motion/react';
import {Icon,Primary,spring} from '../UI';
import FloatingField from '../FloatingField';
import {useTravel} from '../../TravelContext';
import {stableItems,pendingDay,scheduleIssues} from './journal-model';
import {requestProposal} from '../../production/proposals';
import {normalizePlan,reservations,conflicts} from '../services/planning';

function ItemDetail({day,item,onBack}){
 const {days,profile,setProfile,reviseJournalDay}=useTravel();
 const [draft,setDraft]=useState({...item}),[editing,setEditing]=useState(false),[asking,setAsking]=useState(false),[request,setRequest]=useState(''),[pending,setPending]=useState(null),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const timer=useRef(null),reduced=useReducedMotion();
 useEffect(()=>()=>clearTimeout(timer.current),[]);
 useEffect(()=>{if(!editing&&!pending)setDraft({...item});},[item,editing,pending]);
 const next=pending?pendingDay(day,pending):{...day,items:stableItems(day).map(row=>row.journalId===item.journalId?draft:row)};
 const issues=(editing||pending)?scheduleIssues(next.items):[];
 const plan=normalizePlan(profile.servicePlan),impacts=(editing||pending)?reservations(plan).filter(row=>row.dayId===day.id).flatMap(row=>conflicts(next,days.map(d=>d.id===day.id?next:d),plan,row).map(value=>row.name+'：'+value)):[];
 const remember=(text,state='success')=>setProfile(prev=>({...prev,journalChats:{...prev.journalChats,[day.id]:[...(prev.journalChats?.[day.id]||[]),{id:crypto.randomUUID(),role:'assistant',mode:'itinerary',itemId:item.journalId,text,state,at:Date.now()}]}}));
 function save(proposal){
  const result=reviseJournalDay(day.id,proposal?pendingDay(day,proposal).items:next.items,{source:proposal?'AI协作 · 已确认':'手动修改',reason:proposal?.reason||'在当天安排详情中修改'});
  if(result){setNotice(result);remember(result,'failure');return;}
  setNotice('已回填当天行程。');remember('已回填 '+(proposal?.after.title||draft.title)+'；旧安排与修改记录保留。');setPending(null);setEditing(false);setAsking(false);setRequest('');
 }
 async function ask(event){event.preventDefault();if(!request.trim()||busy)return;setBusy(true);setNotice('');setPending(null);const text=request.trim();try{
  const value=await requestProposal(text,{day:day.place,item},'title,time（HH:mm）,endTime（可为空）,description,reason');
  if(typeof value.title!=='string'||!value.title.trim()||typeof value.time!=='string')throw new Error('请补充新的安排名称与开始时间。');
  const after={...item,title:value.title.slice(0,240),time:value.time,endTime:value.endTime||'',description:typeof value.description==='string'?value.description.slice(0,48000):item.description};
  const issues=scheduleIssues([after]);if(issues.length)throw new Error(issues.join(' '));
  setPending({before:item,after,reason:typeof value.reason==='string'?value.reason:text});
 }catch(error){setNotice(error.message);remember(error.message,'failure');}finally{setBusy(false);}}

 const field=(key,value)=>{setDraft(prev=>({...prev,[key]:value}));setNotice('');};
 const proposalField=(key,value)=>setPending(prev=>({...prev,after:{...prev.after,[key]:value}}));
 return <motion.section className="journal-arrange-detail" aria-label={'安排详情 '+item.title} initial={reduced?false:{scale:.95,opacity:0}} animate={{scale:1,opacity:1}} exit={{scale:.96,opacity:0}} transition={spring}>
  <button type="button" className="arrange-detail-back" onClick={onBack}><Icon name="back" size={15}/>当天安排</button>
  <header><time>{item.time}{item.endTime?' — '+item.endTime:''}</time><h3>{item.title}</h3><p>{item.description||'还没有备注。'}</p></header>
  {!editing&&!pending&&<div className="arrange-detail-tools"><button type="button" onClick={()=>{setEditing(true);setAsking(false);setDraft({...item});setNotice('');}}><Icon name="edit" size={16}/>自己修改</button><button type="button" aria-expanded={asking} onClick={()=>setAsking(value=>!value)}><Icon name="thought" size={16}/>与 AI 商量</button></div>}
  {editing&&<form className="arrange-compact-form" onSubmit={event=>{event.preventDefault();if(!issues.length)save();}}><FloatingField label="安排名称" aria-label="修改安排名称" value={draft.title} onChange={event=>field('title',event.target.value)}/><div className="arrange-time-pair"><FloatingField type="time" label="开始" aria-label="修改安排开始" value={draft.time} onChange={event=>field('time',event.target.value)}/><FloatingField type="time" label="结束（可选）" aria-label="修改安排结束" value={draft.endTime||''} onChange={event=>field('endTime',event.target.value)}/></div><FloatingField as="textarea" label="备注" aria-label="修改安排备注" rows={2} value={draft.description||''} onChange={event=>field('description',event.target.value)}/><div className="arrange-confirm-actions"><button type="button" className="journal-text-action" onClick={()=>{setEditing(false);setDraft({...item});setNotice('');}}>取消</button><Primary type="submit" icon="check" disabled={issues.length>0}>确认修改</Primary></div></form>}
  {asking&&!editing&&<form className="arrange-ai-compose" onSubmit={ask}><label htmlFor={'arrange-request-'+item.journalId}>希望怎样调整？</label><div><input id={'arrange-request-'+item.journalId} aria-label="描述这项调整" value={request} onChange={event=>setRequest(event.target.value)} placeholder="新的安排或开始时间" maxLength={500}/><button type="submit" className="confirm-capsule confirm-icon" aria-label="生成安排修改对照" disabled={!request.trim()||busy}><Icon name="arrow" size={17}/></button></div></form>}
  {busy&&<p className="arrange-feedback" role="status">正在整理修改对照…</p>}
  {pending&&<section className="arrange-proposal" aria-label="待确认的安排修改"><small>修改对照 · 待确认</small><div className="arrange-old-line"><del>{pending.before.time} {pending.before.title}</del><Icon name="chevron" size={12}/></div><div className="arrange-compact-form"><FloatingField label="新的安排" aria-label="AI新安排名称" value={pending.after.title} onChange={event=>proposalField('title',event.target.value)}/><div className="arrange-time-pair"><FloatingField type="time" label="开始" aria-label="AI新安排开始" value={pending.after.time} onChange={event=>proposalField('time',event.target.value)}/><FloatingField type="time" label="结束（可选）" aria-label="AI新安排结束" value={pending.after.endTime||''} onChange={event=>proposalField('endTime',event.target.value)}/></div><FloatingField as="textarea" label="备注" aria-label="AI新安排说明" rows={2} value={pending.after.description||''} onChange={event=>proposalField('description',event.target.value)}/></div><div className="arrange-confirm-actions"><button type="button" className="journal-text-action" onClick={()=>{setPending(null);setNotice('这份修改未采用。');}}>暂不采用</button><Primary type="button" icon="check" disabled={issues.length>0} onClick={()=>save(pending)}>确认回填</Primary></div></section>}
  {issues.length>0&&<ul className="arrange-validation" role="status">{issues.map(value=><li key={value}>{value}</li>)}</ul>}{impacts.length>0&&<details className="arrange-reservation-impact"><summary>预订衔接 · {impacts.length}项需核对</summary>{impacts.map((value,index)=><p key={index}>{value}</p>)}</details>}
  {notice&&<p className="arrange-feedback" role="status">{notice}</p>}
 </motion.section>;
}

export default function JournalArrangePage({day}){
 const [selected,setSelected]=useState(null),[pressed,setPressed]=useState(null),reduced=useReducedMotion();
 const items=stableItems(day),current=items.find(item=>item.journalId===selected);
 return <section className="journal-arrange-page" aria-label="调整当天行程"><AnimatePresence initial={false} mode="wait">{current?<ItemDetail key={current.journalId} day={day} item={current} onBack={()=>setSelected(null)}/>:<motion.div key="arrange-cards" initial={reduced?false:{opacity:0,x:-20}} animate={{opacity:1,x:0}} exit={{opacity:0,x:-20}} transition={spring}><p className="arrange-cards-caption">选择一站，看看细节，再慢慢调整。</p><div className="arrange-day-cards" role="list" aria-label="当天行程卡片">{items.map((item,index)=><motion.div layout key={item.journalId} role="listitem" className={'arrange-card-slot arrange-offset-'+index%3} animate={reduced?{scale:1,y:0}:{scale:pressed===item.journalId?1.04:pressed?.97:1,y:pressed&&pressed!==item.journalId?(index%2?6:-6):0}} transition={{type:'spring',stiffness:430,damping:24}}><button type="button" className="glass arrange-day-card" aria-label={'展开安排 '+item.title} onPointerDown={()=>setPressed(item.journalId)} onPointerUp={()=>setPressed(null)} onPointerCancel={()=>setPressed(null)} onPointerLeave={()=>setPressed(null)} onBlur={()=>setPressed(null)} onClick={()=>{setPressed(null);setSelected(item.journalId);}}><time>{item.time}</time><Icon name={/餐|食|饭/.test(item.title)?'dining':'pin'} size={17}/><strong>{item.title}</strong><p>{item.description||'点开补充备注'}</p><span><Icon name="expand" size={13}/></span></button></motion.div>)}</div>{items.length===0&&<p className="arrange-feedback">这一天还没有安排。</p>}</motion.div>}</AnimatePresence></section>;
}
