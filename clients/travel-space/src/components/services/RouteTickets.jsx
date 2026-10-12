import React,{useId} from 'react';
import {AnimatePresence,motion,useReducedMotion} from 'motion/react';
import {Icon} from '../UI';
import {displayServicePrice} from '../../production/service-provider';
import InterestStatus from '../InterestStatus';
import {minutes,clock,isoAdd} from './planning';
export function routeTicket({route,fromName,toName,date,time,mode,buffer=0,offset=0}){
 const departure=minutes(time)+offset,duration=route.duration+buffer,total=departure+duration;
 return {id:mode+'-'+date+'-'+time+'-'+offset,kind:'transfer',mode,from:fromName,to:toName,date:isoAdd(date,Math.floor(departure/1440)),time:clock(departure%1440),windowTime:time,arrival:clock(total%1440),arrivalDate:isoAdd(date,Math.floor(total/1440)),price:route.price,priceCurrency:route.priceCurrency,duration,offset,priceUnit:['出租车','自驾'].includes(mode)?'／车':'／人',line:route.line,stops:route.stops.map(s=>s.name),source:route.source||'待确认'};
}
export default function RouteTickets({route,fromName,toName,date,time,mode,buffer,onSelect,selected}){
 const id=useId(),reduced=useReducedMotion();
 if(!route||!Number.isFinite(minutes(time)))return null;
 const windowTime=selected?.mode===mode&&selected?.time===time?selected.windowTime||time:time;
 const publicMode=['公交车','火车','渡轮','接驳船'].includes(mode),offsets=[0];
 return <section className="route-ticket-search route-ticket-choice" aria-label="交通票据"><header><small>YOUR CONNECTION</small><h3>{publicMode?'选一班，衔接下一站。':'选一份，沿途更从容。'}</h3></header><div className="route-ticket-options">{offsets.map(offset=>{
  const t=routeTicket({route,fromName,toName,date,time:windowTime,mode,buffer,offset}),active=selected?.id===t.id,panel=id+'-'+offset;
  return <motion.article layout key={t.id} className={'glass route-ticket-card'+(active?' is-selected':'')} data-pending-key={'route-ticket-'+t.id} transition={reduced?{duration:0}:{type:'spring',stiffness:330,damping:30}}>
   <div className="route-ticket-card-heading"><button type="button" aria-label={'选择'+t.time+'出发的'+mode+'票据'} aria-pressed={active} aria-expanded={active} aria-controls={active?panel:undefined} onClick={()=>onSelect(t)}><span><strong>{t.time} <span>→ {t.arrival}</span></strong><small>{mode} · {t.duration} 分钟</small></span><span className="route-ticket-price">{displayServicePrice(t.price,t.priceCurrency)}</span></button><InterestStatus choice={t.time+'出发的'+mode+'票据'} active={active} onClick={()=>onSelect(active?null:t)}/></div>
   <AnimatePresence initial={false}>{active&&<motion.div id={panel} className="route-ticket-card-details" initial={reduced?false:{opacity:0,height:0}} animate={{opacity:1,height:'auto'}} exit={{opacity:0,height:0}} transition={{duration:reduced?0:.22}}><p>{fromName}<Icon name="chevron" size={12}/>{toName}</p><ol>{t.stops.map((station,i)=><li key={i}><span className="route-ticket-station-dot"/><span>{station}</span>{i===0&&<time>{t.time}</time>}{i===t.stops.length-1&&<time>{t.arrival}</time>}</li>)}</ol><footer><span>{t.priceUnit} · 含 {buffer} 分钟衔接时间</span><span><Icon name="check" size={12}/>已选择</span></footer></motion.div>}</AnimatePresence>
  </motion.article>;
 })}</div></section>;
}
