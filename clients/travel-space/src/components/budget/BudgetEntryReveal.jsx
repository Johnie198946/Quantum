import React,{forwardRef,useEffect,useImperativeHandle,useLayoutEffect,useRef,useState} from 'react';
import {useReducedMotion} from 'motion/react';
import FlyingPanel from '../FlyingPanel';
import {Icon} from '../UI';
import {formatMoney,parseMoney} from './budget-model';
import './BudgetEntryReveal.css';

const compactHeight=150;
const entryIcons={flight:'plane',transport:'train',hotel:'bed',restaurant:'dining',activity:'ticket',shopping:'bag',other:'receipt'};
const entryLabels={flight:'航班',transport:'交通',hotel:'住宿',restaurant:'餐饮',activity:'体验',shopping:'购物',other:'其他'};

// Keep the source card compact during its flight, then reveal the editable details below it.
export default forwardRef(function BudgetEntryReveal({entry,origin,label,onClose,children,className=''},ref){
 const reduced=useReducedMotion(),summary=useRef(null),alive=useRef(true),closing=useRef(false),timers=useRef(new Set());
 const [phase,setPhase]=useState(reduced?'expanded':'lifting');
 const [availableHeight,setAvailableHeight]=useState(()=>Math.max(compactHeight,(document.querySelector('.phone')?.clientHeight||800)-92));
 const height=phase==='expanded'?availableHeight:compactHeight;
 const schedule=(callback,delay)=>{const id=setTimeout(()=>{timers.current.delete(id);if(alive.current)callback();},delay);timers.current.add(id);};
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;timers.current.forEach(clearTimeout);timers.current.clear();};},[]);
 useEffect(()=>{if(phase==='lifting')schedule(()=>setPhase('expanded'),reduced?0:500);},[reduced]);
 useLayoutEffect(()=>{
  const phone=summary.current?.closest('.phone');
  const measure=()=>{
   const bounds=phone?.getBoundingClientRect(),scale=bounds&&phone.clientHeight?bounds.height/phone.clientHeight:1;
   const visible=window.visualViewport;
   const screenBottom=visible?visible.offsetTop+visible.height:window.innerHeight;
   const visibleHeight=bounds?Math.max(0,(Math.min(bounds.bottom,screenBottom)-bounds.top)/scale):800;
   setAvailableHeight(Math.max(compactHeight,Math.min(phone?.clientHeight||800,visibleHeight)-92));
  };
  const observer=new ResizeObserver(measure);if(phone)observer.observe(phone);measure();
  window.addEventListener('resize',measure);window.visualViewport?.addEventListener('resize',measure);window.visualViewport?.addEventListener('scroll',measure);
  return()=>{observer.disconnect();window.removeEventListener('resize',measure);window.visualViewport?.removeEventListener('resize',measure);window.visualViewport?.removeEventListener('scroll',measure);};
 },[]);
 useLayoutEffect(()=>{summary.current?.closest('.budget-entry-reveal')?.style.setProperty('--budget-reveal-height',height+'px');},[height]);
 async function finish(action=onClose){
  if(closing.current)return;
  timers.current.forEach(clearTimeout);timers.current.clear();
  closing.current=true;setPhase('closing');
  const perform=async()=>{
   try{const result=await action();if(result===false&&alive.current){closing.current=false;setPhase('expanded');}}
   catch{if(alive.current){closing.current=false;setPhase('expanded');}}
  };
  if(reduced)await perform();else schedule(perform,350);
 }
 useImperativeHandle(ref,()=>({finish}),[reduced,onClose]);
 const amount=parseMoney(entry?.amount||'0',entry?.currency||'CNY');
 return <FlyingPanel origin={origin} label={label} onClose={()=>finish()} flyHeight={height} className={className+' budget-entry-reveal is-'+phase}>
  <div ref={summary} className="budget-entry-reveal-summary" data-phase={phase}>
   <span className={'budget-category-icon category-'+(entry?.category||'shopping')}><Icon name={entryIcons[entry?.category]||'receipt'} size={18}/></span>
   <span className="budget-row-copy"><strong>{entry?.title||'新的一笔花费'}</strong><small>{entryLabels[entry?.category]||'其他'} · {entry?.date||'今天'} · {entry?.status==='planned'?'预计花费':'已支付'}</small></span>
   <span className="budget-row-money"><b>{amount===null?'待补齐':formatMoney(amount,entry?.currency||'CNY')}</b><small>{entry?.currency||'CNY'}</small></span>
  </div>
  <div className="budget-entry-detail-content" data-phase={phase} aria-label="账目详情" role="region" tabIndex={phase==='expanded'?0:-1} inert={phase==='expanded'?undefined:''} aria-hidden={phase==='expanded'?undefined:true}>{children}</div>
 </FlyingPanel>;
});
