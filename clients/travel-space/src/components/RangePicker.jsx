import React, { useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { Sheet, Icon, Primary } from './UI';
import HorizontalTimeRange from './HorizontalTimeRange';

const DAY = 86400000;
export const isoDay = value => Math.floor(Date.parse(value + 'T00:00:00Z') / DAY);
export const dayISO = value => new Date(value * DAY).toISOString().slice(0,10);
export const dateLabel = value => { const d = new Date(value * DAY); return (d.getUTCMonth()+1) + '月' + d.getUTCDate() + '日'; };
export function readTime(item) {
  const toSlot = value => { const match = /^(\d{1,2}):(\d{2})/.exec(value || ''); return match ? Math.max(0,Math.min(48,Math.round((+match[1]*60 + +match[2])/30))) : 18; };
  const start = Math.min(47,toSlot(item.time)), end = item.endTime ? toSlot(item.endTime) : Math.min(48,start+2);
  return [start, Math.max(start, Math.min(47, end-1))];
}
export function readDates(profile) {
  if (profile.dateRange) { const stored=profile.dateRange.map(isoDay); if(stored.every(Number.isFinite)&&stored.map(dateLabel).join(' — ')===profile.dates)return stored; }
  const matches = [...profile.dates.matchAll(/(\d{1,2})月(\d{1,2})日/g)];
  const year = 2026;
  if (matches.length === 2) {
    const start = Math.floor(Date.UTC(year,+matches[0][1]-1,+matches[0][2])/DAY);
    let end = Math.floor(Date.UTC(year,+matches[1][1]-1,+matches[1][2])/DAY);
    if (end < start) end = Math.floor(Date.UTC(year+1,+matches[1][1]-1,+matches[1][2])/DAY);
    return [start,end];
  }
  const today = Math.floor(Date.now()/DAY); return [today,today+3];
}

// One contiguous interval, with two endpoint handles. Dragging never creates
// disconnected selections; crossing a handle clamps it to the other endpoint.
function useRangeGesture(initial, bounds) {
  const [range, setRange] = useState(initial), [dragging, setDragging] = useState(false);
  const root = useRef(null), session = useRef(null), current = useRef(range);
  current.current = range;
  const fromPoint = event => {
    const cells = [...root.current.querySelectorAll('[data-range-cell]')];
    let nearest = null, distance = Infinity;
    for (const cell of cells) {
      const r = cell.getBoundingClientRect(), dx = Math.max(r.left-event.clientX,0,event.clientX-r.right), dy = Math.max(r.top-event.clientY,0,event.clientY-r.bottom);
      if (dx*dx + dy*dy < distance) { nearest = +cell.dataset.rangeCell; distance = dx*dx + dy*dy; }
    }
    return nearest;
  };
  const apply = index => {
    const s = session.current;
    if (!s || index === null) return;
    const [low,high] = current.current;
    const next = s.kind === 'start' ? [Math.min(index,high),high] : s.kind === 'end' ? [low,Math.max(index,low)] : [Math.min(s.anchor,index),Math.max(s.anchor,index)];
    current.current = next; setRange(next);
  };
  const pointerDown = (event, kind, index) => {
    if (event.button !== 0 || session.current) return;
    event.preventDefault(); event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    if(kind==='select'&&event.shiftKey)kind=index<range[0]?'start':'end';
    session.current = { kind, anchor:index, prior:[...range], pointer:event.pointerId };
    setDragging(true); apply(index);
  };
  const pointerMove = event => {
    if (session.current?.pointer !== event.pointerId) return;
    event.preventDefault();
    const strip = root.current;
    if (strip.scrollWidth > strip.clientWidth) { const r=strip.getBoundingClientRect(); if(event.clientX>r.right-28)strip.scrollLeft+=14; else if(event.clientX<r.left+28)strip.scrollLeft-=14; }
    apply(fromPoint(event));
  };
  const finish = (event, cancel = false) => {
    if (session.current?.pointer !== event.pointerId) return;
    if (cancel) { setRange(session.current.prior); current.current = session.current.prior; }
    session.current = null; setDragging(false);
  };
  const key = (event, kind) => {
    const amount = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1 : event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : 0;
    if (!amount && !['Home','End'].includes(event.key)) return;
    event.preventDefault(); const at = kind === 'start' ? 0 : 1;
    const next = [...range]; next[at] = event.key === 'Home' ? bounds[0] : event.key === 'End' ? bounds[1] : next[at]+amount;
    next[at] = Math.max(at === 0 ? bounds[0] : next[0], Math.min(at === 0 ? next[1] : bounds[1], next[at]));
    setRange(next);
  };
  return { range, setRange, root, dragging, pointerDown, pointerMove, finish, key };
}

export default function RangePicker(props) {
  return props.kind==='time'?<HorizontalTimeRange {...props}/>:<DateRangePicker {...props}/>;
}
function DateRangePicker({ initial, onClose, onConfirm }) {
  const [month, setMonth] = useState(() => new Date(initial[0]*DAY));
  const year = month.getUTCFullYear(), monthIndex = month.getUTCMonth();
  const first = Math.floor(Date.UTC(year,monthIndex,1)/DAY), last = Math.floor(Date.UTC(year,monthIndex+1,0)/DAY);
  const g = useRangeGesture(initial, [first-3660,last+3660]);
  const [start,end] = g.range;
  const cells = Array.from({length:last-first+1},(_,i)=>first+i);
  const endpoint = side => <button type="button" className={'range-handle handle-'+side} role="slider" aria-label={side === 'start' ? '调整开始日期' : '调整结束日期'} aria-valuemin={first-3660} aria-valuemax={last+3660} aria-valuenow={side === 'start'?start:end} aria-valuetext={dateLabel(side === 'start'?start:end)} onPointerDown={e=>g.pointerDown(e,side,side==='start'?start:end)} onKeyDown={e=>g.key(e,side)}><span/><span/></button>;
  return <Sheet label="选择旅行日期" className="range-sheet date-range-sheet" onClose={onClose}>
    <p className="eyebrow">给旅程，留几天空白</p>
    <h2>什么时候出发</h2>
    <div className="range-value" role="status" aria-live="polite"><strong>{dateLabel(start)}</strong><span>—</span><strong>{dateLabel(end)}</strong></div>
    <div className="calendar-heading"><button className="icon-btn" aria-label="上个月" onClick={()=>setMonth(new Date(Date.UTC(year,monthIndex-1,1)))}><Icon name="back" size={18}/></button><span>{year}年 · {monthIndex+1}月</span><button className="icon-btn" aria-label="下个月" onClick={()=>setMonth(new Date(Date.UTC(year,monthIndex+1,1)))}><Icon name="chevron" size={18}/></button></div>
    <div className="calendar-week" aria-hidden="true">{'一二三四五六日'.split('').map(d=><span key={d}>{d}</span>)}</div>
    <div ref={g.root} className={'range-grid date-grid'+(g.dragging?' selecting':'')} onPointerMove={g.pointerMove} onPointerUp={e=>g.finish(e)} onPointerCancel={e=>g.finish(e,true)} onLostPointerCapture={e=>g.finish(e)}>
      {cells.map((index,i)=>{const selected=index>=start&&index<=end, isStart=index===start, isEnd=index===end;return <div className={'range-cell '+(selected?'in-range ':'')+(isStart?'range-start ':'')+(isEnd?'range-end':'')} key={index} data-range-cell={index} style={i===0?{gridColumnStart:(new Date(first*DAY).getUTCDay()+6)%7+1}:undefined}>
        <motion.button type="button" className="range-slot" aria-label={dateLabel(index)} aria-pressed={selected} onPointerDown={e=>g.pointerDown(e,'select',index)} onClick={e=>{if(e.detail===0)g.setRange(e.shiftKey?[Math.min(start,index),Math.max(end,index)]:[index,index]);}} whileTap={{scale:.96}}><strong>{new Date(index*DAY).getUTCDate()}</strong></motion.button>
        {isStart&&endpoint('start')}{isEnd&&endpoint('end')}
      </div>;})}
    </div>
    {(start<first||end>last)&&<div className="calendar-endpoints"><button aria-label="查看开始日期" onClick={()=>setMonth(new Date(start*DAY))}>{dateLabel(start)}</button><button aria-label="查看结束日期" onClick={()=>setMonth(new Date(end*DAY))}>{dateLabel(end)}</button></div>}
    <p className="range-hint">拖过想要的日期，或拉动两端微调</p>
    <Primary onClick={()=>onConfirm(g.range)}>确认日期</Primary>
  </Sheet>;
}
