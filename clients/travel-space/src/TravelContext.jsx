import React,{createContext,useContext,useState,useCallback,useRef,useEffect,useSyncExternalStore} from 'react';
import {notebookSnapshot} from './components/lifecycle/SavedPlanSheet';
import {normalizeSession,beginTrip,finishTrip,recordProgress,validateRemainingChange} from './components/lifecycle/trip-model';
import {reviseDay,scheduleIssues,undoDayRevision,stableItems} from './components/journal/journal-model';
import {defaultProfile,initialDays,images,replacePlaces} from './data';
import {runtime,travelRequestDescription} from './production/runtime';
import {setMapDays} from './components/mapRoute';
import {serviceCache,resetServiceCache} from './production/service-provider';
import {stateToDocument} from './production/travel-adapter';
import {profileFromRequirements} from './components/travel-requirements';
import {draftDays} from './production/travel-preflight';
import {personalState} from './production/preparation';
import {readTravel,writeTravel,DRAFT_KEY,SAVED_KEY,defaultNotebookConfig} from './components/travel-storage';
const TravelContext=createContext(null);
export function TravelProvider({children}){
 const offline=useSyncExternalStore(runtime.subscribe,()=>!!runtime.state.offline);
 const [todosOpen,setTodosOpen]=useState(false),[pendingWarning,setPendingWarning]=useState(false),pendingAction=useRef(null);
 const [initial]=useState(()=>readTravel(DRAFT_KEY));
 const [servicesFocus,setServicesFocus]=useState({kind:'flight',dayId:1,origin:'route'});
 const [stage,changeStage]=useState(()=>({services:'services',journal:'notebook',notebook:'notebook',budget:'guide',trip:'trip',today:'trip',review:'trip'})[new URLSearchParams(window.location.search).get('view')]||'workflow'),[orbArrival,setOrbArrival]=useState(null),arrivalSerial=useRef(0);
 const setStage=useCallback((next,options={})=>{if(next==='guide'&&!runtime.adopted){runtime.publish({error:'请先查看成稿并明确采用这份行程。'});return;}setProfile(prev=>({...prev,flowCheckpoint:next}));setOrbArrival(options.fromOrb?{stage:next,token:++arrivalSerial.current}:options.fromCard?{stage:next,origin:options.fromCard,fromCard:true,token:++arrivalSerial.current}:null);changeStage(next);},[]);
 const finishOrbArrival=useCallback(token=>setOrbArrival(value=>value?.token===token?null:value),[]);
 const [profile,setProfile]=useState(initial?.profile||defaultProfile),[days,setDays]=useState(initial?.days||initialDays);
 const [selected,setSelected]=useState(initial?.selected||[]),[extraCards,setExtraCards]=useState(()=>initial?.extraCards.map(x=>({...x,image:images[x.imageId]||images.senganen}))||[]);
 const [message,setMessage]=useState(initial?.message||''),[followUps,setFollowUps]=useState(initial?.followUps||[]),[followUpDraft,setFollowUpDraft]=useState(initial?.followUpDraft||'');
 const [saved,setSaved]=useState(initial?.saved||false),[noteTitle,setNoteTitle]=useState(initial?.noteTitle||'旅行手记'),[entries,setEntries]=useState(initial?.entries||{});
 const [notebookConfig,setNotebookConfig]=useState(initial?.notebookConfig||defaultNotebookConfig),[notebookOrigin,setNotebookOrigin]=useState('guide'),[notebookRequest,setNotebookRequest]=useState(null);
 const [savedTrip,setSavedTrip]=useState(()=>readTravel(SAVED_KEY)),[storageAvailable,setStorageAvailable]=useState(true);
 const snapshot=useRef(null);snapshot.current={profile,days,selected,extraCards,message,followUps,followUpDraft,saved,noteTitle,entries,notebookConfig};
 const persist=useCallback(()=>{const current=snapshot.current,draftOK=writeTravel(DRAFT_KEY,current);let saveOK=true;if(current.saved){saveOK=writeTravel(SAVED_KEY,current);setSavedTrip(current);}setStorageAvailable(draftOK&&saveOK);},[]);
 useEffect(()=>{const timer=setTimeout(persist,700);return()=>clearTimeout(timer);},[profile,days,selected,extraCards,message,followUps,followUpDraft,saved,noteTitle,entries,notebookConfig,persist]);
 useEffect(()=>{const hidden=()=>{if(document.hidden)persist();};window.addEventListener('pagehide',persist);document.addEventListener('visibilitychange',hidden);return()=>{window.removeEventListener('pagehide',persist);document.removeEventListener('visibilitychange',hidden);};},[persist]);
 useEffect(()=>{
  const hydrate=(value,options={open:true})=>{if(!value?.profile?.destination)return;replacePlaces(runtime.places?.length?runtime.places:value.profile.discoveryPlaces||[]);setMapDays(value.days||[]);const found=value.profile.serviceResults||{};for(const key of Object.keys(serviceCache.weather))delete serviceCache.weather[key];Object.assign(serviceCache.weather,found.weatherByDay||{});serviceCache.flights=found.flight||[];serviceCache.routes=found.route||[];serviceCache.candidates.splice(0,serviceCache.candidates.length,...(found.hotel||[]),...(found.restaurant||[]),...(found.activity||[]));setProfile({...defaultProfile,...value.profile});setDays(value.days||[]);setSelected(value.selected||[]);setExtraCards(value.extraCards||[]);setMessage(value.message||'');setFollowUps(value.followUps||[]);setFollowUpDraft(value.followUpDraft||'');setEntries(value.entries||{});setNoteTitle(value.noteTitle||'旅行手记');setNotebookConfig(value.notebookConfig||defaultNotebookConfig);setSaved(!!value.saved);if(options.open)changeStage(options.stage||(runtime.document?(runtime.adopted?(value.saved||runtime.state.snapshot?.noteMode?'notebook':'guide'):'adopt'):value.profile.flowCheckpoint||'chat'));};
  runtime.documentListeners.add(hydrate);
  let restored=false;
  const unsubscribe=runtime.subscribe(()=>{if(!restored&&!runtime.state.loading){restored=true;if(runtime.state.draft?.profile?.destination)hydrate(runtime.state.draft,{open:false});}});
  return()=>{runtime.documentListeners.delete(hydrate);unsubscribe();};
 },[]);
 useEffect(()=>{
  const generation=runtime.generation;const timer=setTimeout(()=>{
   if(generation!==runtime.generation||runtime.personalSaveHold)return;const state=snapshot.current;
   if(!state.profile.destination&&!state.message)return;
   const save=async()=>{
    const personal=personalState(state);
    await runtime.saveDraft(personal);
    if(generation!==runtime.generation)return;
    if(!runtime.state.offline&&runtime.document&&runtime.adopted){
     const proposed=stateToDocument(runtime.document,state.days,state.profile);
     if(JSON.stringify({...proposed,client_state:null})!==JSON.stringify({...runtime.document,client_state:null})){
      await runtime.enqueue('revise',{content:JSON.stringify(proposed),reason:'用户确认手记中的行程调整'});if(generation!==runtime.generation)return;runtime.document=proposed;
     }
    }
    if(generation!==runtime.generation||runtime.personalSaveHold)return;await runtime.persist(personal);
   };
   save().catch(error=>runtime.publish({error:error.message,sync:'尚未同步'}));
  },1000);return()=>clearTimeout(timer);
 },[profile,days,selected,extraCards,message,followUps,saved,noteTitle,entries,notebookConfig,offline]);
 const selectPlace=useCallback(id=>setSelected(prev=>prev.includes(id)?prev:[...prev,id]),[]);
 const updateDay=useCallback(next=>{const state=snapshot.current,day=state.days.find(d=>d.id===next.id);if(!day)return '这一天已不存在。';const issues=validateRemainingChange(state.profile,day,next.items);if(issues.length)return issues.join(' ');const begun=normalizeSession(state.profile,state.days).phase!=='before';if(begun){const schedule=scheduleIssues(next.items);if(schedule.length)return schedule.join(' ');}const undo=begun?undoDayRevision(day):null,exactUndo=undo&&JSON.stringify(stableItems(next))===JSON.stringify(stableItems(undo))&&JSON.stringify(next.journalRevisions)===JSON.stringify(undo.journalRevisions);const revised=begun&&!exactUndo?reviseDay(day,next.items,{source:'行程详情',reason:'调整当前安排'}):next;const recorded={...next,items:revised.items,journalRevisions:revised.journalRevisions};setDays(prev=>prev.map(d=>d.id===next.id?recorded:d));return '';},[]);
 const commitPersonal=async next=>{if(runtime.personalSaveHold)throw new Error('正在保存这次变化，请稍候。');const generation=runtime.generation;runtime.personalSaveHold=1;try{await runtime.queue.catch(()=>{});if(generation!==runtime.generation)throw new Error('旅行已切换。');if(runtime.document&&runtime.adopted){const proposed=stateToDocument(runtime.document,next.days,next.profile);if(JSON.stringify({...proposed,client_state:null})!==JSON.stringify({...runtime.document,client_state:null})){await runtime.enqueue('revise',{content:JSON.stringify(proposed),reason:'用户确认当前安排'});runtime.document=proposed;}}await runtime.persist(personalState(next));if(generation!==runtime.generation)throw new Error('旅行已切换，变化保留在原任务中。');}finally{runtime.personalSaveHold=0;}};
 const beginJourney=async()=>{try{const current=snapshot.current,next=beginTrip(current.profile,current.days);await commitPersonal({...current,...next});setProfile(next.profile);setDays(next.days);return '';}catch(e){return e.message;}};
 const endJourney=async()=>{try{const current=snapshot.current,next=finishTrip(current.profile);await commitPersonal({...current,profile:next});setProfile(next);return '';}catch(e){return e.message;}};
 const recordJourneyProgress=async(day,action,status)=>{
  const translations={in_progress:'in_progress',completed:'completed',cancelled:'cancelled',skipped:'skipped',delayed:'delayed','进行中':'in_progress','已完成':'completed','已取消':'cancelled','已跳过':'skipped','已延后':'delayed'};
  const progress=translations[status]||status;
  const generation=runtime.generation;try{await runtime.enqueue('progress',{actionId:action.journalId||action.id,progress});if(generation!==runtime.generation)throw new Error('任务已切换，请查看原旅行的进度。');runtime.artifactHash=null;await runtime.refresh();return '';}catch(e){return e.message;}
 };
 const setJourneyDay=id=>{if(!snapshot.current.days.some(d=>String(d.id)===String(id)))return;setProfile(prev=>({...prev,tripSession:{...normalizeSession(prev,snapshot.current.days),activeDayId:id}}));};
 const reorderDays=useCallback(order=>{if(normalizeSession(snapshot.current.profile,snapshot.current.days).phase!=='before')return '出发后的日期顺序会保留，请只调整剩余安排。';setDays(prev=>order.map((item,index)=>({...prev.find(day=>day.id===item.id),order:index+1,date:prev[index].date,dateISO:prev[index].dateISO||null})));return '';},[]);
 const updateDates=useCallback(range=>{
  if(normalizeSession(snapshot.current.profile,snapshot.current.days).phase!=='before')return '出发后的日期会保留，请只调整剩余安排。';
  const labels=range.map(value=>{const date=new Date(value*86400000);return(date.getUTCMonth()+1)+'月'+date.getUTCDate()+'日';});
  setProfile(prev=>({...prev,dates:labels.join(' — '),dateRange:range.map(value=>new Date(value*86400000).toISOString().slice(0,10)),requirements:prev.requirements?{...prev.requirements,date:new Date(range[0]*86400000).toISOString().slice(0,10)}:undefined}));
  setDays(prev=>prev.map((day,index)=>{const date=new Date((range[0]+index)*86400000);return {...day,date:(date.getUTCMonth()+1)+'月'+date.getUTCDate()+'日',dateISO:date.toISOString().slice(0,10)};}));
 },[]);
 const confirmRequirements=useCallback(draft=>{
  setProfile(prev=>profileFromRequirements(prev,draft));
  setDays(prev=>prev.map((day,index)=>{if(!draft.date||draft.date==='未定')return {...day,date:'日期未定'};const date=new Date(draft.date+'T00:00:00Z');date.setUTCDate(date.getUTCDate()+index);return {...day,date:(date.getUTCMonth()+1)+'月'+date.getUTCDate()+'日',dateISO:date.toISOString().slice(0,10)};}));
 },[]);
 const showDiscovery=async readyProfile=>{
  const discovery=await runtime.discover(readyProfile,snapshot.current.message);
  replacePlaces(discovery.places);setSelected([]);setProfile({...readyProfile,discoveryPlaces:discovery.places,conversationSummary:discovery.summary,flowCheckpoint:'discover'});
  const draft=draftDays(readyProfile,[]);setDays(draft);setMapDays(draft);setStage('discover');
 };
 const confirmPlaceFolder=()=>{
  const current=snapshot.current,chosen=(current.profile.discoveryPlaces||[]).filter(p=>current.selected.includes(p.id));
  const next={...current.profile,selectedPlaces:chosen,flowCheckpoint:'preferences'},draft=draftDays(next,chosen);
  setProfile(next);setDays(draft);setMapDays(draft);setStage('preferences');
 };
 const confirmTripPlan=async()=>{
  const current=snapshot.current,chosen=(current.profile.discoveryPlaces||[]).filter(p=>current.selected.includes(p.id));
  const next={...current.profile,selectedPlaces:chosen},draft=draftDays(next,chosen);
  setProfile(next);setDays(draft);setMapDays(draft);await runtime.saveDraft(personalState({...current,profile:next,days:draft}));await runtime.prepare(next,current.message);
 };
 const enterTransport=()=>{runtime.publish({panelDismissed:true});openServices('flight',snapshot.current.days[0]?.id,{beforeGeneration:true});};
 const startMaking=async()=>{
  if(runtime.state.snapshot?.workflow.status!=='agent_ready'||runtime.state.snapshot?.execution)throw new Error('请先确认旅行计划，再开始制作。');
  const current=snapshot.current;runtime.profile={...current.profile,preflightServiceDrafts:current.days.map(d=>({day:d.order,services:d.journalServices||null}))};
  await runtime.saveDraft(personalState(current));
  if(travelRequestDescription(current.profile,current.message)!==runtime.preparedDescription){await runtime.prepare(runtime.profile,current.message);throw new Error('交通与预订条件已更新，请确认更新后的旅行计划，再开始制作。');}
  await runtime.start();runtime.publish({panelDismissed:true});setStage('generating');
 };
 const adoptDraft=async()=>{if(runtime.personalSaveHold)throw new Error('正在保存，请稍候。');runtime.personalSaveHold=1;try{await runtime.captureEdits(snapshot.current);await runtime.approveOutput();}finally{runtime.personalSaveHold=0;}};
 const exportNotebook=async()=>{await commitPersonal(snapshot.current);const s=runtime.state.snapshot;await runtime.call('printNotebook',{executionId:s.execution?.id,artifactId:s.artifact.id,hash:s.artifact.contentHash});};
 const saveNotebook=useCallback(async config=>{
  const savedProfile={...snapshot.current.profile,notebookSnapshot:notebookSnapshot(snapshot.current.days,snapshot.current.noteTitle)},next={...snapshot.current,profile:savedProfile,saved:true,notebookConfig:config};await commitPersonal({...next,saved:false});await runtime.saveNotebook();setProfile(savedProfile);setNotebookConfig(config);setSaved(true);setNotebookOrigin('guide');setSavedTrip(next);const savedOK=writeTravel(SAVED_KEY,next),draftOK=writeTravel(DRAFT_KEY,next);setStorageAvailable(savedOK&&draftOK);setStage('notebook');
 },[setStage]);
 const resumeSavedTrip=useCallback(()=>{
  const value=readTravel(SAVED_KEY)||savedTrip;if(!value)return;
  setProfile(value.profile);setDays(value.days);setSelected(value.selected);setExtraCards(value.extraCards.map(x=>({...x,image:x.image||images[x.imageId]||images.senganen})));setMessage(value.message||'');setFollowUps(value.followUps);setFollowUpDraft(value.followUpDraft||'');setNoteTitle(value.noteTitle);setEntries(value.entries);setNotebookConfig(value.notebookConfig);setSaved(true);setNotebookOrigin('workflow');setStage(value.profile.tripSession?.phase&&value.profile.tripSession.phase!=='before'?'trip':'notebook');
 },[savedTrip,setStage]);
 const openNotebook=useCallback((origin='guide',options={})=>{setNotebookOrigin(origin);setNotebookRequest({...options,token:Date.now()});setStage('notebook');},[setStage]);
 const reviseJournalDay=(dayId,items,options={})=>{
  const day=snapshot.current.days.find(d=>d.id===dayId),issues=[...scheduleIssues(items),...(day?validateRemainingChange(snapshot.current.profile,day,items):[])];
  if(!day)return '这一天已不存在，请重新打开手记。';
  if(issues.length)return issues.join(' ');
  const next=reviseDay(day,items,options);setDays(prev=>prev.map(d=>d.id===day.id?next:d));return '';
 };
 const applyJournalEdit=({title,subtitle,cover,flags,draft})=>{
  if(!title||draft.length!==days.length||draft.some(d=>!d.name.trim()))return '请补齐手记和每天的标题。';
  const issues=draft.flatMap(d=>[...scheduleIssues(d.items),...validateRemainingChange(snapshot.current.profile,days.find(x=>x.id===d.id)||d,d.items)]);if(issues.length)return issues.join(' ');
  setNoteTitle(title);setNotebookConfig(prev=>({...prev,cover,flags}));setProfile(prev=>({...prev,journal:{...prev.journal,subtitle:subtitle.trim()}}));
  setDays(prev=>prev.map(d=>{const next=draft.find(x=>x.id===d.id);return {...reviseDay(d,next.items,{source:'整体编辑',reason:'在手记中调整当天安排'}),name:next.name.trim(),journalServices:next.journalServices};}));
  setEntries(prev=>({...prev,...Object.fromEntries(draft.map(d=>[d.id,d.record]))}));return '';
 };
 const openServices=(kind='flight',dayId=days[0]?.id,options={})=>{setServicesFocus({...options,kind,dayId,requestId:Date.now(),origin:['route','guide','notebook','trip'].includes(stage)?stage:'guide'});setStage('services');};
 const todos=Array.isArray(profile.todos)?profile.todos:[],pendingCount=todos.filter(t=>!t.done).length;
 const markPending=useCallback((source,title)=>setProfile(prev=>{const rows=Array.isArray(prev.todos)?prev.todos:[],found=rows.find(t=>t.source===source);return {...prev,todos:found?rows.map(t=>t.id===found.id?{...t,done:false}:t):[...rows,{id:crypto.randomUUID(),source,title:title.slice(0,100),done:false,at:Date.now()}]};}),[]);
 const addTodo=useCallback(title=>setProfile(prev=>({...prev,todos:[...(prev.todos||[]),{id:crypto.randomUUID(),source:'',title:title.slice(0,100),done:false,at:Date.now()}]})),[]);
 const toggleTodo=useCallback(id=>setProfile(prev=>({...prev,todos:(prev.todos||[]).map(t=>t.id===id?{...t,done:!t.done}:t)})),[]);
 const reorderTodos=useCallback(rows=>setProfile(prev=>({...prev,todos:rows})),[]);
 const requestGenerate=action=>{if(pendingCount){pendingAction.current=action;setPendingWarning(true);}else action();};
 const continueGeneration=()=>{const action=pendingAction.current;pendingAction.current=null;setPendingWarning(false);action?.();};
 const closeWarning=()=>{pendingAction.current=null;setPendingWarning(false);};
 const reset=()=>{runtime.generation++;runtime.pendingDraft=null;runtime.pendingEdits=null;runtime.createRequest=null;runtime.startRequest=null;resetServiceCache();clearTimeout(runtime.timer);runtime.document=null;runtime.artifactHash=null;runtime.preparedDescription=null;runtime.publish({snapshot:null,error:'',discovery:null,panelDismissed:true,taskDetails:false,taskLibrary:false});setTodosOpen(false);setPendingWarning(false);pendingAction.current=null;setStage('workflow');setProfile(defaultProfile);setDays(initialDays);setSelected([]);setExtraCards([]);setMessage('');setFollowUps([]);setFollowUpDraft('');setSaved(false);setNoteTitle('旅行手记');setNotebookConfig(defaultNotebookConfig);setNotebookOrigin('guide');setEntries({});};
 return <TravelContext.Provider value={{todos,pendingCount,markPending,addTodo,toggleTodo,reorderTodos,todosOpen,setTodosOpen,pendingWarning,requestGenerate,continueGeneration,closeWarning,stage,setStage,beginJourney,endJourney,recordJourneyProgress,setJourneyDay,servicesFocus,openServices,reviseJournalDay,applyJournalEdit,orbArrival,finishOrbArrival,profile,setProfile,exportNotebook,adoptDraft,confirmRequirements,showDiscovery,confirmPlaceFolder,confirmTripPlan,enterTransport,startMaking,days,updateDay,reorderDays,updateDates,selected,setSelected,selectPlace,message,setMessage,followUps,setFollowUps,followUpDraft,setFollowUpDraft,saved,setSaved,noteTitle,setNoteTitle,entries,setEntries,extraCards,setExtraCards,reset,notebookConfig,notebookOrigin,notebookRequest,openNotebook,saveNotebook,savedTrip,resumeSavedTrip,storageAvailable}}>{children}</TravelContext.Provider>;
}
export function useTravel(){return useContext(TravelContext);}
