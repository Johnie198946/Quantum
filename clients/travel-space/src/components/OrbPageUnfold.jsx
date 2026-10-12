import React, { useLayoutEffect, useRef, useState } from 'react';
import { motion, useIsPresent, useReducedMotion } from 'motion/react';
import TravelThinkingOrb from './TravelThinkingOrb';

export default function OrbPageUnfold({children,onComplete}) {
  const host=useRef(null),complete=useRef(false);
  const reduced=useReducedMotion(),present=useIsPresent();
  const [radius,setRadius]=useState(null);
  useLayoutEffect(()=>{
    const measure=()=>setRadius(Math.hypot(host.current.clientWidth,host.current.clientHeight)/2+2);
    const observer=new ResizeObserver(measure);observer.observe(host.current);measure();
    return ()=>observer.disconnect();
  },[]);
  return <div ref={host} className="orb-page-unfold" data-testid="orb-page-unfold">
    {radius!==null&&<motion.div className="orb-page-content" inert="" aria-hidden="true"
      initial={{clipPath:reduced?'none':'circle(0px at 50% 50%)'}}
      animate={{clipPath:reduced?'none':`circle(${radius||0}px at 50% 50%)`}}
      transition={{duration:reduced?.12:.9,ease:[.3,0,.25,1]}}
      onAnimationComplete={()=>{if(radius&&present&&!complete.current){complete.current=true;onComplete();}}}>
      {children}
    </motion.div>}
    <motion.div className="orb-page-core" initial={{opacity:1,scale:1}} animate={{opacity:0,scale:reduced?1:1.08}}
      transition={{delay:reduced?0:.42,duration:reduced?.12:.4}}><TravelThinkingOrb/></motion.div>
    <p className="orb-unfold-status" role="status">正在展开这份旅程…</p>
  </div>;
}
