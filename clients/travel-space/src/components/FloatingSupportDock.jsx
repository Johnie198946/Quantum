import React,{useCallback,useEffect,useId,useLayoutEffect,useRef,useState} from 'react';
import {AnimatePresence,motion,useReducedMotion} from 'motion/react';
import {Icon} from './UI';
import {flightOrigin} from './FlyingPanel';
import './FloatingSupportDock.css';

const storageKey='quantum-travel-support-dock-v1',targetSize=44,idleDelay=700;
const clamp=(value,min,max)=>Math.min(max,Math.max(min,value));
function savedPosition(){
 try{const value=JSON.parse(sessionStorage.getItem(storageKey));if(value&&['left','right'].includes(value.side)&&Number.isFinite(value.fraction))return{side:value.side,fraction:clamp(value.fraction,0,1)};}catch{}
 return {side:'right',fraction:1};
}
function limits(phone){return {width:phone.clientWidth,maxX:Math.max(0,phone.clientWidth-targetSize),minY:58,maxY:Math.max(58,phone.clientHeight-122)};}

export default function FloatingSupportDock({stage,pendingCount,triggerRef,blocked,onTodo,onChat,confirmation,onConfirm}){
 const root=useRef(null),gesture=useRef(null),suppressClick=useRef(false),idleTimer=useRef(null),position=useRef(savedPosition()),pointRef=useRef({x:0,y:58}),bounds=useRef(null);
 const [point,setPoint]=useState(pointRef.current),[side,setSide]=useState(position.current.side),[diameter,setDiameter]=useState(19.5),[expanded,setExpanded]=useState(false),[dragging,setDragging]=useState(false),[scrolling,setScrolling]=useState(false);
 const reduced=useReducedMotion(),menuId=useId();
 const moveTo=useCallback(next=>{pointRef.current=next;setPoint(next);},[]);
 const reveal=useCallback(()=>{clearTimeout(idleTimer.current);setScrolling(false);},[]);
 const save=useCallback((nextSide,nextPoint)=>{
  const range=bounds.current;if(!range)return;
  const value={side:nextSide,fraction:(nextPoint.y-range.minY)/(range.maxY-range.minY||1)};
  position.current=value;setSide(nextSide);try{sessionStorage.setItem(storageKey,JSON.stringify(value));}catch{}
 },[]);
 const snap=useCallback(()=>{
  const range=bounds.current;if(!range)return;
  const nextSide=pointRef.current.x+targetSize/2<range.width/2?'left':'right';
  const next={x:nextSide==='left'?0:range.maxX,y:clamp(pointRef.current.y,range.minY,range.maxY)};
  save(nextSide,next);moveTo(next);
 },[moveTo,save]);

 useLayoutEffect(()=>{
  const phone=root.current?.closest('.phone');if(!phone)return;
  let frame;
  const measure=()=>{
   const range=limits(phone);bounds.current=range;
   if(!gesture.current){const {side:edge,fraction}=position.current;moveTo({x:edge==='left'?0:range.maxX,y:range.minY+fraction*(range.maxY-range.minY)});}
   const label=[...phone.querySelectorAll('.interest-row .requirement-copy strong')].find(element=>element.textContent.trim()==='徒步');
   if(label){const height=parseFloat(getComputedStyle(label).lineHeight);if(Number.isFinite(height))setDiameter(height);}
  };
  const schedule=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(measure);};
  const resize=new ResizeObserver(schedule);resize.observe(phone);
  const mutation=new MutationObserver(schedule);mutation.observe(phone,{childList:true,subtree:true});
  window.addEventListener('resize',schedule);measure();
  return()=>{cancelAnimationFrame(frame);resize.disconnect();mutation.disconnect();window.removeEventListener('resize',schedule);};
 },[stage,moveTo]);
 useEffect(()=>{
  const phone=root.current?.closest('.phone');if(!phone)return;
  const scroll=event=>{
   if(blocked||gesture.current||event.target instanceof Element&&event.target.closest('.sheet-overlay,.floating-support-dock'))return;
   setExpanded(false);setScrolling(true);clearTimeout(idleTimer.current);
   idleTimer.current=setTimeout(()=>setScrolling(false),idleDelay);
  };
  phone.addEventListener('scroll',scroll,true);
  return()=>{phone.removeEventListener('scroll',scroll,true);clearTimeout(idleTimer.current);};
 },[blocked]);
 useEffect(()=>{setExpanded(false);reveal();},[stage,blocked,reveal]);
 useEffect(()=>{
  if(!expanded)return;
  const outside=event=>{if(!root.current?.contains(event.target))setExpanded(false);};
  const escape=event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();setExpanded(false);triggerRef.current?.focus();}};
  document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape,true);
  return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape,true);};
 },[expanded,triggerRef]);

 const start=event=>{
  if(!event.isPrimary||event.pointerType==='mouse'&&event.button!==0)return;
  const phone=root.current?.closest('.phone');if(!phone)return;
  reveal();suppressClick.current=false;
  const rect=phone.getBoundingClientRect();
  gesture.current={id:event.pointerId,x:event.clientX,y:event.clientY,point:pointRef.current,scale:rect.width/phone.clientWidth||1,moved:false};
  event.currentTarget.setPointerCapture(event.pointerId);
 };
 const move=event=>{
  const current=gesture.current,range=bounds.current;if(!current||current.id!==event.pointerId||!range)return;
  const dx=(event.clientX-current.x)/current.scale,dy=(event.clientY-current.y)/current.scale;
  if(!current.moved&&Math.hypot(dx,dy)<5)return;
  current.moved=true;setDragging(true);setExpanded(false);
  moveTo({x:clamp(current.point.x+dx,0,range.maxX),y:clamp(current.point.y+dy,range.minY,range.maxY)});
 };
 const finish=(event,cancel=false)=>{
  const current=gesture.current;if(!current||current.id!==event.pointerId)return;
  gesture.current=null;setDragging(false);
  if(current.moved){suppressClick.current=true;snap();}
  else if(cancel)suppressClick.current=true;
 };
 const toggle=event=>{
  if(suppressClick.current&&event.detail!==0){suppressClick.current=false;return;}
  suppressClick.current=false;reveal();setExpanded(value=>!value);
 };
 const action=(event,callback)=>{
  const origin=flightOrigin(event.currentTarget);setExpanded(false);reveal();triggerRef.current?.focus();callback(origin);
 };
 const transition=reduced||dragging?{duration:0}:{type:'spring',stiffness:430,damping:32,mass:.75};
 const hiddenOffset=scrolling&&!dragging&&!expanded?(side==='left'?-22:22):0,inward=side==='left'?1:-1;
 return <motion.div ref={root} className="flow-support-actions floating-support-dock" data-side={side} data-scrolling={scrolling} data-dragging={dragging} data-expanded={expanded}
  style={{'--support-orb-size':diameter+'px'}} initial={false} animate={{x:point.x+hiddenOffset,y:point.y}} transition={transition}>
  <button ref={triggerRef} type="button" className="support-orb-trigger" aria-label="旅行助手" aria-description={pendingCount+'项旅行待办，打开'+(confirmation||'待办')+'与AI建议'} aria-controls={menuId} aria-expanded={expanded}
   onPointerDown={start} onPointerMove={move} onPointerUp={event=>finish(event)} onPointerCancel={event=>finish(event,true)} onLostPointerCapture={event=>finish(event,true)} onClick={toggle} onFocus={reveal}>
   <span className="support-orb" aria-hidden="true"><span>{expanded?'×':'?'}</span></span>
   {pendingCount>0&&<span className="support-orb-dot" aria-hidden="true"/>}
  </button>
  <AnimatePresence>{expanded&&!blocked&&<motion.div id={menuId} className="support-dock-menu" role="group" aria-label="旅行助手操作" initial={false} exit={{opacity:0}} transition={{duration:reduced?0:.14}}>
   <motion.button type="button" className={'glass flow-todo-bubble'+(confirmation?' support-confirm':'')} data-action={confirmation?'confirm':'todos'} aria-label={confirmation||'旅行待办，'+pendingCount+'项待处理'} initial={reduced?false:{x:0,scale:.35,opacity:0}} animate={{x:inward*52,scale:1,opacity:1}} exit={{x:0,scale:.35,opacity:0}} transition={transition} onClick={event=>action(event,confirmation?onConfirm:onTodo)}><Icon name={confirmation?"check":"list"} size={17}/>{pendingCount>0&&<span>{pendingCount}</span>}</motion.button>
   <motion.button type="button" className="glass flow-chat-bubble" aria-label="与AI沟通旅行建议" initial={reduced?false:{x:0,scale:.35,opacity:0}} animate={{x:inward*104,scale:1,opacity:1}} exit={{x:0,scale:.35,opacity:0}} transition={transition} onClick={event=>action(event,onChat)}><Icon name="thought" size={21}/></motion.button>
  </motion.div>}</AnimatePresence>
 </motion.div>;
}
