import React from 'react';
import {Icon} from '../UI';
import {candidate,clock,minutes} from './planning';
import {serviceAmount,serviceSourceId} from './service-expenses';
import './revision68-services.css';

function Expense({kind,recordKey,record,profile}){
 const paid=profile.budgetLedger?.entries?.find(entry=>entry.sourceId===serviceSourceId(kind,recordKey)&&entry.status==='paid');
 const estimate=serviceAmount(record,profile);
 return <>{paid?paid.currency+' '+paid.amount+' · 已支付':estimate?estimate.currency+' '+estimate.amount.toLocaleString()+' · 预计':'费用待补充'}</>;
}
export default function DayServiceFacts({day,items,profile,plan,onOpen}){
 const legs=Object.entries(plan.transport).filter(([,record])=>String(record.dayId)===String(day.id));
 return <div className="day-service-facts"><section className="day-stay-and-meals" aria-label="当天住宿与三餐"><header><small>AT THE TABLE · AT REST</small><h3>吃在哪，今晚住在哪。</h3></header>{[['restaurant','早餐','07:30'],['restaurant','午餐','12:30'],['restaurant','晚餐','18:30'],['hotel','今晚住宿','夜晚']].map(([kind,label,time])=>{
  const key=kind==='hotel'?String(day.id):day.id+'-'+label,record=plan[kind][key],place=candidate(record?.candidateId),activity=kind==='restaurant'?items.find(item=>item.title.includes(label)):null;
  const leg=plan.transport[day.id+'-'+(kind==='hotel'?'return':label==='午餐'?'lunch':label==='早餐'?'hotel':'return')];
  return <article key={label} className="daily-fact-card" data-pending-key={'day-'+day.id+'-'+label}><button type="button" className="daily-fact-heading" onClick={()=>onOpen(kind,day.id,kind==='restaurant'?{meal:label}:{})}><Icon name={kind==='hotel'?'bed':'dining'} size={15}/><span><small>{record?.time||activity?.time||time} · {label}</small><strong>{record?.name||activity?.title||(kind==='hotel'?'住宿待选择':'餐厅待选择')}</strong></span><Icon name="chevron" size={12}/></button><dl><div><dt>在哪里</dt><dd>{record?.address||place?.name||day.place+' · 具体地址待补充'}</dd></div><div><dt>预约</dt><dd>{record?.status==='recorded'?'已录入预约'+(record.time?' · '+record.time:''):record?.status==='todo'?'待预约':'尚未预约'}</dd></div><div><dt>怎么去</dt><dd>{leg?leg.mode+' · '+leg.time+'出发':record?.howToGet||'交通待安排'}</dd></div><div><dt>花费</dt><dd><Expense kind={kind} recordKey={key} record={record} profile={profile}/></dd></div></dl></article>;
 })}</section><section className="day-traffic-facts" aria-label="当天交通与时间建议"><header><small>BETWEEN EACH STOP</small><h3>几点出发，怎么到下一站。</h3><button type="button" aria-label="安排当天交通" onClick={()=>onOpen('transport',day.id)}><Icon name="plus" size={15}/></button></header>{legs.length?legs.map(([key,record])=>{
  const target=record.segment==='lunch'?plan.restaurant[day.id+'-午餐']?.time:record.segment==='play'?plan.activity[day.id]?.time:record.segment==='return'?null:items[0]?.time;
  const end=Number.isFinite(minutes(record.time))?clock((minutes(record.time)+(record.duration||0))%1440):'';
  return <article key={key} className="daily-traffic-card"><button type="button" onClick={()=>onOpen('transport',day.id,{segment:record.segment})}><time>{record.time||'时间待定'}</time><span><strong>{record.name}</strong><small>{record.mode}{end?' · '+end+'抵达':''}</small></span><Icon name="chevron" size={12}/></button><dl><div><dt>上车</dt><dd>{record.ticket?.stops?.[0]||record.route?.stops?.[0]?.name||'上车点待补充'}</dd></div><div><dt>费用</dt><dd><Expense kind="transport" recordKey={key} record={record} profile={profile}/></dd></div></dl><p className="daily-time-advice"><Icon name="clock" size={12}/>{target?'下一项 '+target+' 开始；':'抵达后'}预留 {record.buffer??20} 分钟衔接{record.ticket?.stops?.[1]?'，在 '+record.ticket.stops[1]+' 候车。':'。'}</p></article>;
 }):<button type="button" className="daily-traffic-empty" onClick={()=>onOpen('transport',day.id)}><Icon name="car" size={17}/><span>补一段交通<small>出发时间、上车点和费用一起收好。</small></span><Icon name="plus" size={14}/></button>}</section></div>;
}
