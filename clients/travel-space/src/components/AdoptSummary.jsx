import React,{useRef,useEffect} from 'react';
import {motion,useMotionValue,useTransform,animate,useReducedMotion} from 'motion/react';
import {Icon,spring} from './UI';
import {AdoptCardContent} from './AdoptionGather';
export default function AdoptSummary({day,expanded,onExpand,onSetExpanded,onPull,onAI,children,preview=false}){
 const reduced=useReducedMotion(),progress=useMotionValue(expanded?1:0),height=useTransform(progress,v=>94+v*156),radius=useTransform(progress,v=>22-v*4),opacity=useTransform(progress,[0,.25,1],[0,0,1]),gesture=useRef(null),control=useRef(null),suppress=useRef(false);
 useEffect(()=>{control.current?.stop();if(reduced)progress.set(expanded?1:0);else control.current=animate(progress,expanded?1:0,spring);return()=>control.current?.stop();},[expanded,reduced]);
 function down(e){if(e.button!==0||preview||e.target.closest('.adopt-ai-orb,[data-reorder-handle]'))return;e.stopPropagation();suppress.current=false;control.current?.stop();gesture.current={id:e.pointerId,y:e.clientY,start:progress.get()};e.currentTarget.setPointerCapture(e.pointerId);}
 function move(e){const g=gesture.current;if(!g||g.id!==e.pointerId)return;const dy=e.clientY-g.y;if(Math.abs(dy)>5)suppress.current=true;const next=Math.max(0,Math.min(1,g.start+dy/156));progress.set(next);onPull?.(next);}
 function finish(e,cancel=false){const g=gesture.current;if(!g||g.id!==e.pointerId)return;e.stopPropagation();gesture.current=null;const next=(cancel||!suppress.current)?expanded:progress.get()>.38;onPull?.(0);onSetExpanded(next);if(next===expanded){if(reduced)progress.set(next?1:0);else control.current=animate(progress,next?1:0,spring);}}
 return <motion.div className="adopt-card-header adopt-pull-summary" data-adoption-card={preview?undefined:day.id} style={{height,borderRadius:radius,touchAction:preview?'auto':'none'}} onTouchStart={e=>{if(!e.target.closest('[data-reorder-handle]'))e.stopPropagation();}} onPointerDown={down} onPointerMove={move} onPointerUp={e=>finish(e)} onPointerCancel={e=>finish(e,true)} onLostPointerCapture={e=>finish(e,true)} onClickCapture={e=>{if(suppress.current){e.stopPropagation();suppress.current=false;}}}>
  <AdoptCardContent day={day} preview={preview} expanded={expanded} onView={onExpand}/>{children}
  {!preview&&<div className="adopt-reorder-surface" data-reorder-handle data-reorder-surface aria-hidden="true"/>}
  {!preview&&<motion.button className="adopt-ai-orb" aria-label={'与AI调整第'+(day.order||day.id)+'天行程'} onClick={e=>{e.stopPropagation();onAI(e);}} whileTap={reduced?undefined:{scale:.72}}><Icon name="spark" size={14}/></motion.button>}
  <motion.div className="adopt-summary-stats glass" style={{opacity}} aria-hidden={!expanded} inert={!expanded?'':undefined}><p>这一天，慢慢展开。</p><dl><div><dt>停留安排</dt><dd>{day.items.length}<small> 项</small></dd></div><div><dt>开始</dt><dd>{day.items[0]?.time||'未定'}</dd></div><div><dt>最后一站</dt><dd>{day.items.at(-1)?.time||'未定'}</dd></div></dl><span>{day.items.map(x=>x.title).join(' → ')}</span></motion.div>
 </motion.div>;
}
