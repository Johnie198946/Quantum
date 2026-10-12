import ServiceSearch from '../../production/ServiceSearch';
import {serviceCache} from '../../production/service-provider';
import {useRuntime} from '../../production/RuntimePanel';
import React,{useId,useRef,useState} from 'react';
import {useTravel} from '../../TravelContext';
import {motion,useReducedMotion} from 'motion/react';

function WeatherIcon({cloud=false}){return <svg aria-hidden="true" width="23" height="23" viewBox="0 0 24 24" fill="none" stroke={cloud?'#faf7f0':'#f6cd76'} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{cloud?<path d="M6.2 18h11.2a4.2 4.2 0 0 0 .1-8.4 5.9 5.9 0 0 0-11.3-1.1A4.8 4.8 0 0 0 6.2 18Z"/>:<><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.4 1.4m11.2 11.2L19 19M5 19l1.4-1.4M17.6 6.4 19 5"/></>}</svg>;}
const HEIGHT=142;
export default function JournalWeather({day}){
 useRuntime();
 const {profile}=useTravel(),recorded=serviceCache.weather[day.id]||profile.assistantWeather?.[day.id];
 const reduced=useReducedMotion(),id=useId(),gesture=useRef(null),suppress=useRef(false),[height,setHeight]=useState(0),[dragging,setDragging]=useState(false);
 const expanded=height>=HEIGHT/2;
 const start=e=>{if(e.button!==0||!e.isPrimary)return;gesture.current={id:e.pointerId,y:e.clientY,height};suppress.current=false;e.currentTarget.setPointerCapture(e.pointerId);setDragging(true);};
 const move=e=>{const g=gesture.current;if(!g||g.id!==e.pointerId)return;const delta=e.clientY-g.y;if(Math.abs(delta)>4)suppress.current=true;setHeight(Math.max(0,Math.min(HEIGHT,g.height+delta)));};
 const end=e=>{const g=gesture.current;if(!g||g.id!==e.pointerId)return;const delta=e.clientY-g.y;setHeight(e.type==='pointercancel'?g.height:Math.abs(delta)>24?(delta>0?HEIGHT:0):height>=HEIGHT/2?HEIGHT:0);gesture.current=null;if(e.type==='pointercancel')suppress.current=false;setDragging(false);};
 const toggle=e=>{if(e.detail!==0&&suppress.current){suppress.current=false;return;}setHeight(expanded?0:HEIGHT);};
 const handlers={onPointerDown:start,onPointerMove:move,onPointerUp:end,onPointerCancel:end,onLostPointerCapture:e=>{if(gesture.current){setHeight(gesture.current.height);gesture.current=null;setDragging(false);}}};
 return <section className="journal-weather" aria-label={day.place+(recorded?'已确认天气':'天气待查询')}>
  <button type="button" className="weather-summary" aria-label={expanded?'收起逐小时天气':'展开逐小时天气'} aria-expanded={expanded} aria-controls={id} onClick={toggle} {...handlers}><span className="weather-now"><WeatherIcon/><strong>{recorded?.temperature??'—'}°</strong><span>{recorded?.condition||'天气待确认'}</span></span><span className="weather-range">{recorded?<>自己核对<br/>当天气温</>:<>天气信息<br/>尚未核对</>}</span></button>
  <motion.div id={id} className="weather-hourly-reveal" initial={false} animate={{height}} transition={dragging||reduced?{duration:0}:{type:'spring',stiffness:340,damping:32}} aria-hidden={height===0}>
   <ol className="weather-hours" aria-label="逐小时预报">{(recorded?.hours||[]).map((hour,i)=><li key={i}><time>{hour.time}</time><WeatherIcon cloud={hour.condition!=='晴'}/><strong>{hour.temperature}°</strong></li>)}</ol>
   <ServiceSearch kind="weather" query={{dayId:day.id,place:day.place,date:day.date}}/>
   <button type="button" className="weather-grip" tabIndex={height===0?-1:0} aria-label="上滑收起天气" onClick={()=>setHeight(0)} {...handlers}><span/></button>
  </motion.div>
  <small className="weather-demo">{recorded?.sourceUrl?<a href={recorded.sourceUrl} target="_blank" rel="noreferrer">天气来源 · {recorded.checked_at}</a>:recorded?'用户确认天气':'下拉查询天气'}</small>
 </section>;
}
