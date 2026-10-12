import React,{useLayoutEffect,useRef,useState} from 'react';
import {motion,useReducedMotion} from 'motion/react';
export const cardRevealTransition={duration:.48,ease:[.2,.8,.2,1]};
export default function CardPageUnfold({origin,children,onComplete}){
 const host=useRef(null),done=useRef(false),reduced=useReducedMotion(),[radius,setRadius]=useState(null);
 useLayoutEffect(()=>{const measure=()=>setRadius(Math.hypot(host.current.clientWidth,host.current.clientHeight));const observer=new ResizeObserver(measure);observer.observe(host.current);measure();return()=>observer.disconnect();},[]);
 const x=origin?.x||180,y=(origin?.y||180)-40;
 return <div ref={host} className="card-page-unfold">{radius!==null&&<motion.div className="card-page-unfold-content" initial={reduced?false:{clipPath:`circle(0px at ${x}px ${y}px)`}} animate={{clipPath:reduced?'none':`circle(${radius}px at ${x}px ${y}px)`}} transition={reduced?{duration:0}:cardRevealTransition} onAnimationComplete={()=>{if(!done.current){done.current=true;onComplete();}}}>{children}</motion.div>}</div>;
}
