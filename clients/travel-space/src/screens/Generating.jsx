import React from 'react';
import {useTravel} from '../TravelContext';
import {TopBar,Primary} from '../components/UI';
import TravelThinkingOrb from '../components/TravelThinkingOrb';
import {useRuntime} from '../production/RuntimePanel';
import {runtime} from '../production/runtime';
import {statusLabel} from '../production/TaskPages';
export default function Generating(){
 const {setStage}=useTravel(),live=useRuntime(),s=live.snapshot,ready=!!s?.artifact,stopped=['failed','cancelled'].includes(s?.execution?.status);
 return <section className="generating-screen thinking-generation"><div className="travel-sunlight" aria-hidden="true"><i/><i/><i/></div><TopBar title="" onBack={()=>setStage('route')}/><header className="generation-heading"><p className="eyebrow">让旅程慢慢成形</p><h1>{stopped?'旅程暂时停在这里，':ready?'属于你的风景，':'正在拼好'}<br/>{stopped?'已完成的部分会保留。':ready?'已整理成稿。':'这段旅程。'}</h1><p>{stopped?s.execution.errorMessage||'查看当前记录，再决定下一步。':ready?'查看来源与安排，再采用这份行程。':'正在等待服务端生成结果。'}</p></header>{!stopped&&<div className="thinking-generation-button"><TravelThinkingOrb/></div>}<div className="thinking-generation-copy">{ready?<Primary onClick={()=>setStage('adopt',{fromOrb:true})}>查看成稿</Primary>:stopped?<Primary onClick={()=>runtime.publish({taskDetails:true})}>查看任务与已完成内容</Primary>:<><strong>{s?.execution?.progress||0}<small>%</small></strong><p role="status">{s?.execution?statusLabel(s.execution.status):'等待服务端'}</p></>}</div></section>;
}
