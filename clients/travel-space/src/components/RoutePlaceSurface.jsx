import { dayNumber } from './mapRoute';
import React, { useEffect, useRef, useState } from 'react';
import { motion, useMotionValue, useTransform, animate, useReducedMotion } from 'motion/react';
import { Sheet, Icon, spring } from './UI';
export function photoRevealOrigin(event,host,target=event.currentTarget) {
  const box=host.getBoundingClientRect(),rect=target.getBoundingClientRect();
  const pointer=event.pointerType||event.detail;
  return {x:(pointer?event.clientX:rect.x+rect.width/2)-box.x-16,y:(pointer?event.clientY:rect.y+rect.height/2)-box.y-16,radius:Math.hypot(box.width,box.height)};
}
export default function RoutePlaceSurface({day,origin,label,onClose,children,photoMeta,className=''}) {
  const layout=useRef(null),gesture=useRef(null),controls=useRef(null),suppress=useRef(false);
  const [height,setHeight]=useState(650),[expanded,setExpanded]=useState(false);
  const reduced=useReducedMotion(),progress=useMotionValue(0);
  const panelY=useTransform(progress,value=>height*(.46-.33*value));
  const panelHeight=useTransform(progress,value=>height*(.54+.33*value));
  const photoHeight=useTransform(progress,value=>height*(.54-.38*value));
  const captionOpacity=useTransform(progress,[0,.35,.7,1],[1,.4,0,0]);
  const photoScale=useTransform(progress,value=>1.03-value*.03);
  useEffect(()=>{const observer=new ResizeObserver(()=>setHeight(layout.current.clientHeight));observer.observe(layout.current);return()=>{observer.disconnect();controls.current?.stop();};},[]);
  function settle(value) {setExpanded(value===1);controls.current?.stop();if(reduced)progress.set(value);else controls.current=animate(progress,value,spring);}
  function down(event) {if(event.button!==0)return;controls.current?.stop();suppress.current=false;gesture.current={id:event.pointerId,y:event.clientY,start:progress.get()};event.currentTarget.setPointerCapture(event.pointerId);}
  function move(event) {const active=gesture.current;if(!active||active.id!==event.pointerId)return;const dy=active.y-event.clientY;if(Math.abs(dy)>6)suppress.current=true;progress.set(Math.max(0,Math.min(1,active.start+dy/(height*.33))));}
  function finish(event,cancel=false) {const active=gesture.current;if(!active||active.id!==event.pointerId)return;gesture.current=null;settle(cancel?(active.start>.5?1:0):(progress.get()>.45?1:0));}
  return <Sheet label={label} onClose={onClose} className={'route-place-sheet full-sheet '+className} revealFrom={reduced?undefined:origin}>
    <div ref={layout} className="route-place-layout">
      <motion.figure className="route-place-photo" style={{height:photoHeight}}><motion.div className="route-photo-zoom" initial={{scale:reduced?1:1.2}} animate={{scale:1}} transition={{duration:.8,ease:[.2,.8,.2,1]}}><motion.img src={day.image} alt={day.place+'的目的地视觉参考'} style={{scale:photoScale}}/></motion.div><motion.figcaption style={{opacity:captionOpacity}}><span>{photoMeta || ('DAY '+String(dayNumber(day)).padStart(2,'0')+' / '+day.date)}</span><strong>{day.place}</strong></motion.figcaption></motion.figure>
      <motion.div className="route-detail-panel glass day-detail" style={{y:panelY,height:panelHeight}}>
        <button type="button" className="route-panel-grip" aria-label="展开或收起旅行简述" aria-expanded={expanded} onPointerDown={down} onPointerMove={move} onPointerUp={e=>finish(e)} onPointerCancel={e=>finish(e,true)} onLostPointerCapture={e=>finish(e,true)} onClick={e=>{if(e.detail===0||!suppress.current)settle(progress.get()>.5?0:1);}}><span aria-hidden="true"/></button>
        <div className="route-detail-content">{children}</div>
      </motion.div>
    </div>
  </Sheet>;
}
