import React,{useState,useRef,useCallback} from 'react';
import {createPortal} from 'react-dom';
import {motion,useMotionValue,useSpring,useReducedMotion} from 'motion/react';
import {Sheet,Icon} from '../UI';
import {formatPrice} from './price-currency';
import {money,dateText} from './flight-data';
export default function TearTicket({ticket,container,onClose,onSelect,selected,currency}){
 const [expanded,setExpanded]=useState(false),raw=useMotionValue(0),height=useSpring(raw,{stiffness:360,damping:32}),session=useRef(null),suppressUntil=useRef(0),reduced=useReducedMotion(),limit=ticket.kind==='flight'?232:204;
 const toggle=()=>{const next=!expanded;setExpanded(next);if(reduced)height.jump(next?limit:0);raw.set(next?limit:0);};
 const flight=ticket.kind==='flight',close=useCallback(onClose,[onClose]);
 return createPortal(<Sheet label={flight?'航班票据':'接驳票据'} className="tear-ticket-sheet" onClose={close}>
 <div className="tear-summary"><p className="ticket-kicker">{ticket.caption||(flight?'FLIGHT / '+dateText(ticket.date):'TRANSFER / '+dateText(ticket.date))}</p><h2>{ticket.from}<span>→</span>{ticket.to}</h2><div className="tear-summary-values"><strong>{ticket.time}<span> → {ticket.arrival}</span></strong><strong>{currency?formatPrice(ticket.price,currency,ticket.priceCurrency||'CNY'):money(ticket.price)}<small>{ticket.priceUnit||'/人'}</small></strong></div></div>
 <motion.div className="tear-reveal" style={{height:reduced?(expanded?limit:0):height}} aria-hidden={!expanded} inert={!expanded?'':undefined}><div className="tear-details">
 {flight?<><div><span>航班</span><strong>{ticket.carrier}<br/>{ticket.flightNumber}</strong></div><div><span>行程</span><strong>{ticket.connection} · {ticket.duration}分钟</strong></div><div><span>到达</span><strong>{ticket.arrivalDate} · {ticket.arrival}<br/>当地 UTC+{ticket.destinationOffset}</strong></div><div><span>票价内容</span><strong>{ticket.seat} · {ticket.baggage}</strong></div><p>公开资料中的班次与票价，出发前核对{ticket.pet?' · 携宠需渠道确认':''}</p></>:<><p>{ticket.line} · {ticket.caption?'含缓冲的估时':'落地后 '+ticket.offset+'分钟'}</p><ol className="ticket-stations">{ticket.stops.map((station,i)=><li key={i}><i/><span>{station}</span>{i===0&&<time>{ticket.time}</time>}{i===ticket.stops.length-1&&<time>{ticket.arrival}</time>}</li>)}</ol><p>来源班次 · {ticket.duration}分钟 · {ticket.arrivalDate}</p></>}
 </div></motion.div>
 <button type="button" className="tear-pull" aria-expanded={expanded} aria-label={expanded?'收起票据详情':'展开票据详情'} onClick={e=>{if(performance.now()<suppressUntil.current){e.preventDefault();return;}toggle();}} onPointerDown={e=>{if(e.button!==0)return;session.current={id:e.pointerId,y:e.clientY,start:raw.get(),moved:false};e.currentTarget.setPointerCapture(e.pointerId);}} onPointerMove={e=>{const s=session.current;if(!s||s.id!==e.pointerId)return;const dy=e.clientY-s.y;if(Math.abs(dy)>4)s.moved=true;if(s.moved){const next=Math.max(0,Math.min(limit,s.start+dy));raw.set(next);setExpanded(next>35);}}} onPointerUp={e=>{const s=session.current;if(!s||s.id!==e.pointerId)return;const next=raw.get()>limit*.28;raw.set(next?limit:0);setExpanded(next);if(s.moved)suppressUntil.current=performance.now()+300;session.current=null;}} onPointerCancel={()=>{raw.set(expanded?limit:0);session.current=null;}}><span>{expanded?'向上收起':'向下拉开票据'}</span><Icon name={expanded?'arrow':'down'} size={15}/></button>
 <button type="button" className="ticket-select" aria-label={ticket.action||(flight?'采用这班航班':'采用这班接驳')} aria-pressed={selected} onClick={()=>{onSelect(ticket);onClose();}}><span>{selected?'已选择':ticket.action||'选择这班'+(flight?'航班':'接驳')}</span><Icon name="check" size={16}/></button>
 </Sheet>,container||document.body);
}
