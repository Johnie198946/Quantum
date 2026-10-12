import React,{useEffect,useState} from 'react';
import {Icon,Primary,Sheet} from '../components/UI';
import {runtime} from './runtime';
import {useTravel} from '../TravelContext';

const labels={clarifying:'需求澄清中',awaiting_requirement_confirmation:'待确认需求',planning:'正在整理计划',needs_attention:'需要处理',building_agent:'正在准备',agent_ready:'待开始',ready:'已就绪',queued:'排队中',running:'正在制作',awaiting_approval:'待确认成稿',awaiting_review:'待采用成果',completed:'已完成',succeeded:'已完成',failed:'需要重试',cancelled:'已取消',pending:'等待中',skipped:'已跳过'};
export const statusLabel=status=>labels[status]||'正在读取状态';

// Earlier clients embedded requirement JSON in the description. Display its
// human-readable fields without changing the authoritative server plan/hash.
export function readableBrief(value=''){
  return [...new Set(value.split('\n').flatMap(line=>{
    try{const r=JSON.parse(line);if(!r||Array.isArray(r)||typeof r!=='object')return [line];
      const names={origin:'出发城市',date:'出发日期',duration:'游玩天数',count:'同行人数',budget:'预算',pace:'节奏',transport:'当地交通'};
      return [...Object.entries(names).filter(([k])=>r[k]&&r[k]!=='未定').map(([k,n])=>`${n}：${r[k]}`),...(r.interests?.length?[`兴趣：${r.interests.join('、')}`]:[]),...(r.notes||[])];
    }catch{return [line];}
  }).filter(Boolean))].join('\n');
}

export function TaskLibrary({live,act,working}){
  const [query,setQuery]=useState(''),[archive,setArchive]=useState(false);
  const tasks=live.workflows.filter(w=>archive?w.uiKind==='archive':w.uiKind!=='archive').filter(w=>w.title.toLowerCase().includes(query.trim().toLowerCase()));
  return <Sheet label="全部任务" className="task-library" onClose={()=>runtime.publish({taskLibrary:false})}>
    <p className="eyebrow">YOUR IDEAS, KEPT</p><h2>每一个想法，<br/>都有自己的下一步。</h2>
    <p className="task-caption">{archive?'旧任务保留为历史记录。':'当前对话里的旅行与照片。'}</p>
    <button className="text-btn" onClick={()=>setArchive(!archive)}>{archive?'回到旅行与照片':'查看历史记录'}<Icon name="chevron" size={16}/></button>
    <label className="task-search glass"><Icon name="search" size={18}/><input aria-label="搜索任务" value={query} onChange={e=>setQuery(e.target.value)} placeholder="找一段旅程或一个任务"/></label>
    <div className="task-list">{tasks.map(w=><button className="glass task-row" key={w.id} disabled={working} onClick={()=>act(()=>runtime.open(w.id))}>
      <span><strong>{w.title}</strong><small>{statusLabel(w.latestExecution?.status||w.status)}</small></span><Icon name="chevron" size={18}/>
    </button>)}</div>
    {!tasks.length&&<p className="production-empty">{query?'还没找到这个任务。':'从一个想法开始，任务会留在这里。'}</p>}
    <button className="text-btn" disabled={working} onClick={()=>act(()=>runtime.showTasks())}>重新读取任务<Icon name="replay" size={18}/></button>
  </Sheet>;
}

