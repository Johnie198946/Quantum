import React,{useCallback,useId,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {AnimatePresence,useReducedMotion} from 'motion/react';
import GeographicMap from '../GeographicMap';
import {Icon,Sheet} from '../UI';
import {dayNumber,destinations,mapExtent} from '../mapRoute';
import './JournalRouteMap.css';

function mapCoordinate(day){
 // An explicit null means the location is unknown. Only an omitted field is
 // eligible for the existing itinerary's verified legacy anchor.
 const coordinate=Object.prototype.hasOwnProperty.call(day,'geo')?day.geo:destinations[day.id];
 if(!coordinate||typeof coordinate.lat!=='number'||typeof coordinate.lon!=='number'||!Number.isFinite(coordinate.lat)||!Number.isFinite(coordinate.lon))return null;
 const {lat,lon}=coordinate;
 if(lat<-90||lat>90||lon<-180||lon>180||lat<mapExtent.south||lat>mapExtent.north||lon<mapExtent.west||lon>mapExtent.east)return null;
 return coordinate;
}
function dayLabel(number){return 'DAY '+String(number).padStart(2,'0');}
function sameDay(left,right){return left!==undefined&&right!==undefined&&String(left)===String(right);}
function routeRows(days){
 return days.filter(day=>day&&typeof day==='object').map((day,index)=>{
  const number=Number(dayNumber(day));
  return {day,index,number:Number.isFinite(number)&&number>0?number:index+1,coordinate:mapCoordinate(day),place:String(day.place||'地点未命名'),date:String(day.date||'日期未定')};
 });
}

function RegionMap({rows,current,scope,expanded=false,reduced}){
 const points=rows.filter(row=>row.coordinate).map(row=>({...row.day,id:scope+'-'+row.index,order:row.number,geo:row.coordinate}));
 const focusRow=rows.find(row=>sameDay(row.day.id,current?.day.id));
 const focus=focusRow?.coordinate?scope+'-'+focusRow.index:scope+'-unmarked';
 return <div className={'journal-route-map-canvas'+(expanded?' journal-route-map-expanded':'')} data-current-day={current?.day.id} data-valid-points={points.length} data-missing-points={rows.length-points.length}>
  {points.length?<GeographicMap days={points} focus={focus} animated={expanded&&!reduced}/>:<div className="journal-route-map-empty" role="status"><Icon name="pin" size={23}/><p>这些日子的地点，还没有标注。</p><span>补充有效位置后，会在这里串起游览顺序。</span></div>}
 </div>;
}

export default function JournalRouteMap({day,days,onSelectDay}){
 const id=useId(),scope='journal-map-'+id.replace(/[^a-zA-Z0-9_-]/g,''),headingId=scope+'-heading',root=useRef(null),reduced=useReducedMotion();
 const [expanded,setExpanded]=useState(false),[host,setHost]=useState(null),close=useCallback(()=>setExpanded(false),[]);
 const rows=useMemo(()=>routeRows(Array.isArray(days)&&days.length?days:day?[day]:[]),[days,day]);
 const current=rows.find(row=>sameDay(row.day.id,day?.id))||routeRows(day?[day]:[])[0],valid=rows.filter(row=>row.coordinate).length,missing=rows.length-valid;
 useLayoutEffect(()=>{setHost(root.current?.closest('.notebook-screen')||root.current?.closest('.phone')||null);},[]);
 const choose=row=>{if(row.day.id!==undefined&&row.day.id!==null)onSelectDay?.(row.day.id);};
 const currentLine=current?<><strong>{dayLabel(current.number)} · {current.place}</strong><span>{current.date}</span></>:<strong>旅行地点</strong>;
 const explanation=valid?'区域地点的游览顺序；连线不代表道路或导航。':'已有日记会保留，暂不显示未核实的位置。';

 return <section className="journal-route-map" ref={root} aria-labelledby={headingId}>
  <header className="journal-route-map-heading"><div><p className="journal-kicker">THE JOURNEY / ON THE MAP</p><h2 id={headingId}>这一天，在地图上。</h2></div><button type="button" className="journal-route-map-open" aria-label="展开旅行日记地图" aria-haspopup="dialog" aria-expanded={expanded} onClick={()=>setExpanded(true)}><Icon name="expand" size={17}/></button></header>
  <figure className="journal-route-map-figure" aria-label="旅行日记地点地图">
   <RegionMap rows={rows} current={current} scope={scope+'-preview'} reduced={reduced}/>
   <figcaption><div className="journal-route-map-current" aria-live="polite">{currentLine}</div><p className="journal-route-map-explanation">{explanation}</p></figcaption>
  </figure>
  {current&&!current.coordinate&&<p className="journal-route-map-missing" role="status">{dayLabel(current.number)} · {current.place}的位置未标注。</p>}
  {missing>0&&valid>0&&<p className="journal-route-map-coverage">{valid} 天已标注 · {missing} 天位置未标注，未参与连线</p>}
  <div className="journal-route-map-days" role="group" aria-label="地图切换日记日期">{rows.map(row=><button type="button" key={String(row.day.id)+'-'+row.index} className={'journal-route-map-day'+(sameDay(row.day.id,current?.day.id)?' is-current':'')} data-day-id={row.day.id} data-located={row.coordinate?'true':'false'} aria-label={'地图切换到'+dayLabel(row.number)+' '+row.place} aria-pressed={sameDay(row.day.id,current?.day.id)} disabled={!onSelectDay||row.day.id===undefined||row.day.id===null} onClick={()=>choose(row)}><small>{dayLabel(row.number)}</small><span>{row.place}</span></button>)}</div>
  {host&&createPortal(<AnimatePresence>{expanded&&<Sheet key="journal-route-map" label="旅行日记地图" onClose={close} className="journal-route-map-sheet">
   <header className="journal-route-map-sheet-heading"><p className="journal-kicker">THE WHOLE JOURNEY</p><h2>沿途，在地图上。</h2><div className="journal-route-map-current" aria-live="polite">{currentLine}</div></header>
   <figure className="journal-route-map-sheet-figure" aria-label="展开的旅行日记地点地图"><RegionMap rows={rows} current={current} scope={scope+'-expanded'} expanded reduced={reduced}/><figcaption>{explanation}</figcaption></figure>
   {current&&!current.coordinate&&<p className="journal-route-map-missing" role="status">{dayLabel(current.number)} · {current.place}的位置未标注；仍可阅读这一天的日记。</p>}
   <ol className="journal-route-map-list" aria-label="整趟旅程日记日期">{rows.map(row=><li key={String(row.day.id)+'-'+row.index}><button type="button" className={sameDay(row.day.id,current?.day.id)?'is-current':''} data-day-id={row.day.id} data-located={row.coordinate?'true':'false'} aria-label={'地图查看'+dayLabel(row.number)+' '+row.place} aria-pressed={sameDay(row.day.id,current?.day.id)} disabled={!onSelectDay||row.day.id===undefined||row.day.id===null} onClick={()=>choose(row)}><span className="journal-route-map-number">{String(row.number).padStart(2,'0')}</span><span className="journal-route-map-copy"><strong>{row.place}</strong><small>{row.date}{!row.coordinate?' · 位置未标注':typeof row.coordinate.anchor==='string'&&row.coordinate.anchor?' · '+row.coordinate.anchor:''}</small></span><Icon name={sameDay(row.day.id,current?.day.id)?'check':'chevron'} size={16}/></button></li>)}</ol>
  </Sheet>}</AnimatePresence>,host)}
 </section>;
}
