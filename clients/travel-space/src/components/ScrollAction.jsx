import React,{useState,useRef,useCallback} from 'react';
import {motion,useReducedMotion} from 'motion/react';
import {Primary,spring} from './UI';
export function useScrollAction(){
 const [expanded,setExpanded]=useState(true),last=useRef(0),reveal=useCallback(()=>setExpanded(true),[]);
 const onScroll=e=>{const top=e.currentTarget.scrollTop,delta=top-last.current;last.current=top;if(top<8)setExpanded(true);else if(Math.abs(delta)>2)setExpanded(delta<0);};
 return {expanded,reveal,handlers:{onScroll}};
}
export function ScrollAction({expanded,reveal,onClick,disabled,label='确认完善计划'}){
 const reduced=useReducedMotion();
 return <motion.div className={'scroll-action floating-confirm'+(expanded?' is-expanded':' is-compact')} animate={{width:expanded?112:44}} transition={reduced?{duration:0}:spring}><Primary icon="check" aria-label={label} onFocus={reveal} onClick={onClick} disabled={disabled}><motion.span aria-hidden="true" animate={{width:expanded?32:0,opacity:expanded?1:0}} transition={reduced?{duration:0}:{duration:.2}}>确认</motion.span></Primary></motion.div>;
}