export function TaskDetails({snapshot:s,act,working}){
  const {setStage}=useTravel();
  const [preview,setPreview]=useState(null),[revision,setRevision]=useState('');
  const execution=s.execution,artifacts=s.artifacts||[];
  const historical=s.workflow.uiKind==='archive';
  useEffect(()=>{setPreview(null);setRevision('');},[s.workflow.id]);
  useEffect(()=>{if(preview&&!artifacts.some(a=>a.id===preview.artifact.id&&a.contentHash===preview.artifact.contentHash))setPreview(null);},[artifacts,preview]);
  const inspect=artifact=>act(async()=>{
    if(artifact.id===s.artifact?.id&&runtime.document){runtime.publish({taskDetails:false,panelDismissed:true});setStage(execution?.status==='completed'?'guide':'adopt');return;}
    const receipt=await runtime.artifactContent(artifact);setPreview({artifact,content:receipt.content});
  });
  const gated=!historical&&s.workflow.uiKind!=='photo'&&execution?.status==='awaiting_approval',final=!historical&&s.workflow.uiKind!=='photo'&&execution?.status==='awaiting_review';
  const approve=artifact=>act(async()=>{await (gated?runtime.review(artifact,'approve'):runtime.approveArtifacts([artifact.id]));setPreview(null);});
  const revise=artifact=>act(async()=>{await runtime.review(artifact,'revise',revision);setPreview(null);setRevision('');});
  return <Sheet label="任务与执行记录" className="task-details" onClose={()=>runtime.publish({taskDetails:false})}>
    <p className="eyebrow">ALONG THE WAY</p><h2>{s.workflow.title}</h2>
    <p className="task-caption" role="status">{statusLabel(execution?.status||s.workflow.status)}</p>
    {historical&&<p className="task-caption">旧工作流已归档，执行记录和成果可以查看与导出。</p>}
    {s.workflow.uiKind==='photo'&&['awaiting_approval','completed'].includes(execution?.status)&&<Primary disabled={working} onClick={()=>act(()=>runtime.call('openPhotoTask'))}>{execution.status==='completed'?'查看处理后的照片':'按已确认参数处理照片'}</Primary>}
    <details className="task-disclosure glass"><summary>这次想完成什么</summary><p className="task-brief">{readableBrief(s.plan?.goal||s.workflow.description)}</p><p>{s.plan?.deliverable||s.workflow.desiredOutput}</p></details>
    {execution&&<><div className="task-progress"><progress value={execution.progress} max="100" aria-label="服务端执行进度"/><small>{execution.progress}%</small></div>
      {!historical&&['failed','cancelled'].includes(execution.status)&&<div className="task-failure glass"><h3>这一段，需要再试一次。</h3><p>{execution.errorMessage||execution.nodes?.find(n=>n.errorMessage)?.errorMessage||'服务端尚未返回具体原因。已完成的步骤会保留。'}</p><Primary disabled={working} onClick={()=>act(()=>runtime.retry())}>从失败步骤继续</Primary></div>}
      <ol className="task-timeline">{execution.nodes?.map(node=><li key={node.id||node.nodeId} data-status={node.status}><span className="task-dot"/><div><strong>{node.name}</strong><small>{statusLabel(node.status)}</small>{node.outputSummary&&<details><summary>查看这一步的资料</summary><p className="task-step-output">{node.outputSummary}</p></details>}{node.errorMessage&&<p className="task-failure">{node.errorMessage}</p>}</div></li>)}</ol>
    </>}
    {artifacts.length>0&&<section className="task-artifacts"><h3>留下的成果</h3>{artifacts.map(a=><button className="glass task-row" key={a.id} disabled={working} onClick={()=>inspect(a)}><span><strong>{a.title}</strong><small>{a.extension?.toUpperCase()||a.kind}{a.metadata?.approvalGate?' · 待确认':''}</small></span><Icon name="book" size={18}/></button>)}</section>}
    {!artifacts.length&&<p className="task-caption">{execution?.status==='completed'?'这次没有独立成果文件，执行记录仍保留在这里。':'成果完成后，会出现在这里。'}</p>}
    {!!s.executionEvents?.length&&<details className="task-disclosure glass"><summary>沿途的执行记录</summary><ol className="task-events">{s.executionEvents.map(e=><li key={e.id}><p>{e.message}</p>{e.payload?.detail&&<small>{e.payload.detail}</small>}</li>)}</ol></details>}
    <details className="task-disclosure glass"><summary>执行明细</summary><dl><dt>任务</dt><dd>{s.workflow.id}</dd>{execution&&<><dt>实际调用</dt><dd>{execution.apiCalls??'尚未汇总'}</dd><dt>实际 tokens</dt><dd>{execution.tokenUsed??'尚未汇总'}</dd></>}{s.plan&&<><dt>预计 tokens</dt><dd>{s.plan.estimatedTokens}</dd></>}</dl></details>
    <button className="text-btn" disabled={working} onClick={()=>act(()=>runtime.refresh())}>重新读取进度<Icon name="replay" size={18}/></button>
    {preview&&<Sheet label="成果预览" className="task-preview" closeLabel="关闭成果预览" onClose={()=>setPreview(null)}>
      <p className="eyebrow">YOUR WORK, READY TO READ</p><h2>{preview.artifact.title}</h2><pre className="task-content">{preview.content}</pre>
      {(gated||final)&&<><p className="task-caption">确认当前显示的版本后，才会继续执行或采用成果。</p><Primary disabled={working} onClick={()=>approve(preview.artifact)}>{gated?'确认这份成稿':'采用这份成果'}</Primary>
        {gated&&<><textarea aria-label="成稿调整意见" placeholder="还想调整什么" value={revision} onChange={e=>setRevision(e.target.value)} maxLength={6000}/><button className="text-btn" disabled={working||!revision.trim()} onClick={()=>revise(preview.artifact)}>按意见调整<Icon name="edit" size={18}/></button></>}
      </>}
      <button className="text-btn" disabled={working} onClick={()=>act(()=>runtime.shareArtifact(preview.artifact))}>导出这份成果<Icon name="arrow" size={18}/></button>
    </Sheet>}
  </Sheet>;
}
