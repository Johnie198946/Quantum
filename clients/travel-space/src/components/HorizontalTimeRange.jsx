import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Sheet, Primary } from './UI';

const STEP=32, LAST=48;
export const clockLabel=slot=>String(Math.floor(slot/2)).padStart(2,'0')+':'+(slot%2?'30':'00');
const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));

export default function HorizontalTimeRange({initial,title,onClose,onConfirm}) {
  const [range,setRange]=useState(()=>[initial[0],initial[1]+1]);
  const [mode,setMode]=useState('range'),[padding,setPadding]=useState(0),[dragging,setDragging]=useState(false);
  const strip=useRef(null),session=useRef(null),idle=useRef(null),current=useRef(null);
  current.current={range,mode};
  const [start,end]=range, at=mode==='end'?end:start;
  const bounds=(r,m)=>m==='end'?[r[0]+1,LAST]:m==='start'?[0,r[1]-1]:[0,LAST-(r[1]-r[0])];
  const [min,max]=bounds(range,mode);
  const update=useCallback((slot,selectedMode=current.current.mode)=>{
    const {range:r}=current.current,[low,high]=bounds(r,selectedMode),value=clamp(slot,low,high);
    const next=selectedMode==='end'?[r[0],value]:selectedMode==='start'?[value,r[1]]:[value,value+r[1]-r[0]];
    current.current={range:next,mode:selectedMode};setRange(next);
    return value;
  },[]);
  const snap=useCallback(()=>{
    const el=strip.current;if(!el)return;
    const {range:r,mode:m}=current.current;
    el.scrollTo({left:(m==='end'?r[1]:r[0])*STEP,behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
  },[]);
  useEffect(()=>{
    const el=strip.current;
    const observer=new ResizeObserver(()=>setPadding(Math.max(0,el.clientWidth/2-STEP/2)));
    observer.observe(el);
    el.scrollLeft=initial[0]*STEP;
    const wheel=e=>{
      if(e.ctrlKey)return;
      e.preventDefault();
      const {range:r,mode:m}=current.current,[low,high]=bounds(r,m);
      const delta=Math.abs(e.deltaX)>Math.abs(e.deltaY)?e.deltaX:e.deltaY;
      el.scrollLeft=clamp(el.scrollLeft+delta*.72,low*STEP,high*STEP);
      update(Math.round(el.scrollLeft/STEP));
      clearTimeout(idle.current);idle.current=setTimeout(snap,120);
    };
    el.addEventListener('wheel',wheel,{passive:false});
    return()=>{observer.disconnect();clearTimeout(idle.current);el.removeEventListener('wheel',wheel);};
  },[update,snap]);
  // The first/last tick must be able to sit exactly at the centre, too.
  useEffect(()=>{if(padding)strip.current.scrollLeft=at*STEP;},[padding]);
  function choose(nextMode){
    clearTimeout(idle.current);session.current=null;setDragging(false);
    current.current.mode=nextMode;setMode(nextMode);
    strip.current.scrollTo({left:(nextMode==='end'?current.current.range[1]:current.current.range[0])*STEP,behavior:'instant'});
  }
  function down(e){
    if(e.button!==0)return;
    e.preventDefault();clearTimeout(idle.current);
    strip.current.focus({preventScroll:true});strip.current.setPointerCapture(e.pointerId);
    session.current={pointer:e.pointerId,x:e.clientX,left:strip.current.scrollLeft,range:[...current.current.range],mode:current.current.mode,moved:false};
    setDragging(true);
  }
  function move(e){
    const s=session.current;if(!s||s.pointer!==e.pointerId)return;
    const dx=e.clientX-s.x;if(Math.abs(dx)>3)s.moved=true;
    const [low,high]=bounds(s.range,s.mode);
    strip.current.scrollLeft=clamp(s.left-dx*.72,low*STEP,high*STEP);
    update(Math.round(strip.current.scrollLeft/STEP),s.mode);
  }
  function finish(e,cancel=false){
    const s=session.current;if(!s||s.pointer!==e.pointerId)return;
    session.current=null;setDragging(false);
    if(cancel){current.current.range=s.range;setRange(s.range);}
    else if(!s.moved){
      const r=strip.current.getBoundingClientRect();
      update(Math.round((strip.current.scrollLeft+e.clientX-r.left-r.width/2)/STEP));
    }
    snap();
  }
  function key(e,selectedMode=mode){
    const {range:r}=current.current,[low,high]=bounds(r,selectedMode);
    const value=selectedMode==='end'?r[1]:r[0],delta=e.key==='ArrowRight'||e.key==='ArrowUp'?1:e.key==='ArrowLeft'||e.key==='ArrowDown'?-1:0;
    if(!delta&&!['Home','End'].includes(e.key))return;
    e.preventDefault();choose(selectedMode);
    const next=update(e.key==='Home'?low:e.key==='End'?high:value+delta,selectedMode);
    strip.current.scrollTo({left:next*STEP,behavior:'instant'});
  }
  const endpoint=side=><button type="button" role="slider" aria-label={'调整'+(side==='start'?'开始':'结束')+'时间'} aria-valuemin={side==='start'?0:start+1} aria-valuemax={side==='start'?end-1:LAST} aria-valuenow={side==='start'?start:end} aria-valuetext={clockLabel(side==='start'?start:end)}
    className={'time-endpoint '+(mode===side?'active':'')} onClick={()=>choose(side)} onKeyDown={e=>key(e,side)}>
    <small>{side==='start'?'开始':'结束'}</small><strong>{clockLabel(side==='start'?start:end)}</strong>
  </button>;
  return <Sheet label="选择时间段" className="range-sheet time-range-sheet horizontal-time-sheet" onClose={onClose} closeIconSize={10}>
    <p className="eyebrow">留一段时间，给这片风景</p>
    <h2>{title}</h2>
    <div className="range-value time-range-value">{endpoint('start')}<span>—</span>{endpoint('end')}</div>
    <div className="time-wheel-meta"><button type="button" aria-pressed={mode==='range'} onClick={()=>choose('range')}>整段移动</button><span>{(end-start)*30}分钟</span></div>
    <div className="time-wheel-frame" data-mode={mode}>
      <span className="time-wheel-highlight" aria-hidden="true"/>
      <div ref={strip} className={'time-wheel'+(dragging?' is-dragging':'')} role="slider" tabIndex={0} aria-label="横向时间刻度" aria-valuemin={min} aria-valuemax={max} aria-valuenow={at} aria-valuetext={clockLabel(at)} aria-orientation="horizontal"
        onPointerDown={down} onPointerMove={move} onPointerUp={e=>finish(e)} onPointerCancel={e=>finish(e,true)} onLostPointerCapture={e=>finish(e,true)} onKeyDown={e=>key(e)}
        onScroll={()=>{if(padding&&!session.current)update(Math.round(strip.current.scrollLeft/STEP));}}>
        <div className="time-wheel-track" style={{paddingInline:padding}}>
          {Array.from({length:49},(_,slot)=><span key={slot} data-time-tick={slot} className={'time-tick '+(slot%2?'minor ':'major ')+(slot===at?'is-current ':'')+(slot>=start&&slot<=end?'in-interval':'')}><i aria-hidden="true"/><time>{slot===at||slot%2===0?clockLabel(slot):':30'}</time></span>)}
        </div>
      </div>
      <span className="time-wheel-needle" aria-hidden="true"/>
    </div>
    <p className="range-hint">左右拨动刻度，点起止时间分别调整</p>
    <span className="sr-only" role="status" aria-live="polite">{clockLabel(start)+' — '+clockLabel(end)}</span>
    <Primary onClick={()=>onConfirm({time:clockLabel(start),endTime:clockLabel(end)})}>确认时间段</Primary>
  </Sheet>;
}
