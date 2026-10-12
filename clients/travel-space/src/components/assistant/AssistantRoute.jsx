import React,{useId} from 'react';
import GeographicMap from '../GeographicMap';
import {project,mapExtent,destinations} from '../mapRoute';
const located=day=>{const p=Object.hasOwn(day,'geo')?day.geo:destinations[day.id];return p&&Number.isFinite(p.lat)&&Number.isFinite(p.lon)&&p.lon>=mapExtent.west&&p.lon<=mapExtent.east&&p.lat>=mapExtent.south&&p.lat<=mapExtent.north?p:null;};
export default function AssistantRoute({days,values,onChange}){
 const unique=useId().replace(/:/g,''),from=days.find(d=>String(d.id)===String(values.fromId)),to=days.find(d=>String(d.id)===String(values.toId)),points=[from,to].filter(Boolean),valid=points.length===2&&points.every(located);
 return <div className="answer-route"><div className="answer-route-endpoints">{[['fromId','A · 出发'],['toId','B · 到达']].map(([key,label])=><label key={key}>{label}<select aria-label={label+'地点'} value={values[key]} onChange={e=>onChange(key,e.target.value)}>{days.map(d=><option value={d.id} key={d.id}>{d.place}</option>)}</select></label>)}</div>{valid?<figure aria-label={from.place+'到'+to.place+'游览连线'}><GeographicMap days={points.map((d,i)=>({...d,id:unique+'-'+i,geo:located(d)}))} focus={unique}>{points.map((d,i)=>{const p=project(located(d));return <span key={i} className="answer-map-pin" style={{left:p.x+'%',top:p.y+'%'}}>{i?'B':'A'}<small>{d.place}</small></span>;})}</GeographicMap><figcaption>A → B · 游览连线</figcaption></figure>:<p className="answer-missing">地点尚未标注，补齐坐标后即可展示连线。</p>}</div>;
}
