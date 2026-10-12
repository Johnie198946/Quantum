import React from 'react';
import {useTravel} from '../../TravelContext';
import {Icon} from '../UI';
import {normalizePlan,reservations,recordState} from './planning';
export default function ServiceDaySummary({day,compact=false}){
 const {profile,days,openServices}=useTravel(),plan=normalizePlan(profile.servicePlan),rows=reservations(plan).filter(r=>r.dayId===day.id).sort((a,b)=>(a.time||'23:59').localeCompare(b.time||'23:59'));
 if(!rows.length)return null;
 return <section className={'service-day-summary'+(compact?' compact':'')}><h2>这一天的预订与衔接</h2>{rows.map(r=><button key={r.kind+r.key} onClick={()=>openServices(r.kind,day.id)}><time>{r.time||'入住'}</time><span><strong>{r.name}</strong><small>{recordState(r,day,days,plan)}</small></span><Icon name="chevron" size={12}/></button>)}</section>;
}
