import React,{useState} from 'react';
import {useTravel} from '../TravelContext';
import {searchServices} from './service-provider';
import {runtime} from './runtime';
import {Icon} from '../components/UI';
export default function ServiceSearch({kind,query,onResult}){
 const {setProfile}=useTravel();
 const [busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const search=async()=>{if(busy)return;setBusy(true);setMessage('正在查找资料…');const generation=runtime.generation;const isCurrent=()=>runtime.generation===generation;try{const rows=await searchServices(kind,query,isCurrent);setMessage(rows.length?'已找到 '+rows.length+' 项带来源的资料':'暂时没有查到可核验的资料。');setProfile(previous=>({...previous,serviceResults:{...previous.serviceResults,...(kind==='weather'?{weatherByDay:{...previous.serviceResults?.weatherByDay,[query.dayId]:rows[0]||null}}:{[kind]:rows})}}));onResult?.(rows);runtime.publish({serviceRevision:(runtime.state.serviceRevision||0)+1});}catch(e){setMessage(e.message);}finally{setBusy(false);}};
 return <div className="production-service-query"><button type="button" className="glass" disabled={busy} onClick={search}><Icon name="search" size={16}/>{busy?'查询中…':'查询最新资料'}</button><small role="status">{message||'查询结果供选择；预订以实际订单为准。'}</small></div>;
}
