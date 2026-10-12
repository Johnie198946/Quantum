import React from 'react';
import {Icon} from '../UI';
import {ReaderText} from './ReaderAnnotations';
import RecordCards from './RecordCards';
import {stableItems} from './journal-model';

export default function JournalAnnotationsPage({day,days,profile,entries,onDay,onList}){
 const notes=(profile.readerAnnotations||[]).filter(note=>note.dayId===day.id);
 const intro=day.place+' · '+(profile.journal?.subtitle||'把风景，也把日常收进来。');
 return <section className="journal-annotation-page" aria-label="阅读与批注">
  <div className="annotation-days" role="group" aria-label="选择批注日期">{days.map((item,index)=><button key={item.id} type="button" aria-pressed={item.id===day.id} onClick={()=>onDay(item.id)}>DAY {String(index+1).padStart(2,'0')}</button>)}</div>
  <header className="annotation-reading-title"><small>{day.date} · {day.place}</small><h3>{day.name}</h3><p><ReaderText dayId={day.id} id="intro" text={intro}/></p></header>
  <p className="annotation-reading-hint"><Icon name="edit" size={13}/>选中一段文字，留下高亮或批注。</p>
  <article className="annotation-reading-copy" aria-label="可批注的当天行程">{stableItems(day).map(item=><section key={item.journalId}><time>{item.time}</time><h4>{item.title}</h4><p><ReaderText dayId={day.id} id={item.journalId} text={item.description||''}/></p></section>)}</article>
  {(entries[day.id]||profile.journalRecords?.[day.id]?.length>0)&&<section className="annotation-original-records"><h4>自己的记录</h4><RecordCards records={profile.journalRecords?.[day.id]||[]} legacy={entries[day.id]} dayId={day.id} ReaderText={ReaderText}/></section>}
  <button type="button" className="annotation-list-entry" onClick={onList}><Icon name="book" size={17}/><span>高亮与批注<small>{notes.length} 条留在这一天</small></span><Icon name="chevron" size={14}/></button>
  {notes.length>0&&<ul className="annotation-day-notes">{notes.map(note=><li key={note.id}><button type="button" className={'highlight-'+note.color} onClick={onList} aria-label={'查看批注 '+note.quote}><blockquote>{note.quote}</blockquote>{note.note&&<p>{note.note}</p>}<small>{note.note?'批注':'高亮'} · 点击查看或编辑</small></button></li>)}</ul>}
 </section>;
}
