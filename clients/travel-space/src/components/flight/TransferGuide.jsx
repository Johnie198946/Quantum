import React from 'react';
import {Icon} from '../UI';
import {serviceCache} from '../../production/service-provider';
export default function TransferGuide({mode,onPlan}){
 const route=serviceCache.routes.find(r=>r.mode===mode);
 return <article className="airport-transfer-guide glass"><header><div className="guide-icon"><Icon name="car" size={20}/></div><div><p>YOUR AIRPORT CONNECTION</p><h2>{mode} · 到达后的第一段</h2></div></header>{route?<><ol className="guide-steps">{route.stops.map((step,i)=><li key={i}><span>{i+1}</span><div><strong>{step.name}</strong><p>{step.instruction}</p></div></li>)}</ol><a href={route.sourceUrl} target="_blank" rel="noreferrer">查看查询来源</a><p>资料查询：{route.checked_at}</p></>:<p>先确认实际落地机场、时间与目的地，再查询接驳资料。</p>}{onPlan&&<button className="guide-plan" onClick={onPlan}>规划这一段<Icon name="chevron"/></button>}</article>;
}
