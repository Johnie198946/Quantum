import React,{useId,useState} from 'react';
import {AnimatePresence,motion,useReducedMotion} from 'motion/react';
import {useTravel} from '../../TravelContext';
import {Icon,Primary,spring} from '../UI';
import FloatingField from '../FloatingField';
import {normalizeSession} from './trip-model';
import {preparationMemos,updatePreparation,addPreparationMemo} from './lifecycle-model';

function Check({checked,onChange,label,disabled=false}){
 const reduced=useReducedMotion();
 return <label className={'preparation-check'+(checked?' is-checked':'')}><input type="checkbox" checked={checked} disabled={disabled} aria-label={label} onChange={event=>onChange(event.target.checked)}/><motion.span aria-hidden="true" initial={false} animate={reduced?{rotate:0,scale:1}:{rotate:checked?[-16,6,0]:0,scale:checked?[.88,1.16,1]:1}} transition={reduced?{duration:0}:{duration:.42,ease:[.2,.8,.2,1]}}>{checked&&<Icon name="check" size={15}/>}</motion.span></label>;
}
function MemoCategory({category,profile,days,setProfile}){
 const [open,setOpen]=useState(false),[draft,setDraft]=useState(''),[error,setError]=useState(''),id=useId(),reduced=useReducedMotion();
 const pending=category.memos.filter(memo=>!memo.done),questions=pending.filter(memo=>memo.question),done=category.memos.length>0&&!pending.length;
 function add(event){event.preventDefault();try{const next=addPreparationMemo(profile,days,category.id,draft);setProfile(next);setDraft('');setError('');}catch(issue){setError(issue.message);}}
 return <article className={'glass preparation-category'+(done?' is-complete':'')} data-category={category.id}>
  <header><Check checked={done} disabled={!category.memos.length} label={'勾选全部'+category.title} onChange={checked=>setProfile(previous=>updatePreparation(previous,days,category.memos.map(memo=>memo.id),checked))}/><button type="button" className="preparation-category-toggle" aria-expanded={open} aria-controls={id} onClick={()=>setOpen(value=>!value)}><span><strong>{category.title}</strong><small>{category.memos.length?done?'已核对 '+category.memos.length+' 项':pending.length+' 项待核对':'添加自己的备忘'}</small></span>{questions.length>0&&<span className="preparation-question-badge" aria-label={questions.length+'个待确认问题'}>{questions.length}</span>}<motion.span aria-hidden="true" animate={{rotate:open?180:0}} transition={reduced?{duration:0}:spring}><Icon name="down" size={16}/></motion.span></button></header>
  <AnimatePresence initial={false}>{open&&<motion.div id={id} className="preparation-category-body" initial={reduced?false:{height:0,opacity:0}} animate={{height:'auto',opacity:1}} exit={{height:0,opacity:0}} transition={reduced?{duration:0}:{duration:.22}}><ul>{category.memos.map(memo=><li key={memo.id} className={memo.done?'is-complete':''}><Check checked={memo.done} label={'核对：'+memo.text} onChange={checked=>setProfile(previous=>updatePreparation(previous,days,[memo.id],checked))}/><span>{memo.text}{memo.source==='user'&&<small>自己的备忘</small>}</span></li>)}</ul><form onSubmit={add} className="preparation-add"><FloatingField placeholder="补充一条备忘" aria-label={category.title+'的新备忘'} value={draft} maxLength={500} onChange={event=>setDraft(event.target.value)}/><button type="submit" className="icon-btn" disabled={!draft.trim()} aria-label={'添加'+category.title+'备忘'}><Icon name="plus" size={18}/></button></form>{category.id==='conditions'&&Array.isArray(profile.travelDocument?.sources)&&profile.travelDocument.sources.length>0&&<div className="preparation-sources">{profile.travelDocument.sources.map((source,index)=><div className="lifecycle-source" key={source.id||index}><strong>{source.title||'资料来源'}</strong>{/^https?:\/\//.test(source.url||'')&&<a href={source.url} target="_blank" rel="noreferrer">查看原文</a>}{source.checked_at&&<small>{source.checked_at}</small>}</div>)}</div>}{error&&<p className="lifecycle-error" role="alert">{error}</p>}</motion.div>}</AnimatePresence>
 </article>;
}
export default function BeforePage({busy=false,onBegin,onPlan,onNotebook,onBudget}){
 const {profile,setProfile,days,saved,setTodosOpen}=useTravel(),session=normalizeSession(profile,days),categories=preparationMemos(profile,days);
 return <div className="lifecycle-before">
  <header className="lifecycle-intro"><p className="eyebrow">BEFORE THE JOURNEY</p><h1>把期待，<br/>慢慢排进日子里。</h1><p>{profile.destination} · {days.length} 天 · {profile.count}</p></header>
  <div className="glass lifecycle-plan-preview"><p>{profile.dates}</p><h2>{days.map(day=>day.place).filter(Boolean).join(' → ')}</h2><button type="button" onClick={onPlan}>查看当前安排<Icon name="chevron" size={15}/></button></div>
  <div className="lifecycle-shortcuts"><button type="button" onClick={onNotebook}><Icon name="book" size={19}/><b>{saved?'翻开已存手记':'查看旅行手记'}</b><small>把行程带在身边</small></button><button type="button" onClick={onBudget}><Icon name="wallet" size={19}/><b>预算与同行人</b><small>先确定怎样一起算</small></button></div>
  <section className="lifecycle-section"><header><h2>出发前，再确认一下。</h2><button type="button" onClick={()=>setTodosOpen(true)}>旅行待办<Icon name="chevron" size={13}/></button></header><div className="lifecycle-checklist preparation-categories">{categories.map(category=><MemoCategory key={category.id} category={category} profile={profile} days={days} setProfile={setProfile}/>)}</div></section>
  {session.phase==='before'&&<div className="lifecycle-begin"><Primary icon="check" disabled={busy} onClick={onBegin}>开始这趟旅行</Primary></div>}
 </div>;
}
