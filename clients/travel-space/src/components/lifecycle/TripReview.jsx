import React,{useMemo,useState} from 'react';
import {motion,useReducedMotion} from 'motion/react';
import {useTravel} from '../../TravelContext';
import {Icon,Primary,Disclosure,spring} from '../UI';
import FloatingField from '../FloatingField';
import RecordCards from '../journal/RecordCards';
import {stableItems} from '../journal/journal-model';
import {normalizeLedger,ledgerEntries,summarizeLedger,formatMoney} from '../budget/budget-model';
import {normalizeSession,summaryFacts,statusOf} from './trip-model';
import {tripFragments,proposeTripSummary} from './lifecycle-model';
import SummarySheet from './SummarySheet';
import './lifecycle-review.css';

const statusLabels={planned:'尚未记录',delayed:'延误',in_progress:'进行中',completed:'已完成',skipped:'已跳过',cancelled:'已取消'};
const dateLabel=value=>{const date=new Date(value);return Number.isFinite(date.getTime())?date.toLocaleDateString('zh-CN',{month:'long',day:'numeric'}):'日期待确认';};
// This local signature only detects a stale review; backend CAS uses its SHA256.
function signature(value){let hash=2166136261;for(const character of JSON.stringify(value)){hash^=character.codePointAt(0);hash=Math.imul(hash,16777619);}return 'review-'+(hash>>>0).toString(16);}
const ReaderText=({text})=><span>{text}</span>;

function PlanComparison({profile,days,session}){
 const baseline=session.baseline?.days||[];
 return <Disclosure title="原来的计划，实际的脚步"><div className="trip-review-days">
  {days.map((day,index)=>{const original=baseline.find(value=>String(value.id)===String(day.id)),current=stableItems(day),items=original?.items||current,seen=new Set(items.map(item=>item.journalId));
   const rows=[...items,...current.filter(item=>!seen.has(item.journalId))];
   return <section className="trip-review-day" key={day.id}><header><small>DAY {String(index+1).padStart(2,'0')} · {day.date}</small><h3>{day.place||day.name}</h3></header>
    {rows.map(item=>{const next=current.find(value=>value.journalId===item.journalId),fact=session.facts?.[item.journalId],status=fact?.status||statusOf(profile,next||item),changed=next&&(item.title!==next.title||item.time!==next.time),removed=!next;
     return <div className="trip-review-plan-row" key={item.journalId}><span className={'trip-review-status-dot status-'+status} aria-hidden="true"/><div><strong>{fact?.title||next?.title||item.title||'标题待补充'}</strong><small>{changed?<><del>{item.time} · {item.title}</del><span>调整为 {next.time} · {next.title}</span></>:<span>{item.time||'时间待确认'}{removed?' · 已从安排移除':''}</span>}</small>{fact?.actual_start&&<small>实际开始 {dateLabel(fact.actual_start)}{fact.actual_end?' · 已记录结束':''}</small>}</div><span className="trip-review-status">{statusLabels[status]||'尚未记录'}</span></div>;
    })}
   </section>;
  })}
  {!baseline.length&&<p className="trip-review-note">还没有出发时的计划快照。这里显示现有安排与实际标记。</p>}
 </div></Disclosure>;
}

