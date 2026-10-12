import React,{useEffect,useRef,useState} from 'react';
import {motion,useReducedMotion} from 'motion/react';
import {Icon} from './UI';
const icons={经济:'leaf',适中:'sliders',舒适:'home',不限:'globe',轻松:'leaf',充实:'layers',公共交通:'bus',自驾:'car',包车:'person',未定:'thought'};
const hints={经济:'把预算留给体验',适中:'舒适与花费平衡',舒适:'多一些自在',不限:'先按喜欢来',轻松:'少些站点，多些停留',充实:'走走看看，日程更满',公共交通:'公交、铁路与渡轮衔接',自驾:'灵活停靠，慢慢看沿途',包车:'同行分摊，少些接驳'};
export default function IntentTray({field,open,value,onSelect,onFinish}){
 const reduced=useReducedMotion(),timer=useRef(null),[picked,setPicked]=useState(false);
 useEffect(()=>{setPicked(false);return()=>clearTimeout(timer.current);},[open]);
 const choose=next=>{clearTimeout(timer.current);setPicked(true);onSelect(next);timer.current=setTimeout(onFinish,reduced?80:430);};
 return <motion.div id={'choices-'+field.id} className={'intent-tray'+(open?' is-open':'')} role="group" aria-label={field.title} initial={false} animate={{height:open?100:10}} transition={reduced?{duration:0}:{type:'spring',stiffness:340,damping:30}} onKeyDown={e=>{if(e.key==='Escape'){e.stopPropagation();onFinish();}}}>
  {open&&<motion.div className="intent-tray-content" initial={reduced?false:{opacity:0,y:-6}} animate={{opacity:1,y:0}} transition={{duration:reduced?0:.18,delay:reduced?0:.08}}>
   <div className="intent-buttons" role="group" aria-label={field.title+'选项'}>{field.options.filter(x=>field.id==='budget'?x!=='未定':true).map(x=><motion.button layout type="button" key={x} aria-label={x} aria-pressed={value===x} className={value===x?'is-picked':''} onClick={()=>choose(x)} transition={reduced?{duration:0}:{type:'spring',stiffness:420,damping:27}} whileTap={reduced?undefined:{scale:.93}}><Icon name={icons[x]} size={17}/>{value===x&&<motion.span initial={{opacity:0,width:0}} animate={{opacity:1,width:'auto'}}>{x}</motion.span>}</motion.button>)}</div>
   <p role="status">{value&&value!=='未定'?hints[value]:'选一个图标，展开你的偏好'}{picked&&<span> · 已选</span>}</p>
  </motion.div>}
 </motion.div>;
}
