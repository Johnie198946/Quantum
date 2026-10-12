import React,{useSyncExternalStore,useState,useEffect} from 'react';
import {runtime} from './runtime';
import {Icon,Primary,Sheet} from '../components/UI';
import {errorMessage} from './bridge';
import TravelThinkingOrb from '../components/TravelThinkingOrb';
import {TaskLibrary,TaskDetails,readableBrief,statusLabel} from './TaskPages';
import {useTravel} from '../TravelContext';

export const useRuntime=()=>useSyncExternalStore(runtime.subscribe,()=>runtime.state);
export default function RuntimePanel(){
  const {enterTransport,days}=useTravel();
  const live=useRuntime(),{snapshot:s,error,busy,recoveryAvailable,panelDismissed,taskLibrary,taskDetails}=live,[response,setResponse]=useState(''),[working,setWorking]=useState(false),[localError,setLocalError]=useState('');
  const act=async action=>{if(working)return;setWorking(true);setLocalError('');try{await action();}catch(e){setLocalError(errorMessage(e));}finally{setWorking(false);}};
  const session=s?.clarification?.session, question=[...(s?.clarification?.events||[])].reverse().find(e=>e.payload?.question)?.payload;
  const planningFailure=[...(s?.clarification?.events||[])].reverse().find(e=>['planning_failed','clarification_unavailable'].includes(e.type));
  useEffect(()=>setResponse(''),[s?.workflow.id,session?.phase,session?.roundNumber]);
  const unfinished=!panelDismissed&&!taskLibrary&&!taskDetails&&s&&s.workflow.uiKind!=='archive'&&!s.artifact&&!['completed','cancelled'].includes(s.execution?.status||s.workflow.status);
  return <>{(error||localError||recoveryAvailable)&&<div className="production-error" role="alert"><span>{localError||error||'未同步草稿已保留'}</span>{recoveryAvailable&&<button className="production-recovery" onClick={()=>act(()=>runtime.call('export',{filename:'travel-journal.json',content:JSON.stringify(runtime.recoveryDraft)}))}>导出草稿</button>}<button aria-label="重新读取任务" onClick={()=>act(()=>runtime.refresh())}><Icon name="replay"/></button><button aria-label="关闭提示" onClick={()=>{setLocalError('');runtime.publish({error:'',recoveryAvailable:false});}}><Icon name="close"/></button></div>}
    {unfinished&&<Sheet label={s.workflow.uiKind==='photo'?'照片处理进度':'核对旅行计划'} className="production-task-panel" onClose={()=>runtime.publish({panelDismissed:true})}>
      <p className="eyebrow">YOUR JOURNEY, TAKING SHAPE</p><h2>{s.workflow.title}</h2>
      {s.workflow.uiKind==='photo'?<><p>{s.workflow.description}</p>{s.workflow.status==='awaiting_approval'&&!s.execution&&s.plan?<Primary disabled={working} onClick={()=>act(()=>runtime.approvePlan())}>确认照片处理方案</Primary>:s.workflow.status==='agent_ready'&&!s.execution?<Primary disabled={working} onClick={()=>act(()=>runtime.start())}>开始照片处理</Primary>:<Primary onClick={()=>act(()=>runtime.call('openNative'))}>查看照片处理进度</Primary>}</>:s.execution?<>{['queued','running'].includes(s.execution.status)&&<TravelThinkingOrb/>}<p role="status">{s.execution.status==='failed'?s.execution.errorMessage||'生成未完成':s.execution.status==='awaiting_approval'?'成稿已准备好，请查看后确认。':statusLabel(s.execution.status)}</p>
        <progress value={s.execution.progress} max="100" aria-label="服务端执行进度"/><p>{s.execution.progress}%</p>
        <ol className="task-timeline">{s.execution.nodes?.map(n=><li key={n.id||n.nodeId} data-status={n.status}><span className="task-dot"/><div><strong>{n.name}</strong><small>{statusLabel(n.status)}</small></div></li>)}</ol>
        {['awaiting_approval','awaiting_review','failed'].includes(s.execution.status)&&<Primary onClick={()=>act(()=>runtime.call('openNative'))}>查看任务详情</Primary>}</>
      :s.workflow.status==='awaiting_approval'&&s.plan?<><p className="task-brief">{readableBrief(s.plan.goal)}</p><p>{s.plan.deliverable}</p>
        <ol>{s.plan.dsl?.nodes?.map(n=><li key={n.id||n.nodeId}>{n.name||n.title||n.id}</li>)}</ol>
        <p>预计 {s.plan.estimatedTokens} tokens · {s.plan.allowNetwork?'会检索公开资料':'不访问网络'}</p>
        {!!s.plan.validationErrors?.length&&<p className="task-failure">{s.plan.validationErrors.join('；')}</p>}<Primary disabled={working||!!s.plan.validationErrors?.length} onClick={()=>act(async()=>{await runtime.approvePlan();if(runtime.state.snapshot?.workflow.status==='agent_ready'&&days.length)enterTransport();})}>确认旅行计划</Primary></>
      :s.workflow.status==='agent_ready'?<><p>旅行计划已确认，先核对交通与预订，再开始制作。</p><Primary disabled={working||!days.length} onClick={enterTransport}>进入交通与预订</Primary></>
      :['clarifying','awaiting_requirement_confirmation'].includes(session?.phase)?<form onSubmit={e=>{e.preventDefault();act(()=>runtime.respond(response));}}><p>{question?.question||s.clarification.messages?.at(-1)?.content||'再补充一点旅行想法。'}</p>
        {question?.choices?.map(choice=><button className="glass" type="button" key={choice} onClick={()=>setResponse(choice)}>{choice}</button>)}
        <textarea aria-label="回答旅行澄清问题" value={response} onChange={e=>setResponse(e.target.value)} maxLength={6000}/><Primary disabled={working||!response.trim()} type="submit">{session.phase==='awaiting_requirement_confirmation'?'确认旅行需求':'确认回答'}</Primary></form>
      :s.workflow.status==='needs_attention'?<><p className="task-failure">{planningFailure?.payload?.detail||s.clarification?.messages?.at(-1)?.content||planningFailure?.message||'计划暂未完成，已有需求会保留。'}</p><Primary disabled={working} onClick={()=>act(()=>runtime.retry())}>重新整理计划</Primary></>
      :<><TravelThinkingOrb/><p role="status">{busy?'正在创建旅行任务…':'正在等待旅行规划结果…'}</p></>}
      <button className="text-btn" onClick={()=>act(()=>runtime.call('openNative'))}>完整任务与执行记录<Icon name="chevron"/></button>
    </Sheet>}
    {taskLibrary&&<TaskLibrary live={live} act={act} working={working}/>}
    {taskDetails&&s&&<TaskDetails snapshot={s} act={act} working={working}/>}
  </>;
}
