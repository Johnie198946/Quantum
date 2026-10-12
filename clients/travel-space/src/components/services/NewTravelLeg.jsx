import FloatingField from '../FloatingField';
import React,{useState} from 'react';
import {motion,AnimatePresence,useReducedMotion} from 'motion/react';
import {Icon} from '../UI';
import {routeModes} from './route-model';
export default function NewTravelLeg({onAdd}){
 const [open,setOpen]=useState(false),[name,setName]=useState(''),[mode,setMode]=useState('公交车'),[error,setError]=useState(''),reduced=useReducedMotion();
 const confirm=()=>{if(!open){setOpen(true);return;}if(!name.trim()){setError('给这段交通起个名字');return;}onAdd({id:'custom-'+Date.now(),name:name.trim().slice(0,60),mode});setOpen(false);setName('');setError('');};
 return <div className="new-leg"><motion.button type="button" className={'icon-btn new-leg-toggle'+(open?' is-confirm':'')} aria-label={open?'确认新增交通段':'新增交通段'} aria-expanded={open} animate={{rotate:open?-360:0}} transition={reduced?{duration:0}:{type:'spring',stiffness:180,damping:23}} onClick={confirm}><Icon name={open?'check':'plus'} size={18}/></motion.button><AnimatePresence>{open&&<motion.div className="new-leg-card glass" initial={reduced?false:{opacity:0,height:0,y:-8}} animate={{opacity:1,height:'auto',y:0}} exit={{opacity:0,height:0}}><label>这段交通叫什么<FloatingField autoFocus aria-label="新增交通段名称" maxLength={60} value={name} placeholder="例如：去码头看海" onChange={e=>{setName(e.target.value);setError('');}} onKeyDown={e=>{if(e.key==='Enter'&&!e.nativeEvent.isComposing){e.preventDefault();confirm();}if(e.key==='Escape'){e.stopPropagation();setOpen(false);}}}/></label><div className="new-leg-modes" role="group" aria-label="新交通段方式">{routeModes.filter(x=>x[0]!=='地铁').map(([text,icon])=><button type="button" key={text} aria-label={'新交通段'+text} aria-pressed={mode===text} onClick={()=>setMode(text)}><Icon name={icon} size={14}/><span>{text}</span></button>)}</div>{error&&<p role="status">{error}</p>}<button type="button" className="new-leg-cancel" onClick={()=>setOpen(false)}>取消</button></motion.div>}</AnimatePresence></div>;
}
