import FloatingField from '../FloatingField';
import React,{useState} from 'react';
import {AnimatePresence,motion,useReducedMotion} from 'motion/react';
import {Icon} from '../UI';
export default function InlinePassengers({value,onChange,scope='航班'}){
 const [open,setOpen]=useState(false),reduced=useReducedMotion();
 const count=Number.isInteger(Number(value))?Math.min(20,Math.max(1,Number(value))):1;
 return <div className="inline-passengers"><span>同行人数</span><div className="passenger-control">{open&&<motion.label initial={reduced?false:{opacity:0,x:12}} animate={{opacity:1,x:0}} className="passenger-number"><span className="sr-only">{scope}同行人数</span><FloatingField type="number" aria-label={scope+'同行人数'} min={1} max={20} value={count} onChange={e=>{const n=+e.target.value;if(Number.isInteger(n)&&n>=1&&n<=20)onChange(n);}}/></motion.label>}<motion.button layout type="button" className="passenger-icons" aria-label={'调整'+scope+'同行人数，当前 '+count+' 人'} aria-expanded={open} onClick={()=>setOpen(!open)} transition={reduced?{duration:0}:{type:'spring',stiffness:480,damping:26}}><AnimatePresence initial={false}>{Array.from({length:count},(_,i)=><motion.span key={i} layout className="passenger-person" initial={reduced?false:{opacity:0,scale:.65,y:4}} animate={{opacity:1,scale:1,y:0}} exit={{opacity:0,scale:.65}} transition={{duration:reduced?0:.18}}><Icon name="person" size={17}/></motion.span>)}</AnimatePresence></motion.button></div></div>;
}
