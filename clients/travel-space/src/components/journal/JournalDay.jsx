import JournalWeather from './JournalWeather';
import JournalRouteMap from './JournalRouteMap';
import RecordCards from './RecordCards';
import {ReaderText} from './ReaderAnnotations';
import React from 'react';
import {useTravel} from '../../TravelContext';
import {Icon} from '../UI';
import {dayNumber} from '../mapRoute';
import {journalServices,itemKey,latestRevision,formatRevisionDate,undoDayRevision} from './journal-model';

function Item({item,changed=false,dayId,blockId}){return <div className={changed?'journal-item journal-new':'journal-item'}>{changed&&<small className="revision-label">新安排</small>}<time>{item.time}{item.endTime?' — '+item.endTime:''}</time><div><strong>{item.title}</strong><p><ReaderText dayId={dayId} id={blockId} text={item.description||''}/></p></div></div>;}
function OldItem({item}){return <div className="journal-old"><small>旧安排</small><del><time>{item.time}{item.endTime?' — '+item.endTime:''}</time> {item.title}<span>{item.description}</span></del></div>;}
export default function JournalDay({day,record,flags,onRecord,onAssistant,onEdit,onSource,onSelectDay}){
 const {profile,days,openServices,updateDay}=useTravel(),services=journalServices(day,days,profile),revision=latestRevision(day);
 const changes=new Map((revision?.changes||[]).map(x=>[x.key,x]));
 const undo=()=>{const next=undoDayRevision(day);if(next)updateDay(next);};
 const canUndo=!!revision&&!!undoDayRevision(day);
 return <article className="journal-editorial-day">
  <header className="journal-day-title"><p className="journal-day-kicker">DAY {String(dayNumber(day)).padStart(2,'0')} / {day.date}</p><JournalWeather key={day.id} day={day}/><h1>{day.name}</h1><p className="journal-location"><ReaderText dayId={day.id} id="intro" text={day.place+' · '+(profile.journal?.subtitle||'把风景，也把日常收进来。')}/></p></header>
  {flags[1]&&<figure className="journal-lead-photo"><img src={day.image} alt={day.place+'目的地区域风景'}/><figcaption><span>{String(dayNumber(day)).padStart(2,'0')} / {day.place}</span><button aria-label="照片来源与拍摄建议" onClick={onSource}>照片参考 <Icon name="expand" size={11}/></button></figcaption></figure>}
  {flags[0]&&<JournalRouteMap day={day} days={days} onSelectDay={onSelectDay}/>}
  <section className="journal-memory"><header><p className="journal-kicker">A NOTE TO REMEMBER</p><button aria-label="编辑这天的旅行记录" onClick={onRecord}><Icon name="edit" size={14}/></button></header><h2>自己的旅行记录</h2>{(record||profile.journalRecords?.[day.id]?.length)?<RecordCards records={profile.journalRecords?.[day.id]||[]} legacy={record} dayId={day.id} ReaderText={ReaderText}/>:<p className="journal-memory-empty">还没有记录。<br/>留给真正出发时的你。</p>}<button className="journal-text-action" onClick={()=>onAssistant('notes')}>阅读与批注 <Icon name="book" size={12}/></button></section>
  {flags[0]&&<section className="journal-schedule"><header className="journal-section-heading"><div><p className="journal-kicker">THE DAY / PLAN</p><h2>今天，怎样慢慢走。</h2></div><button aria-label="编辑当天行程" onClick={onEdit}><Icon name="edit" size={15}/></button></header>
   {revision&&<div className="journal-revision-caption"><p>{revision.source} · {formatRevisionDate(revision.at)}<br/>{revision.reason}</p>{canUndo?<button onClick={undo}>撤回最近行程修改</button>:<small>行程已有后续编辑，保留这份对照。</small>}</div>}
   <ol className="journal-timeline">{day.items.map((item,index)=>{const change=changes.get(itemKey(day,item,index));return <li key={itemKey(day,item,index)}>{change?.before&&<OldItem item={change.before}/>}<Item item={item} dayId={day.id} blockId={itemKey(day,item,index)} changed={!!change?.after}/></li>;})}{(revision?.changes||[]).filter(x=>!x.after&&x.before).map(x=><li key={x.key} className="journal-removed"><OldItem item={x.before}/><small>已从当天安排移除</small></li>)}</ol>
   <button className="journal-text-action" onClick={()=>onAssistant('itinerary')}>与 AI 商量换个安排 <Icon name="spark" size={12}/></button>
   {!!day.journalRevisions?.length&&<details className="journal-version-log"><summary>查看修改记录 · {day.journalRevisions.length}次</summary>{[...day.journalRevisions].reverse().map(r=><div key={r.id}><p>{r.source} · {formatRevisionDate(r.at)}{r.undone?' · 已撤回':''}</p>{r.changes.map(x=><div className="journal-log-change" key={x.key}>{x.before&&<del>{x.before.time} {x.before.title}</del>}{x.after&&<ins>{x.after.time} {x.after.title}</ins>}</div>)}</div>)}</details>}
  </section>}
  <section className="journal-living"><div className="journal-section-heading"><div><p className="journal-kicker">STAY / EAT / MOVE / DO</p><h2>风景之外的日常。</h2></div></div>{services.map((service,index)=><section className={'journal-service journal-service-'+service.kind} key={service.kind}><header><span className="journal-service-number">0{index+1}</span><div><p><Icon name={service.icon} size={14}/>{service.label}</p><h3>{service.heading}</h3></div><button aria-label={'规划手记中的'+service.label} onClick={()=>openServices(service.kind,day.id)}><Icon name="expand" size={13}/></button></header>{service.rows.length?<ul>{service.rows.map(r=><li key={r.kind+r.key}><time>{r.time||'入住'}</time><div><strong>{r.name}</strong><p>{r.state}{r.checkout?' · 离店 '+r.checkout:''}</p>{r.note&&<small>{r.note}</small>}</div></li>)}</ul>:<p className="journal-service-copy"><ReaderText dayId={day.id} id={'service-'+service.kind} text={service.text}/></p>}{service.rows.length>0&&service.custom&&<p className="journal-service-copy"><ReaderText dayId={day.id} id={'service-'+service.kind} text={service.text}/></p>}{service.missingMeals.map(meal=><p className="journal-meal-missing" key={meal}>{meal} · {meal==='早餐'?'围绕酒店安排':meal==='午餐'?'围绕午间行程安排':'围绕今晚落脚点安排'}<small>尚未选择餐厅</small></p>)}<small className="journal-service-footnote">{service.rows.length?'预订安排与清单同步':'行程建议 · 尚未选定预订'}{service.custom?' · 手记补充说明':''}</small></section>)}</section>
  {flags[1]&&<figure className="journal-closing-photo"><img src={days[(days.findIndex(x=>x.id===day.id)+1)%days.length].image} alt="下一段旅程的目的地风景"/><figcaption>让下一段风景，留一点想象。</figcaption></figure>}
  <footer className="journal-day-end"><p>{day.items.map(x=>x.title).join(' → ')}</p><span>END OF DAY {String(dayNumber(day)).padStart(2,'0')}</span></footer>
 </article>;
}
