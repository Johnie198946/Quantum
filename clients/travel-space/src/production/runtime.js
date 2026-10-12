import {invoke,errorMessage} from './bridge';
import {documentToState,discoveryPlaces,stateToDocument} from './travel-adapter';
import {parseDiscovery,discoveryPrompt} from './travel-preflight';
import {preparationDescription,personalState} from './preparation';
import {mergeTravelEdits} from './travel-edits';

export function travelRequestDescription(profile,message){
  const r=profile.requirements||{},known=value=>value===undefined||value===null||value===''?'未定':String(value);
  const notes=[...new Set([...(r.notes||[]),profile.manualAdditional,!r.notes?.length?profile.additional:''].filter(Boolean).map(x=>x.trim()))];
  return [message?.trim(),`目的地：${known(profile.destination)}`,`出发城市：${known(r.origin||profile.origin)}`,
    `出发日期：${known(r.date)}`,`游玩天数：${known(r.duration||profile.duration)}`,`同行人数：${known(r.count||profile.count)}`,
    `预算倾向：${known(r.budget||profile.budget)}`,profile.amount?`预算金额：${profile.amount} ${known(profile.currency)}`:'',
    `旅行节奏：${known(r.pace||profile.pace)}`,`当地交通：${known(r.transport||profile.transport)}`,
    `兴趣偏好：${(r.interests||profile.interests||[]).join('、')||'未定'}`,...notes,
    ...(profile.selectedPlaces||[]).map(p=>`已选景点：${p.name}；来源：${p.sourceUrl}；核对日期：${p.checkedAt}`),preparationDescription(profile)].filter(Boolean).join('\n');
}

export class TravelRuntime {
  listeners=new Set(); state={loading:true,workflows:[],snapshot:null,error:'',sync:'草稿保存在此设备'};
  document=null; documentListeners=new Set(); queue=Promise.resolve(); timer=null; stopped=false; generation=0; mutations=0;
  get adopted(){return !!this.state.snapshot?.noteMode||this.state.snapshot?.execution?.status==='completed';}
  subscribe=(listener)=>{this.listeners.add(listener);return()=>this.listeners.delete(listener);};
  publish=(patch)=>{this.state={...this.state,...patch};this.listeners.forEach(fn=>fn());};
  call=(operation,payload={})=>{
    if(operation==='openTasks')return this.showTasks();
    if(operation==='openNative'){this.publish({taskDetails:true});return Promise.resolve();}
    return invoke(operation,{workflowId:this.state.snapshot?.workflow.id,...payload});
  };
  async showTasks(){try{const data=await invoke('bootstrap');this.publish({workflows:data.workflows,taskLibrary:true,error:''});}catch(e){this.publish({error:errorMessage(e)});}}
  route(workflowId){if(this.state.loading)this.pendingRoute=workflowId;else this.open(workflowId);}
  async boot(){this.stopped=false;try{const data=await invoke('bootstrap');if(this.stopped)return;
    if(data.note){this.document=JSON.parse(data.note.content);this.artifactHash=data.note.artifact.contentHash;this.profile={};this.places=discoveryPlaces(this.document);this.publish({snapshot:data.note,readOnly:!!data.readOnly,loading:false,sync:data.readOnly?'原始成果 · 只读预览':'已保存到笔记',error:''});this.documentListeners.forEach(fn=>fn({...documentToState(this.document),saved:true},{open:true,stage:'notebook'}));return;}
    const draft=data.draft,workflowId=draft?._workflowId;this.createRequest=draft?._createRequest||null;this.startRequest=draft?._startRequest||null;this.pendingEdits=draft?._travelEdits||null;this.publish({...data,draft:workflowId?null:draft,error:'',panelDismissed:true});
    if(workflowId&&data.workflows.some(w=>w.id===workflowId)){
      this.profile=draft.profile||{};this.navigationRequested=false;await this.refresh(workflowId);
      if(this.document&&draft._artifactHash===this.artifactHash){
        this.documentListeners.forEach(fn=>fn(documentToState({...this.document,client_state:draft},{}),{open:false}));
      }else if(this.document){this.recoveryDraft=draft;this.publish({recoveryAvailable:true});}
      else this.publish({draft});
    }
    this.publish({loading:false});
  }catch(error){this.publish({loading:false,error:errorMessage(error)});}finally{if(this.pendingRoute&&!this.stopped){const id=this.pendingRoute;this.pendingRoute=null;await this.open(id);}}}

