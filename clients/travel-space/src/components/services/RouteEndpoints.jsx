import FloatingField from '../FloatingField';
import React,{useState,useRef,useId,useEffect,useMemo} from 'react';
import {motion,useReducedMotion} from 'motion/react';
import {Icon} from '../UI';
import {catalog} from './planning';
import {airportGeo,validRouteGeo} from './route-model';
const normalizedName=name=>String(name||'').trim().toLocaleLowerCase().replace(/\s+/g,'');
export function resolveRouteLocation(name,points=[]){
 const query=normalizedName(name);if(!query)return null;
 return points.find(point=>validRouteGeo(point?.geo)&&[point.name,...(Array.isArray(point.aliases)?point.aliases:[])].some(alias=>normalizedName(alias)===query))||null;
}
export default function RouteEndpoints({day,days,from,to,fromName,toName,value={},onChange,resolvedLocations=[]}){
 const [editing,setEditing]=useState(null),[query,setQuery]=useState(''),[active,setActive]=useState(0),id=useId(),input=useRef(null),reduced=useReducedMotion();
 const resolvedKey=JSON.stringify(Array.isArray(resolvedLocations)?resolvedLocations:[]),dayKey=JSON.stringify(days.map(d=>[d.id,d.place,d.geo]));
 const points=useMemo(()=>[
  ...(Array.isArray(resolvedLocations)?resolvedLocations:[]).filter(p=>p&&typeof p.name==='string'&&validRouteGeo(p.geo)).map((p,i)=>({...p,id:p.id||'resolved-'+i})),
  ...days.filter(d=>validRouteGeo(d.geo)).map(d=>({id:'day-'+d.id,name:d.place+' · '+d.geo.anchor,aliases:[d.place,d.geo.anchor],geo:d.geo})),
  ...catalog.map(c=>({id:c.id,name:c.name,geo:c.geo}))
 ].filter((point,index,all)=>validRouteGeo(point.geo)&&all.findIndex(other=>normalizedName(other.name)===normalizedName(point.name))===index),[resolvedKey,dayKey]);
 const options=points.filter(p=>!query.trim()||p.name.includes(query.trim())).slice(0,5);
 const names={from:fromName,to:toName},geo={from,to},edge=editing||(!fromName?'from':!toName&&fromName?'to':null);
 const change=(key,patch)=>onChange({...value,[key]:{name:names[key],geo:geo[key],...value[key],...patch}});
 useEffect(()=>{
  let next=value,changed=false;
  for(const key of ['from','to']){
   if(!names[key]||validRouteGeo(geo[key]))continue;
   const point=resolveRouteLocation(names[key],points);
   if(point){next={...next,[key]:{...value[key],name:names[key],geo:point.geo,resolved:true}};changed=true;}
  }
  if(changed)onChange(next);
 },[resolvedKey,dayKey,fromName,toName,from?.lat,from?.lon,to?.lat,to?.lon]);
 const select=point=>{if(!edge)return;const key=edge;change(key,{id:point.id,name:point.name,geo:validRouteGeo(point.geo)?point.geo:null,resolved:validRouteGeo(point.geo)});setQuery('');setActive(0);setEditing(key==='from'&&!toName?'to':null);requestAnimationFrame(()=>{if(key==='from'&&!toName)input.current?.focus({preventScroll:true});});};
 const commit=()=>{if(!query.trim())return;select(resolveRouteLocation(query,points)||{id:'custom',name:query.trim().slice(0,60),geo:null});};
 const edit=key=>{setEditing(key);setQuery('');setActive(0);requestAnimationFrame(()=>input.current?.focus({preventScroll:true}));};
 return <div className="route-endpoints sequential-endpoints" role="group" aria-label="交通起点与终点"><div className="location-sequence">{['from','to'].map(key=><React.Fragment key={key}>{key==='to'&&fromName&&<motion.span className="location-arrow" aria-hidden="true" initial={reduced?false:{opacity:0,x:-6}} animate={{opacity:1,x:0}} transition={{duration:reduced?0:.35}}>→</motion.span>}{names[key]&&edge!==key?<motion.button type="button" className="location-pill" aria-label={'修改交通'+(key==='from'?'起点':'终点')+'：'+names[key]} initial={reduced?false:{opacity:0,scale:.9}} animate={{opacity:1,scale:1}} onClick={()=>edit(key)}><Icon name="pin" size={13}/><span>{names[key]}</span></motion.button>:key===edge?<div className="location-input-wrap"><FloatingField ref={input} role="combobox" autoComplete="off" aria-label={key==='from'?'输入交通起点':'输入交通终点'} aria-autocomplete="list" aria-expanded={options.length>0} aria-controls={id+'-options'} aria-activedescendant={options.length?id+'-option-'+Math.min(active,options.length-1):undefined} placeholder={key==='from'?'输入起点…':'输入终点…'} value={query} onChange={e=>{setQuery(e.target.value);setActive(0);}} onKeyDown={e=>{if(e.nativeEvent.isComposing)return;if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();setActive(n=>(n+(e.key==='ArrowDown'?1:-1)+options.length)%Math.max(options.length,1));}if(e.key==='Enter'){e.preventDefault();if(options.length&&query.trim())select(options[active]||options[0]);else commit();}if(e.key==='Escape'){e.stopPropagation();setEditing(null);setQuery('');}}}/><button type="button" className="location-commit" disabled={!query.trim()} aria-label={'确认交通'+(key==='from'?'起点':'终点')} onClick={commit}><Icon name="check" size={13}/></button></div>:null}</React.Fragment>)}</div>
 {edge&&options.length>0&&<div className="location-suggestions" role="listbox" aria-label="地点建议" id={id+'-options'}>{options.map((p,i)=><button id={id+'-option-'+i} role="option" aria-selected={active===i} key={p.id} type="button" onMouseDown={e=>e.preventDefault()} onClick={()=>select(p)}><span className="location-initial" aria-hidden="true">{p.name.slice(0,1)}</span>{p.name}</button>)}</div>}
 {['from','to'].filter(key=>names[key]&&!validRouteGeo(geo[key])).map(key=><p key={key} className="location-query-pending" role="status"><Icon name="pin" size={12}/>{names[key]} · 地点待查询</p>)}
 </div>;
}
