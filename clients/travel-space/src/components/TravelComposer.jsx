import FloatingField from './FloatingField';
import React,{useRef,useLayoutEffect} from 'react';
import {motion,useReducedMotion} from 'motion/react';
import {BorderBeam} from 'border-beam';
import {Icon} from './UI';
export default function TravelComposer({label,sendLabel,placeholder,value,onChange,onSubmit,disabled=false,drawer=false}){
 const reduced=useReducedMotion();
 const field=useRef(null);
 useLayoutEffect(()=>{
  const el=field.current;if(!el)return;
  const resize=()=>{el.style.height='0px';const height=Math.min(132,Math.max(24,el.scrollHeight));el.style.height=height+'px';el.style.overflowY=el.scrollHeight>132?'auto':'hidden';};
  resize();const observer=new ResizeObserver(entries=>{const width=entries[0]?.contentRect.width;if(width!==Number(el.dataset.width)){el.dataset.width=String(width);resize();}});observer.observe(el);
  return()=>observer.disconnect();
 },[value]);
 return <motion.div className={'composer-shell'+(drawer?' drawer-composer':'')} initial={{y:drawer?16:100,opacity:0}} animate={{y:0,opacity:1}} exit={{y:100,opacity:0}}>
  <BorderBeam className="travel-beam" size="md" colorVariant="ocean" strength={.7} theme="light" duration={4.8} staticColors borderRadius={25} active={!disabled&&!reduced} style={{'--beam-stroke-opacity':4,'--beam-inner-opacity':1.7}}>
   <form className="glass composer" onSubmit={onSubmit}><FloatingField as="textarea" ref={field} rows={1} aria-label={label} autoComplete="off" placeholder={placeholder} value={value} onChange={onChange} disabled={disabled} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing&&e.keyCode!==229){e.preventDefault();if(!disabled&&value.trim())e.currentTarget.form.requestSubmit();}}}/><motion.button type="submit" aria-label={sendLabel} disabled={disabled||!value.trim()} whileTap={{scale:.85}}><Icon name="arrow"/></motion.button></form>
  </BorderBeam>
 </motion.div>;
}
