import FloatingField from './FloatingField';
import {runtime} from '../production/runtime';
import {invoke,errorMessage} from '../production/bridge';
import React,{useState,useEffect,useLayoutEffect,useRef,useCallback} from 'react';
import {createPortal} from 'react-dom';
import {AnimatePresence,motion,useReducedMotion} from 'motion/react';
import {useTravel} from '../TravelContext';
import {Icon,Sheet,Primary} from './UI';
import FlyingPanel,{flightOrigin} from './FlyingPanel';
import TravelComposer from './TravelComposer';
import TravelThinkingOrb from './TravelThinkingOrb';
import FloatingSupportDock from './FloatingSupportDock';
import StructuredAnswer from './assistant/StructuredAnswer';
import {answerKinds,createAnswer,validateAnswer} from './assistant/assistant-model';
import {useHoldReorder} from './useHoldReorder';
const pendingContainer=el=>el.matches('tr')?el.cells[0]:el.closest('.cylinder-slot')||el;
const cards='[data-pending-key],.service-accordion-trigger,.flight-preferences,.flight-field,.flight-date-fares,.flight-airport-transfer,.flight-direction,.city-route-picker,.service-result,.hotel-map-card,.route-stop,.timeline-item,.guide-route-row,.preparation-card,.photo-card,.requirement-card,.preference-card,.intent-tray,.activity-card,.adopt-card,.journal-record,.transport-endpoints,.route-estimate-ticket,.route-alternatives button,.route-ticket-options>button,.service-filters,.trail-mosaic article';
function usePendingMarkers(todos,stage,markPending,notice){
 const latest=useRef({todos,stage});latest.current={todos,stage};
 useEffect(()=>{
  const phone=document.querySelector('.phone');if(!phone)return;
  const key=el=>{if(!el.dataset.pendingKey){const identity=el.getAttribute('aria-label')||el.dataset.candidateId||el.dataset.itemId||el.querySelector('h2,h3,strong,.date-clock-heading')?.textContent||el.classList[0];const peers=[...phone.querySelectorAll('.'+el.classList[0])];el.dataset.pendingKey=stage+':'+identity.trim().slice(0,100)+':'+Math.max(0,peers.indexOf(el));}return el.dataset.pendingKey;};
  const sync=()=>{for(const el of phone.querySelectorAll(cards)){if(el.closest('.flow-chat-sheet,.todo-sheet,.pending-warning'))continue;const source=key(el),count=latest.current.todos.filter(t=>!t.done&&t.source===source).length,container=pendingContainer(el);let badge=[...container.children].find(n=>n.classList.contains('pending-number'));el.classList.add('pending-host');if(getComputedStyle(el).position==='static')el.classList.add('pending-static');if(count){if(!badge){badge=document.createElement('span');badge.className='pending-number';badge.setAttribute('aria-label','待定项');container.append(badge);}if(badge.textContent!==String(count))badge.textContent=String(count);}else badge?.remove();}};
  const observer=new MutationObserver(sync);observer.observe(phone,{childList:true,subtree:true});sync();
  let hold=null,blocked=null,timer;
  const cancel=()=>{clearTimeout(timer);hold=null;};
  const start=e=>{cancel();if(e.pointerType==='mouse'&&e.button!==0||e.target.closest('input,textarea,select,[contenteditable],[data-reorder-handle],.aligned-select,.pending-number'))return;const host=e.target.closest(cards);if(!host||!phone.contains(host)||host.closest('.flow-chat-sheet,.todo-sheet,.pending-warning'))return;const control=e.target.closest('button,a');if(control&&control!==host&&host.querySelector('button')!==control&&!control.classList.contains('service-accordion-trigger'))return;cancel();hold={host,id:e.pointerId,x:e.clientX,y:e.clientY};timer=setTimeout(()=>{if(!hold||window.getSelection()?.toString().trim())return;const title=host.getAttribute('aria-label')||host.querySelector('h2,h3,strong')?.textContent||host.textContent;markPending(key(host),title.trim().slice(0,100));notice('已标记待定，可以在待办中处理');blocked={host,until:performance.now()+500};hold=null;},620);};
  const move=e=>{if(hold&&Math.hypot(e.clientX-hold.x,e.clientY-hold.y)>9)cancel();};
  const click=e=>{if(blocked&&performance.now()<blocked.until&&blocked.host.contains(e.target)){e.preventDefault();e.stopImmediatePropagation();blocked=null;}};
  const context=e=>{if(e.target.closest(cards))e.preventDefault();};
  const keyboard=e=>{if(e.altKey&&e.key.toLowerCase()==='p'){const host=e.target.closest(cards);if(host){e.preventDefault();markPending(key(host),host.getAttribute('aria-label')||host.querySelector('h2,h3,strong')?.textContent||host.textContent);notice('已标记待定');}}};
  phone.addEventListener('pointerdown',start,true);phone.addEventListener('click',click,true);phone.addEventListener('contextmenu',context);phone.addEventListener('keydown',keyboard);window.addEventListener('pointermove',move,{passive:true,capture:true});window.addEventListener('pointerup',cancel,true);window.addEventListener('pointercancel',cancel,true);window.addEventListener('blur',cancel);
  return()=>{cancel();observer.disconnect();phone.removeEventListener('pointerdown',start,true);phone.removeEventListener('click',click,true);phone.removeEventListener('contextmenu',context);phone.removeEventListener('keydown',keyboard);window.removeEventListener('pointermove',move,true);window.removeEventListener('pointerup',cancel,true);window.removeEventListener('pointercancel',cancel,true);window.removeEventListener('blur',cancel);};
 },[stage,markPending,notice]);
 useEffect(()=>{document.querySelectorAll('.pending-host').forEach(el=>{const container=pendingContainer(el),count=todos.filter(t=>!t.done&&t.source===el.dataset.pendingKey).length,old=[...container.children].find(n=>n.classList.contains('pending-number'));if(!count)old?.remove();else if(old)old.textContent=String(count);else{const badge=document.createElement('span');badge.className='pending-number';badge.setAttribute('aria-label','待定项');badge.textContent=String(count);container.append(badge);}});},[todos]);
}
function PhonePortal({children}){return createPortal(children,document.querySelector('.phone')||document.body);}
function TodoPanel({onClose}){
 const {todos,pendingCount,addTodo,toggleTodo,reorderTodos}=useTravel(),[adding,setAdding]=useState(false),[text,setText]=useState(''),drag=useHoldReorder(todos,reorderTodos),reduced=useReducedMotion();
 const add=e=>{e.preventDefault();if(text.trim()){addTodo(text.trim());setText('');setAdding(false);}};
 return <Sheet label="旅行待办" className="todo-sheet" slideFrom="right" onClose={onClose}><header className="todo-heading"><div><p className="eyebrow">BEFORE YOU GO</p><h2>还留着的小期待</h2><p>{pendingCount} 项待处理 · 拖动把手排序</p></div><button type="button" className="todo-add" aria-label="增加待办" aria-expanded={adding} onClick={()=>setAdding(!adding)}><Icon name={adding?'close':'plus'} size={20}/></button></header><AnimatePresence>{adding&&<motion.form className="todo-input" initial={reduced?false:{opacity:0,height:0}} animate={{opacity:1,height:'auto'}} exit={{opacity:0,height:0}} onSubmit={add}><FloatingField autoFocus maxLength={100} aria-label="待办内容" placeholder="还有什么要确认？" value={text} onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==='Escape'){e.stopPropagation();setAdding(false);}}}/><button type="submit" disabled={!text.trim()} aria-label="保存待办"><Icon name="check" size={19}/></button></motion.form>}</AnimatePresence><ul className="todo-list">{todos.map((item,i)=><motion.li layout key={item.id} ref={el=>{if(el)drag.refs.current.set(item.id,el);else drag.refs.current.delete(item.id);}} className={'glass todo-row'+(item.done?' is-done':'')+(drag.lift?.id===item.id?' is-held':'')} style={{'--todo-color':['#df91b0','#aea0d6','#75babe','#94b3d4','#e0b18f'][i%5],y:drag.lift?.id===item.id?drag.lift.y:0,zIndex:drag.lift?.id===item.id?2:1}} onPointerDown={e=>drag.start(e,item)} onTouchStart={e=>drag.start(e,item)} onKeyDown={e=>drag.keyDown(e,item)}><label><input type="checkbox" aria-label={'完成'+item.title} checked={item.done} onChange={()=>toggleTodo(item.id)}/><span className="todo-dot" aria-hidden="true">{item.done&&<Icon name="check" size={12}/>}</span><span className="todo-title"><span className="todo-label" title={item.title}>{item.title}</span><small>{item.source?'关联旅行卡片':'自己加的小事'}</small></span></label><button type="button" data-reorder-handle aria-label={'拖动'+item.title+'排序'}><Icon name="grip" size={17}/></button></motion.li>)}</ul>{!todos.length&&<p className="todo-empty">长按旅行卡片标记待定，也可以点 ＋ 留下一件小事。</p>}<span className="sr-only" role="status">{drag.announcement}</span></Sheet>;
}
function useChatHeight({open,engaged,messages,busy,quote,text,log,followLatest}){
 const [height,setHeight]=useState(480),grown=useRef(480),content=useRef(null),intro=useRef(null),composer=useRef(null),quoteElement=useRef(null),caption=useRef(null);
 useLayoutEffect(()=>{
  if(!open){grown.current=480;setHeight(480);return;}
  const phone=document.querySelector('.phone'),sheet=log.current?.closest('.flow-chat-sheet');if(!phone||!sheet)return;
  let frame;
  const outerHeight=element=>{if(!element)return 0;const style=getComputedStyle(element);return element.offsetHeight+(parseFloat(style.marginTop)||0)+(parseFloat(style.marginBottom)||0);};
  const measure=()=>{
   const bounds=phone.getBoundingClientRect(),scale=bounds.height/phone.clientHeight||1,viewport=window.visualViewport;
   const visibleBottom=Math.min(bounds.bottom,viewport?viewport.offsetTop+viewport.height:innerHeight);
   const available=Math.max(180,Math.min(phone.clientHeight-92,(visibleBottom-bounds.top)/scale-68));
   const rounds=messages.filter(message=>message.role==='user').length;
   const chrome=(engaged?64:32)+14+2+(engaged?0:outerHeight(intro.current))+outerHeight(quoteElement.current)+outerHeight(composer.current)+outerHeight(caption.current)+outerHeight(sheet.querySelector('.answer-kind-rail'))+18;
   grown.current=Math.max(grown.current,480+Math.min(rounds,4)*68,chrome+(content.current?.offsetHeight||0));
   setHeight(Math.min(grown.current,available));
   if(followLatest.current&&log.current)log.current.scrollTop=log.current.scrollHeight;
  };
  const schedule=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(measure);};
  const observer=new ResizeObserver(schedule);[phone,content.current,composer.current,quoteElement.current,log.current].filter(Boolean).forEach(element=>observer.observe(element));
  window.addEventListener('resize',schedule);window.visualViewport?.addEventListener('resize',schedule);window.visualViewport?.addEventListener('scroll',schedule);measure();
  return()=>{cancelAnimationFrame(frame);observer.disconnect();window.removeEventListener('resize',schedule);window.visualViewport?.removeEventListener('resize',schedule);window.visualViewport?.removeEventListener('scroll',schedule);};
 },[open,engaged,messages,busy,quote,text,log,followLatest]);
 return {height,content,intro,composer,quoteElement,caption};
}
export default function FlowSupport(){
 const {stage,saved,profile,setProfile,days,setEntries,reviseJournalDay,openServices,todos,pendingCount,markPending,todosOpen,setTodosOpen,pendingWarning,continueGeneration,closeWarning}=useTravel(),[notice,setNotice]=useState(''),[selection,setSelection]=useState(null),[chat,setChat]=useState(null),[quote,setQuote]=useState(''),[text,setText]=useState(''),[busy,setBusy]=useState(false),[composerActive,setComposerActive]=useState(false),followLatest=useRef(true),timer=useRef(null),bubble=useRef(null),log=useRef(null),reduced=useReducedMotion();
 const announce=useCallback(message=>setNotice(message),[]),closeChat=useCallback(()=>{setComposerActive(false);setChat(null);},[]),closeTodos=useCallback(()=>setTodosOpen(false),[setTodosOpen]);
 usePendingMarkers(todos,stage,markPending,announce);
 useEffect(()=>{if(!notice)return;const id=setTimeout(()=>setNotice(''),2500);return()=>clearTimeout(id);},[notice]);
 useEffect(()=>()=>clearTimeout(timer.current),[]);
 const openChat=useCallback((extract='',question='',origin)=>{setComposerActive(false);followLatest.current=true;setQuote(extract);setText(question);setSelection(null);setChat(origin||flightOrigin(bubble.current?.getClientRects().length?bubble.current:document.activeElement));window.getSelection()?.removeAllRanges();},[]);
 useEffect(()=>{const ask=e=>openChat(e.detail?.quote||'',e.detail?.question||'',e.detail?.origin);window.addEventListener('quantum-ask-ai',ask);return()=>window.removeEventListener('quantum-ask-ai',ask);},[openChat]);
 useEffect(()=>{setSelection(null);const change=()=>{if(chat||todosOpen)return;const s=window.getSelection();if(!s?.rangeCount||s.isCollapsed||!s.toString().trim()){setSelection(null);return;}const range=s.getRangeAt(0),start=range.startContainer.parentElement,end=range.endContainer.parentElement,phone=document.querySelector('.phone');if(!phone?.contains(start)||!phone.contains(end)||start.closest('input,textarea,[contenteditable],[data-reader-block],.flow-chat-sheet,.todo-sheet')){setSelection(null);return;}const rect=range.getBoundingClientRect(),bounds=phone.getBoundingClientRect();setSelection({quote:s.toString().slice(0,1600),x:Math.max(12,Math.min(bounds.width-145,rect.left-bounds.left)),y:Math.max(55,Math.min(bounds.height-100,rect.top-bounds.top-46))});};document.addEventListener('selectionchange',change);return()=>document.removeEventListener('selectionchange',change);},[stage,chat,todosOpen]);
 const live=useRef({profile,days});live.current={profile,days};
 const messages=Array.isArray(profile.flowChat)?profile.flowChat:[];
 const engaged=composerActive||!!text.trim()||messages.length>0||busy,chatLayout=useChatHeight({open:!!chat,engaged,messages,busy,quote,text,log,followLatest});
 useLayoutEffect(()=>{if(followLatest.current&&log.current)log.current.scrollTop=log.current.scrollHeight;},[messages,busy,chat]);
 const patchCard=card=>setProfile(prev=>({...prev,flowChat:(prev.flowChat||[]).map(message=>message.card?.id===card.id?{...message,card}:message)}));
 const editCard=card=>{const existing=live.current.profile.flowChat?.find(message=>message.card?.id===card.id)?.card;if(existing?.status==='applied')return;patchCard(card);};

 const request=async(question,extract=quote||profile.destination+' · '+profile.dates)=>{
  if(!question.trim()||busy)return;followLatest.current=true;setProfile(prev=>({...prev,flowChat:[...(prev.flowChat||[]),{role:'user',text:question.trim(),quote:extract}].slice(-80)}));setText('');setBusy(true);const generation=runtime.generation;
  try{const result=await invoke('ask',{question:question.trim(),quote:extract});if(runtime.generation!==generation)return;const current=live.current,day=current.days.find(d=>extract.includes(d.place))||current.days[0];const card=day&&!result.hasActions?createAnswer({question,quote:extract,day,days:current.days,profile:current.profile}):null;if(card){card.values.note=result.answer||'';card.answer=result.answer||'';}setProfile(prev=>({...prev,flowChat:[...(prev.flowChat||[]),{role:'assistant',text:result.answer||'未收到回答，请重试。',card,hasActions:result.hasActions}].slice(-80)}));}
  catch(error){setNotice(errorMessage(error));}finally{setBusy(false);}
 };
 const send=e=>{e.preventDefault();request(text.trim());};
 const regenerate=card=>request(card.question,card.quote);
 const applyCard=card=>{
  const existing=live.current.profile.flowChat?.find(m=>m.card?.id===card.id)?.card;if(existing?.status==='applied'||existing?.status==='applying')return;
  const source=live.current.days.find(d=>String(d.id)===String(card.dayId)),error=validateAnswer(card,card.values,source);
  if(error){patchCard({...card,status:'failed',error});return;}
  patchCard({...card,status:'applying',error:''});
  Promise.resolve().then(()=>{
   const current=live.current,day=current.days.find(d=>String(d.id)===String(card.dayId)),values=card.values,validation=validateAnswer(card,values,day);
   if(validation){patchCard({...card,status:'failed',error:validation});return;}
   let result='',failure='';
   if(card.kind==='schedule'){
    const items=day.items.map((item,index)=>index===Number(values.itemIndex)?{...item,time:values.time}:item);
    failure=reviseJournalDay(day.id,items,{source:'旅行建议确认',reason:card.question});result=day.items[Number(values.itemIndex)]?.title+' 已调整到 '+values.time+'。';
   }else if(card.kind==='party'){
    setProfile(prev=>({...prev,count:Number(values.count)+'人',requirements:values.automatic&&prev.requirements?{...prev.requirements,count:Number(values.count)}:prev.requirements}));result='同行人数已更新为 '+values.count+' 人。';
   }else if(card.kind==='weather'){
    setProfile(prev=>({...prev,assistantWeather:{...prev.assistantWeather,[day.id]:{temperature:Number(values.temperature),condition:values.condition,at:Date.now(),source:'用户确认'}}}));result=day.date+' · '+values.temperature+'° · '+values.condition+' 已存入当天日记。';
   }else if(['flight','hotel'].includes(card.kind)){
    setProfile(prev=>({...prev,bookingRequests:[...(prev.bookingRequests||[]),{id:card.id,kind:card.kind,dayId:day.id,count:Number(values.count),roomCount:card.kind==='hotel'?Number(values.roomCount):undefined,date:day.date,state:'待选择',at:Date.now()}]}));markPending('assistant-booking:'+card.id,day.place+' · '+(card.kind==='hotel'?'选择酒店':'选择航班')+' · '+values.count+'人');result='预订需求已加入待办，班次或酒店等待选择。';
   }else{
    const note=String(values.note).trim(),record={id:'assistant-'+card.id,text:note,dayId:day.id,media:[],at:Date.now(),source:'旅行建议确认'};
    setProfile(prev=>({...prev,journalRecords:{...prev.journalRecords,[day.id]:[...(prev.journalRecords?.[day.id]||[]),record]}}));setEntries(prev=>({...prev,[day.id]:[prev[day.id],note].filter(Boolean).join('\n\n')}));result='文字已收进 '+day.date+' 的旅行记录，原记录继续保留。';
   }
   patchCard({...card,status:failure?'failed':'applied',error:failure,result:failure?'':result});
  });
 };
 const openCardService=(kind,id)=>{closeChat();openServices(kind,id);};
 const visible=!['workflow','portal','generating','chat'].includes(stage);
 return <>{visible&&<FloatingSupportDock stage={stage} pendingCount={pendingCount} triggerRef={bubble} blocked={!!chat||todosOpen||!!pendingWarning} onTodo={()=>setTodosOpen(true)} onChat={origin=>openChat('','',origin)} confirmation={stage==='guide'?(saved?'翻开旅行手记':'生成旅行笔记'):undefined} onConfirm={()=>window.dispatchEvent(new Event('quantum-guide-confirm'))}/>}{notice&&<div className="flow-notice" role="status">{notice}</div>}{selection&&<div className="flow-selection glass" role="toolbar" aria-label="流程选文操作" style={{left:selection.x,top:selection.y}} onPointerDown={e=>e.preventDefault()}><button type="button" onClick={()=>openChat(selection.quote)}>选中问 AI<Icon name="spark" size={14}/></button></div>}<AnimatePresence>{chat&&<FlyingPanel origin={chat} label="旅行AI建议" flyHeight={chatLayout.height} className={"flow-chat-sheet"+(engaged?" is-chatting":"")} onClose={closeChat}><motion.header className="flow-chat-intro" aria-hidden={engaged||undefined} initial={false} animate={{height:engaged?0:"auto",opacity:engaged?0:1,y:engaged?-8:0}} transition={reduced?{duration:0}:{height:{duration:.28,ease:[.2,.8,.2,1]},opacity:{duration:.18},y:{duration:.28}}}><div ref={chatLayout.intro} className="flow-chat-intro-copy"><p className="eyebrow">A LITTLE HELP ALONG THE WAY</p><h2>一起想想，怎样更合适。</h2></div></motion.header>{quote&&<blockquote ref={chatLayout.quoteElement} className="flow-chat-quote" tabIndex={0}>{quote}</blockquote>}<div ref={log} className="flow-chat-log" role="log" tabIndex={0} aria-label="旅行建议对话" onScroll={e=>{const element=e.currentTarget;followLatest.current=element.scrollHeight-element.scrollTop-element.clientHeight<36;}}><div ref={chatLayout.content} className="flow-chat-messages">{!messages.length&&<div className="glass mini-chat">说说你想调整什么，我把需要确认的字段放在卡片里。</div>}{messages.map((m,i)=><div key={i} className={'glass mini-chat '+m.role}>{m.quote&&<small tabIndex={0}>{m.quote}</small>}{m.card?<StructuredAnswer card={m.card} day={days.find(d=>String(d.id)===String(m.card.dayId))||days[0]} days={days} onChange={editCard} onApply={applyCard} onRegenerate={regenerate} onOpenService={openCardService}/>:m.text}{m.hasActions&&<button type="button" onClick={()=>invoke('tab',{tag:0})}>在首页查看待确认操作</button>}</div>)}{busy&&<div className="flow-ai-thinking" role="status"><TravelThinkingOrb/><span>梳理这一段旅行</span></div>}</div></div><div className="answer-kind-rail" aria-label="建议卡片类型">{answerKinds.map(([id,label,icon,prompt])=><button type="button" key={id} disabled={busy} onClick={()=>request(prompt)}><Icon name={icon} size={13}/>{label}</button>)}</div><div ref={chatLayout.composer} className="flow-chat-compose" onFocusCapture={()=>setComposerActive(true)} onBlurCapture={e=>{if(!e.currentTarget.contains(e.relatedTarget))setComposerActive(false);}}><TravelComposer drawer label="旅行建议问题" sendLabel="发送旅行建议问题" value={text} onChange={e=>setText(e.target.value)} onSubmit={send} disabled={busy} placeholder="这些安排怎样衔接更好？"/></div></FlyingPanel>}{todosOpen&&<PhonePortal key="todos"><TodoPanel onClose={closeTodos}/></PhonePortal>}{pendingWarning&&<PhonePortal key="warning"><Sheet label="还有待定安排" className="pending-warning" onClose={closeWarning}><p className="eyebrow">ONE MORE LOOK</p><h2>还有 {pendingCount} 件事，等你拿主意。</h2><p>先看一眼待办，或保留这些待定安排继续生成。</p><Primary onClick={()=>{closeWarning();setTodosOpen(true);}}>查看待办</Primary><button type="button" className="pending-continue" onClick={continueGeneration}>保留待定，继续生成</button></Sheet></PhonePortal>}</AnimatePresence></>;
}
