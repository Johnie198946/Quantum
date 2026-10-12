import React,{useRef,useId,useState,useCallback} from 'react';
import {AnimatePresence} from 'motion/react';
import {Icon} from '../UI';
import FlyingPanel,{flightOrigin} from '../FlyingPanel';
export default function ServiceAccordion({items,active,onChange,children}){
 const id=useId(),buttons=useRef([]),[origin,setOrigin]=useState(null);
 const close=useCallback(()=>onChange(null),[onChange]);
 const choose=(index)=>{setOrigin(flightOrigin(buttons.current[index]));onChange(items[index][0]);};
 return <div className="service-accordion horizontal-accordion fly-service-accordion">
 <nav className="service-accordion-panels" aria-label="旅行服务">{items.map(([key,text,icon],i)=><section key={key} className="service-accordion-panel"><button ref={el=>buttons.current[i]=el} id={id+'-'+key+'-trigger'} type="button" className="service-accordion-trigger" data-pending-key={'service-'+key} aria-label={text} aria-expanded={active===key} aria-controls={id+'-'+key} onClick={()=>choose(i)} onKeyDown={e=>{const index=['ArrowRight','ArrowDown'].includes(e.key)?(i+1)%items.length:['ArrowLeft','ArrowUp'].includes(e.key)?(i+items.length-1)%items.length:e.key==='Home'?0:e.key==='End'?items.length-1:null;if(index!==null){e.preventDefault();buttons.current[index]?.focus();}}}><small aria-hidden="true">{String(i+1).padStart(2,'0')}</small><Icon name={icon} size={16}/><span>{text}</span><Icon name="chevron" size={12}/></button></section>)}</nav>
 <AnimatePresence>{active&&<FlyingPanel key={active} origin={origin||flightOrigin(buttons.current[items.findIndex(x=>x[0]===active)])} label={items.find(x=>x[0]===active)?.[1]+'规划'} className="service-flying-panel" onClose={close}><header className="fly-panel-heading"><small>YOUR JOURNEY</small><h2>{items.find(x=>x[0]===active)?.[1]}</h2></header><div id={id+'-'+active} className="service-panel-body" role="region" aria-label={items.find(x=>x[0]===active)?.[1]+'规划内容'}>{children}</div></FlyingPanel>}</AnimatePresence>
 </div>;
}
