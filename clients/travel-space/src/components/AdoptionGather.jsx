import React, { useEffect, useRef, useState } from 'react';
import { motion, useIsPresent, useReducedMotion } from 'motion/react';
import TravelThinkingOrb from './TravelThinkingOrb';
import { Icon } from './UI';
import { dayNumber } from './mapRoute';

// Use the same content for the resting card and its non-interactive flight copy.
export function AdoptCardContent({day, onView, preview=false, expanded=false}) {
  return <>
    <img src={day.image} alt={preview?'':day.place+'视觉参考'} draggable="false"/>
    <div className="final-photo-copy"><small>DAY {String(dayNumber(day)).padStart(2,'0')} · {day.date}</small><h2 className={day.place.length>12?'long-place-title':undefined}>{day.place}</h2><p>{day.name}</p></div>
    {preview?<span className="final-view"><Icon name="down" size={12}/></span>:
      <button className="final-view" aria-label={'展开第'+dayNumber(day)+'天详情'} aria-expanded={expanded} onClick={onView}><Icon name="down" size={12}/></button>}
  </>;
}

export function captureAdoptionFlight(host, days) {
  const box=host.getBoundingClientRect(),list=host.querySelector('.adopt-canvas').getBoundingClientRect();
  const sx=box.width/host.clientWidth,sy=box.height/host.clientHeight;
  const cards=[...host.querySelectorAll('[data-adoption-card]')].map(el=>{
    const rect=el.closest('.final-photo-card').getBoundingClientRect();
    const height=el.offsetHeight+2;
    return {day:days.find(d=>String(d.id)===el.dataset.adoptionCard),x:(rect.left-box.left)/sx,y:(rect.top-box.top)/sy,
      width:rect.width/sx,height:height,cropTop:Math.min(rect.height,Math.max(0,list.top-rect.top))/sy,
      cropBottom:Math.min(rect.height,Math.max(0,rect.top+height*sy-list.bottom))/sy};
  });
  return {cards,target:{x:host.clientWidth/2,y:host.clientHeight/2}};
}

export default function AdoptionGather({flight,onComplete}) {
  const reduced=useReducedMotion(),present=useIsPresent();
  const [settled,setSettled]=useState(false);
  const status=useRef(null);
  const {cards,target,direction='gather'}=flight,expanding=direction==='expand';
  useEffect(()=>{status.current?.focus({preventScroll:true});},[]);
  useEffect(()=>{
    if(!present||(!reduced&&!settled&&cards.length))return;
    const timer=setTimeout(onComplete,reduced?220:expanding?100:520);
    return ()=>clearTimeout(timer);
  },[reduced,settled,onComplete,cards.length,present,expanding]);
  const phase=expanding?(settled?'expanded':'expanding'):(settled?'collected':'gathering');
  return <div className={'adoption-gather'+(reduced?' is-reduced':'')+(expanding?' is-unfolding':'')} data-phase={phase}>
    <motion.div className="adoption-veil" aria-hidden="true" initial={{opacity:expanding?1:0}} animate={{opacity:expanding?0:1}}
      transition={{duration:reduced?.12:expanding?1.2:.32}}/>
    {!reduced&&cards.map((card,i)=>{
      const dx=target.x-card.x-card.width/2,dy=target.y-card.y-card.height/2;
      const crop=`inset(${card.cropTop}px 0px ${card.cropBottom}px 0px round 22px)`,full='inset(0px 0px 0px 0px round 22px)';
      return <motion.div key={card.day.id} className="glass final-photo-card adopt-surface-card adoption-flight-card" data-flight-day={card.day.id} aria-hidden="true"
        style={{left:card.x,top:card.y,width:card.width,height:card.height,transformOrigin:'50% 50%'}}
        initial={expanding?{x:dx,y:dy,scale:0,opacity:0,rotate:0,clipPath:full}:{x:0,y:0,scale:1,opacity:1,rotate:0,clipPath:crop}}
        animate={expanding?{
          x:[dx,dx,dx*.12,0],y:[dy,dy,dy*.12,0],scale:[0,.12,.96,1],opacity:[0,.65,1,1],
          rotate:[0,(i%2?-1:1)*4,(i%2?-1:1)*1.5,0],clipPath:[full,full,full,crop]
        }:{
          x:[0,dx*.12,dx,dx],y:[0,dy*.12,dy,dy],scale:[1,.96,.12,0],opacity:[1,1,.65,0],
          rotate:[0,(i%2?-1:1)*1.5,(i%2?-1:1)*4,0],clipPath:[crop,full,full,full]
        }}
        transition={{delay:.12+i*.07,duration:.76,times:expanding?[0,.12,.82,1]:[0,.18,.88,1],ease:[.25,.1,.25,1]}}
        onAnimationComplete={()=>{if(i===cards.length-1)setSettled(true);}}>
        <img className="adopt-card-backdrop" src={card.day.image} alt="" aria-hidden="true"/><div className="adopt-card-header"><AdoptCardContent day={card.day} preview/></div>
      </motion.div>;
    })}
    <div className="adoption-orb-anchor" style={{left:target.x,top:target.y}}>
      <motion.div className="adoption-orb-core" aria-hidden="true" initial={{opacity:expanding?1:0,scale:reduced||expanding?1:.9}}
        animate={{opacity:expanding&&settled?0:1,scale:1}} transition={{duration:reduced?.12:.4}}><TravelThinkingOrb/></motion.div>
      <motion.p ref={status} className="adoption-gather-status" role="status" tabIndex={-1}
        initial={{opacity:reduced||expanding?1:0}} animate={{opacity:reduced||expanding||settled?1:0}}
        transition={{duration:reduced?0:.18}}>{expanding?'正在展开每一天的风景…':'正在收好这份旅程…'}</motion.p>
    </div>
  </div>;
}