  stop(){this.stopped=true;this.generation++;clearTimeout(this.timer);}
  async open(workflowId){this.generation++;this.pendingDraft=null;this.pendingEdits=null;this.createRequest=null;this.startRequest=null;this.preparedDescription=null;this.publish({snapshot:null,draft:null,panelDismissed:false,taskLibrary:false,taskDetails:false});this.profile={};this.document=null;this.artifactHash=null;this.navigationRequested=true;this.restoreTaskDraft=true;await this.refresh(workflowId);const s=this.state.snapshot;if(s&&!this.document&&(s.workflow.uiKind==='archive'||s.artifacts?.length||['completed','cancelled'].includes(s.execution?.status||s.workflow.status)))this.publish({taskDetails:true});}
  async refresh(workflowId=this.state.snapshot?.workflow.id){
    if(!workflowId||this.mutations)return;
    const generation=this.generation;
    try{
      const snapshot=await invoke('snapshot',{workflowId});if(this.stopped||generation!==this.generation||this.mutations)return;
      this.publish({snapshot,offline:!!snapshot.offline,sync:snapshot.offline?'离线手记 · 尚未同步':this.state.sync,error:''});
      this.preparedDescription=snapshot.workflow.description||this.preparedDescription;
      const draft=snapshot.draft?._workflowId===workflowId?snapshot.draft:null;
      if(this.restoreTaskDraft){this.restoreTaskDraft=false;this.pendingEdits=draft?._travelEdits||null;this.createRequest=draft?._createRequest||null;this.startRequest=draft?._startRequest||null;this.profile=draft?.profile||{};
        if(!snapshot.content&&snapshot.workflow.uiKind==='travel'){const value=draft||{profile:{destination:snapshot.workflow.title.replace(/ · 旅行计划$/,''),additional:snapshot.workflow.description,flowCheckpoint:'preferences'},days:[]};this.documentListeners.forEach(fn=>fn(value,{open:true}));this.navigationRequested=false;}}
      if(snapshot.content&&snapshot.artifact?.contentHash!==this.artifactHash){
        if(this.navigationRequested)this.publish({taskDetails:false});
        const document=JSON.parse(snapshot.content);this.document=document;this.artifactHash=snapshot.artifact.contentHash;
        let display=document;if(this.pendingEdits?.workflowId===workflowId)display=mergeTravelEdits(this.pendingEdits.base,this.pendingEdits.edited,document);
        const personal=draft&&draft._artifactHash===snapshot.artifact.contentHash?draft:null;
        if(draft&&!personal&&!this.pendingEdits){this.recoveryDraft=draft;this.publish({recoveryAvailable:true});}
        this.places=discoveryPlaces(document);this.documentListeners.forEach(fn=>fn(documentToState(personal?{...display,client_state:personal}:display,this.profile||{}),{open:this.navigationRequested}));
        this.navigationRequested=false;
      }
      clearTimeout(this.timer);
      const awaitingExecution=snapshot.noteMode?false:snapshot.execution?!['completed','failed','cancelled'].includes(snapshot.execution.status):!['completed','failed','cancelled','ready'].includes(snapshot.workflow.status);
      if(snapshot.offline||awaitingExecution)
        this.timer=setTimeout(()=>this.refresh(workflowId),snapshot.offline?8000:2000);
    }catch(error){if(generation===this.generation)this.publish({error:errorMessage(error)});}
  }
  async prepare(profile,message){
    const prior=this.state.snapshot,description=travelRequestDescription(profile,message);
    if([...description].length>12000)throw new Error('旅行条件超过12000字，请减少重复说明后再确认；已有草稿会保留。');
    if(prior?.execution)throw new Error('这段旅程已开始制作，请从成稿中调整安排。');
    if(prior&&this.preparedDescription===description){await this.refresh(prior.workflow.id);this.publish({panelDismissed:false});return;}
    this.generation++;this.profile=profile;
    this.navigationRequested=false;this.document=null;this.artifactHash=null;
    const generation=this.generation;this.publish({snapshot:null,busy:true,error:'',panelDismissed:false});
    if(!prior&&this.createRequest?.description!==description)this.createRequest={description,id:crypto.randomUUID()};
    try{if(this.pendingDraft)await invoke('draft',{state:{...this.pendingDraft,profile,_workflowId:prior?.workflow.id||null,_createRequest:this.createRequest}});
      const response=prior?await invoke('replan',{workflowId:prior.workflow.id,instruction:'按更新后的旅行条件重新制作计划',description}):await invoke('create',{title:profile.destination+' · 旅行计划',description,requestId:this.createRequest.id});
      if(generation===this.generation){this.preparedDescription=description;await this.refresh(prior?.workflow.id||response.workflow.id);if(this.state.snapshot?.workflow.description&&this.state.snapshot.workflow.description!==description)throw new Error('服务端未保存更新后的旅行条件，请更新后端后重试；旧计划不会启动。');}
    }catch(error){if(generation===this.generation)this.publish({snapshot:prior,error:errorMessage(error)});throw error;}finally{if(generation===this.generation)this.publish({busy:false});}
  }
  async converge(profile,message,history=[]){
    const generation=this.generation;
    const response=await invoke('ask',{question:'只收敛旅行需求，不创建工作流、不提出执行操作。用 JSON 返回 {"summary":"忠实总结用户已说的条件，未知条件写未定","question":"下一句最必要的问题，没有则空字符串","ready":false}。用户明确同意条件未定时可以收敛；不得替用户确定日期、预算、人数或偏好。\n'+travelRequestDescription(profile,message)+'\n对话：'+JSON.stringify(history)});
    if(generation!==this.generation)throw new Error('旅行想法已切换。');
    if(response.hasActions)throw new Error('请先继续核对想法，再确认旅行计划。');
    let data;try{data=JSON.parse(response.answer.replace(/^```(?:json)?\s*/,'').replace(/\s*```$/,''));}catch{throw new Error('暂未收到需求总结，可以补充想法或确认已填写的条件。');}
    const r=profile.requirements||{},openConsent=/都未定|全部未定|其他[^。]*未定|先[^。]*规划/.test(history.filter(m=>m.role==='user').map(m=>m.text).join(' '));
    const ready=data.ready===true&&((!!r.origin&&!!r.duration&&!!r.count)||openConsent);
    return {summary:String(data.summary||'').slice(0,4000),question:String(data.question||(!ready?'从哪里出发，预计玩几天、几个人？没确定也可以保留。':'')).slice(0,400),ready};
  }
  async discover(profile,message){
    const generation=++this.generation;this.profile=profile;this.document=null;this.artifactHash=null;
    clearTimeout(this.timer);this.publish({snapshot:null,panelDismissed:true,busy:true,error:''});
    try{const response=await invoke('ask',{question:discoveryPrompt(profile,travelRequestDescription(profile,message))});
      if(generation!==this.generation)throw new Error('旅行想法已切换。');
      if(response.hasActions)throw new Error('景点收集尚未完成，暂不启动制作任务。');
      const discovery=parseDiscovery(response.answer);this.places=discovery.places;this.publish({discovery});return discovery;
    }catch(error){if(generation===this.generation)this.publish({error:errorMessage(error)});throw error;}finally{if(generation===this.generation)this.publish({busy:false});}
  }
  async scopedAction(operation,payload){const generation=this.generation,workflowId=this.state.snapshot?.workflow.id;await this.call(operation,{workflowId,...payload});if(generation!==this.generation)throw new Error('行程已切换，请查看原任务的最新状态。');await this.refresh(workflowId);}
  async respond(response){await this.scopedAction('respond',{response,round:this.state.snapshot?.clarification?.session?.roundNumber});}
  async approvePlan(){const plan=this.state.snapshot?.plan;if(!plan)throw new Error('请先等待服务端计划完成。');
    await this.scopedAction('approvePlan',{hash:plan.contentHash,revision:plan.activationRevision});}
  async start(){const s=this.state.snapshot,plan=s?.plan;if(!plan)throw new Error('当前计划版本尚未读取，请重新核对。');const signature=s.workflow.id+':'+plan.contentHash+':'+plan.activationRevision;
    if(this.startRequest?.signature!==signature)this.startRequest={signature,id:crypto.randomUUID()};
    if(this.pendingDraft)await this.saveDraft(this.pendingDraft);
    await this.scopedAction('start',{requestId:this.startRequest.id,hash:plan.contentHash,revision:plan.activationRevision});}
  async retry(){const s=this.state.snapshot;await this.scopedAction(s.execution?'retryExecution':'retryPlanning',s.execution?{executionId:s.execution.id}:{});}
  async artifactContent(artifact){const s=this.state.snapshot;return this.call('artifactContent',{executionId:s.execution.id,artifactId:artifact.id,hash:artifact.contentHash});}
  async shareArtifact(artifact){const s=this.state.snapshot;return this.call('shareArtifact',{executionId:s.execution.id,artifactId:artifact.id,hash:artifact.contentHash});}
  async review(artifact,decision,comment=''){const s=this.state.snapshot;await this.scopedAction('reviewArtifact',{executionId:s.execution.id,artifactId:artifact.id,hash:artifact.contentHash,decision,comment});}
  async approveArtifacts(ids){const s=this.state.snapshot;const hashes=Object.fromEntries(ids.map(id=>[id,s.artifacts.find(a=>a.id===id)?.contentHash]));await this.scopedAction('approveOutput',{executionId:s.execution.id,artifactIds:ids,expectedHashes:hashes});}
  async approveOutput(){const s=this.state.snapshot;
    if(!s.artifact)throw new Error('尚未收到旅行成果。');
    if(!['awaiting_approval','awaiting_review','completed'].includes(s.execution?.status))throw new Error(s.execution?.status==='failed'?s.execution.errorMessage||'生成未完成，请查看已完成内容和失败记录。':'正在整理最终手记，请等待最新成稿。');
    if(s.execution.status==='awaiting_approval'){
      await this.scopedAction('reviewArtifact',{executionId:s.execution?.id,artifactId:s.artifact.id,hash:s.artifact.contentHash});throw new Error('已确认当前成稿，正在整理最终手记；完成后请再查看并采用。');
    }
    await this.scopedAction('approveOutput',{executionId:s.execution.id,artifactIds:[s.artifact.id],expectedHashes:{[s.artifact.id]:s.artifact.contentHash}});
    if(this.pendingEdits)await this.applyPendingEdits();}
  async captureEdits(state){if(!this.document)return;this.pendingEdits={workflowId:this.state.snapshot.workflow.id,base:this.document,edited:stateToDocument(this.document,state.days,state.profile),personal:personalState(state)};await this.saveDraft(personalState(state));}
  async applyPendingEdits(){const pending=this.pendingEdits;if(!pending||pending.workflowId!==this.state.snapshot?.workflow.id)return;const proposed=mergeTravelEdits(pending.base,pending.edited,this.document);
    if(JSON.stringify(proposed)!==JSON.stringify(this.document)){await this.enqueue('revise',{content:JSON.stringify(proposed),reason:'用户采用成稿时确认的安排调整'});this.document=proposed;}
    await this.persist(pending.personal);this.pendingEdits=null;await this.saveDraft(pending.personal);this.artifactHash=null;await this.refresh();}
  enqueue(operation,payload={}){
    const workflowId=this.state.snapshot?.workflow.id,generation=this.generation,draft=this.pendingDraft;
    this.queue=this.queue.catch(()=>{}).then(async()=>{
      if(this.state.readOnly)throw new Error('这是原始成果预览，请从旅行笔记继续记录。');
      const s=this.state.snapshot;if(generation!==this.generation||workflowId!==s?.workflow.id)throw new Error('任务已切换，本次修改未发送。');if(this.state.offline)throw new Error('当前离线，修改已保存在此设备，联网后再同步。');if(!s?.artifact||!this.adopted)throw new Error('请先采用服务端旅行成果。');
      this.publish({sync:'正在保存…'});
      this.mutations++;let receipt;try{receipt=await this.call(operation,{workflowId,executionId:s.execution?.id,artifactId:s.artifact.id,hash:s.artifact.contentHash,
        requestId:crypto.randomUUID(),...payload});}finally{this.mutations--;}
      if(generation!==this.generation)throw new Error('任务已切换，请重新读取保存结果。');
      if(receipt.content)this.document=JSON.parse(receipt.content);
      this.artifactHash=receipt.contentHash;
      this.publish({snapshot:{...s,artifact:{...s.artifact,id:receipt.id,contentHash:receipt.contentHash}},sync:s.noteMode?'已保存到笔记':'已保存到 Quantum',error:''});
      return receipt;
    }).catch(error=>{if(generation!==this.generation)throw error;if(draft)this.recoveryDraft=draft;this.publish({sync:'尚未同步',error:errorMessage(error),recoveryAvailable:!!this.recoveryDraft});throw error;});
    return this.queue;
  }
  async saveNotebook(){
    await this.queue.catch(()=>{});
    const generation=this.generation,s=this.state.snapshot;
    if(!this.adopted||!s?.artifact)throw new Error('请先采用服务端的最终旅行手记。');
    const receipt=await this.call('saveNotebook',{executionId:s.execution?.id,artifactId:s.artifact.id,hash:s.artifact.contentHash,requestId:crypto.randomUUID()});
    if(generation!==this.generation)throw new Error('旅行已切换，请从笔记库查看保存结果。');
    if(!receipt.noteId||!receipt.contentHash||!receipt.content)throw new Error('尚未收到笔记保存回执，手记还在草稿中。');
    this.document=JSON.parse(receipt.content);this.artifactHash=receipt.contentHash;
    this.publish({snapshot:{...s,noteMode:true,noteId:receipt.noteId,artifact:{id:receipt.noteId,contentHash:receipt.contentHash}},sync:'已保存到笔记',error:''});
    return receipt;
  }
  async saveDraft(state){
    const generation=this.generation,workflowId=this.state.snapshot?.workflow.id;this.pendingDraft={...state,_workflowId:workflowId||null,_artifactHash:this.artifactHash||null,_createRequest:this.createRequest||null,_startRequest:this.startRequest||null,_travelEdits:this.pendingEdits||null};
    await invoke('draft',{state:{...this.pendingDraft,...(this.recoveryDraft?{_recoveryDraft:this.recoveryDraft}:{})}});
    if(generation!==this.generation)throw new Error('任务已切换，草稿未发送到其他任务。');
  }
  async persist(state){
    if(this.state.readOnly)return;
    const generation=this.generation,workflowId=this.state.snapshot?.workflow.id;
    const write=()=>invoke('draft',{state:{...state,_workflowId:workflowId||null,_artifactHash:this.artifactHash||null,...(this.recoveryDraft?{_recoveryDraft:this.recoveryDraft}: {})}});
    await this.saveDraft(state);
    if(generation!==this.generation)throw new Error('任务已切换，草稿未发送到其他任务。');
    if(this.adopted){await this.enqueue('saveState',{state});if(generation===this.generation){this.recoveryDraft=null;this.publish({recoveryAvailable:false});await write();}}
  }

}

export const runtime=new TravelRuntime();