export default function TripReview({onBudget,onRecord}){
 const {profile,setProfile,days,entries:noteEntries,storageAvailable}=useTravel(),reduced=useReducedMotion();
 const session=useMemo(()=>normalizeSession(profile,days),[profile,days]),facts=useMemo(()=>summaryFacts(profile,days),[profile,days]);
 const ledger=useMemo(()=>normalizeLedger(profile.budgetLedger,profile),[profile]),entries=useMemo(()=>ledgerEntries(profile,days,ledger),[profile,days,ledger]);
 const money=useMemo(()=>summarizeLedger(entries,ledger),[entries,ledger]),fragments=tripFragments(profile,days,noteEntries);
 const validPaid=entries.filter(entry=>entry.status==='paid'&&!money.errors.some(error=>error.id===entry.id));
 const currentSignature=signature([session.facts,fragments,facts.changedDays,facts.changeCount,entries,ledger.settlements,ledger.baseCurrency,ledger.rates]);
 const [editing,setEditing]=useState(false),[draft,setDraft]=useState(''),[notice,setNotice]=useState(''),[editingSignature,setEditingSignature]=useState(currentSignature),[proposal,setProposal]=useState(null);
 const recap=session.recap||{},stale=!!recap.text&&recap.factsFingerprint!==currentSignature;
 const ended=!!session.finishedAt;
 function saveRecap(event){event.preventDefault();if(!draft.trim()){setNotice('写下自己的总结。');return;}setProfile(previous=>({...previous,tripSession:{...normalizeSession(previous,days),recap:{...normalizeSession(previous,days).recap,text:draft.trim(),updatedAt:new Date().toISOString(),factsFingerprint:editingSignature}}}));setEditing(false);setNotice('总结已保存，沿途原记录仍可查看。');}
 function startEditing(){setDraft(recap.text||'');setEditingSignature(currentSignature);setEditing(true);setNotice('');}
 const recordDays=days.filter(day=>profile.journalRecords?.[day.id]?.length);
 return <motion.div className="trip-review" initial={reduced?false:{opacity:0,y:8}} animate={{opacity:1,y:0}} transition={reduced?{duration:0}:spring}>
  <header className="trip-review-heading"><p className="eyebrow">AFTER THE JOURNEY</p><h2>把这一程，留得清楚。</h2><p>{ended?dateLabel(session.finishedAt)+' · 旅行已结束':'先回望，记录还会继续。'}{profile.destination?' · '+profile.destination:''}</p></header>
  <section className="glass trip-review-overview" aria-label="旅行实际记录汇总"><div className="trip-review-metrics"><span><strong>{facts.completed}</strong><small>已完成安排</small></span><span><strong>{facts.records}</strong><small>沿途记录</small></span><span><strong>{facts.changeCount}</strong><small>安排调整</small></span></div><p>{facts.total} 项安排中，{facts.unfinished} 项尚未记录完成{facts.skipped+facts.cancelled?'，'+(facts.skipped+facts.cancelled)+' 项已跳过或取消':''}。</p></section>
  <section className="trip-review-recap"><header className="trip-review-section-heading"><div><p className="eyebrow">YOUR WORDS, KEPT</p><h3>这趟旅行，想留下什么？</h3></div>{!editing&&<button type="button" className="trip-review-icon" aria-label="编辑旅行总结" onClick={startEditing}><Icon name="edit" size={18}/></button>}</header>
   {editing?<form onSubmit={saveRecap}><FloatingField as="textarea" rows={6} maxLength={12000} aria-label="自己的旅行总结" placeholder="留下自己的感受。" value={draft} onChange={event=>setDraft(event.target.value)}/><div className="trip-review-edit-actions"><button type="button" onClick={()=>setEditing(false)}>取消</button><Primary type="submit" icon="check">保存总结</Primary></div></form>:recap.text?<div className="trip-review-own-words"><p>{recap.text}</p><small>{dateLabel(recap.updatedAt)} · 自己的总结</small></div>:<div className="trip-review-empty"><Icon name="book" size={24}/><p>先收好真正发生的事。<br/>感受，留给自己慢慢写。</p></div>}
   {stale&&<p className="trip-review-note">沿途记录或账目有更新。原总结已保留，可以再核对一次。</p>}
   {recap.history?.length>0&&<Disclosure title={'之前保存的总结 · '+recap.history.length}><div className="trip-review-recap-history">{recap.history.map((previous,index)=><div className="trip-review-own-words" key={index}><p>{previous.text}</p>{previous.updatedAt&&<small>{dateLabel(previous.updatedAt)}</small>}</div>)}</div></Disclosure>}
  </section>
  <PlanComparison profile={profile} days={days} session={session}/>
  <section className="trip-review-memories"><header className="trip-review-section-heading"><div><p className="eyebrow">FROM ALONG THE WAY</p><h3>回到当时，读读原话。</h3></div><span>{facts.records} 段</span></header>{recordDays.length?<Disclosure title="查看沿途原记录"><div className="trip-review-records">{recordDays.map((day,index)=><section key={day.id}><header><h4>DAY {String(days.findIndex(value=>value.id===day.id)+1).padStart(2,'0')} · {day.place||day.name}</h4>{onRecord&&<button type="button" aria-label={'查看'+day.name+'的原记录'} onClick={()=>onRecord(day.id)}><Icon name="chevron" size={14}/></button>}</header><RecordCards records={profile.journalRecords[day.id]} dayId={day.id} ReaderText={ReaderText}/></section>)}</div></Disclosure>:<p className="trip-review-note">还没有沿途记录。想起一段真实经历时，可以回到当天补记。</p>}{onRecord&&<button type="button" className="trip-review-draft-action" onClick={()=>onRecord(session.activeDayId||days[0]?.id)}><Icon name="plus" size={15}/>补一段真实记录</button>}</section>
  <section className="glass trip-review-finance" aria-label="游后费用核对"><header><div><p className="eyebrow">ONE CURRENCY, ONE ACCOUNT</p><h3>把花费，核对到最后。</h3></div><span>{ledger.baseCurrency}</span></header><p className="trip-review-finance-label">已核对的花费</p><strong className="trip-review-paid" data-testid="trip-review-paid-total">{formatMoney(money.paid,ledger.baseCurrency)}</strong><div className="trip-review-finance-meta"><span>{validPaid.length} 笔已支付</span><span>{ledger.settlements.length} 笔转账记录</span></div><button type="button" className="trip-review-budget-action" onClick={()=>onBudget?.('账目')}>查看完整账本<Icon name="chevron" size={15}/></button></section>
  <section className="glass trip-review-summary-fragments" aria-label="整理已保存的旅行片段"><header className="trip-review-section-heading"><div><p className="eyebrow">PIECES INTO A PAGE</p><h3>把碎片，收成这一程。</h3></div><span>{fragments.length} 段</span></header>{fragments.length>0?<><ul>{fragments.slice(-3).map(fragment=><li key={fragment.id}><span>{fragment.dayLabel}</span><p>{fragment.text||'已保存图片或录音'}</p></li>)}</ul><Primary type="button" icon="spark" aria-label="整理已保存的旅行片段" onClick={()=>{setProposal(proposeTripSummary(profile,days,noteEntries));setNotice('');}}>整理这些片段</Primary></>:<p className="trip-review-note">先留下一段真实记录，再慢慢整理。</p>}</section>
  {(notice||storageAvailable===false)&&<p className="trip-review-notice" role="status">{storageAvailable===false?'本机空间不足，最新修改暂未保存，请先保留文字。':notice}</p>}
  {proposal&&<SummarySheet proposal={proposal} factsFingerprint={currentSignature} onClose={()=>setProposal(null)} onSaved={()=>setNotice('总结已写入旅行手记，所有原片段与实际记录仍保留。')}/>}

 </motion.div>;
}
