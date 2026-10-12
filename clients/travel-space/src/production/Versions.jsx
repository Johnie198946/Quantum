import React,{useEffect,useState} from 'react';
import {runtime} from './runtime';
import {Primary} from '../components/UI';
export default function Versions(){
 const [rows,setRows]=useState([]),[old,setOld]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 const executionId=runtime.state.snapshot?.execution?.id;
 useEffect(()=>{let live=true;runtime.call('versions',{executionId}).then(value=>{if(live)setRows(value.sort((a,b)=>(b.metadata.travelRevision||0)-(a.metadata.travelRevision||0)));}).catch(e=>{if(live)setError(e.message);}).finally(()=>{if(live)setLoading(false);});return()=>{live=false;};},[executionId]);
 const open=async row=>{try{const value=await runtime.call('version',{executionId,artifactId:row.id,hash:row.contentHash});setOld(JSON.parse(value.content));}catch(e){setError(e.message);}};
 return <><h2>{old?'过去的安排':'旧版本'}</h2>{loading&&<p role="status">正在读取已保存的版本…</p>}{error&&<p role="alert">{error}</p>}{old?<><p>保留的旧稿 · 仅供查看</p><h3>{old.destination}</h3><ol>{old.actions?.map(a=><li key={a.id}>{a.start?.slice(11,16)||'时间未定'} · {a.title}</li>)}</ol><Primary onClick={()=>setOld(null)}>返回版本列表</Primary></>:rows.map(row=><button className="menu-row" key={row.id} onClick={()=>open(row)}><span>{row.metadata.changeReason||row.title}<small>{row.metadata.changedAt||row.createdAt||'原始版本'}</small></span><span>查看</span></button>)}</>;
}
