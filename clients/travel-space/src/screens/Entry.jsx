import React, { useState, useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useTravel } from '../TravelContext';
import { Icon, BottomTabs, TopBar, Primary, spring } from '../components/UI';
import {images} from '../data';
import MagazineCarousel from '../components/MagazineCarousel';
import {runtime} from '../production/runtime';
import {useRuntime} from '../production/RuntimePanel';
import {statusLabel} from '../production/TaskPages';
export function WorkflowEntry() {
  const { setStage,reset,message,profile,saved,savedTrip,resumeSavedTrip,storageAvailable } = useTravel();
  const [rootTab,setRootTab]=useState(2);
  const live=useRuntime();
  const [expanded,setExpanded]=useState(false),idle=useRef(null);
  useEffect(()=>{clearTimeout(idle.current);if(expanded)idle.current=setTimeout(()=>setExpanded(false),5000);return()=>clearTimeout(idle.current);},[expanded]);
  return <section className="workflow-screen">
    <button type="button" className="workflow-other-tasks text-btn" onClick={()=>runtime.call('openTasks').catch(error=>runtime.publish({error:error.message}))}>全部任务<Icon name="chevron" size={12}/></button>
    <button type="button" className="workflow-photo-entry icon-btn glass" aria-label="照片处理" onClick={()=>runtime.call('photoStudio').catch(error=>runtime.publish({error:error.message}))}><Icon name="image" size={19}/></button>
    <header className="workflow-heading"><p className="eyebrow">QUANTUM</p><h1>让想去的地方<br />变成一段旅程</h1><p>从一个想法，开始。</p></header>
    <motion.button layoutId="travel-seed" className={'glass new-task-btn '+(expanded?'expanded':'')} aria-label="新建任务" aria-expanded={expanded} disabled={live.loading} onClick={()=>{reset();setStage('chat');}} animate={{width:expanded?132:48}} transition={spring}><Icon name="plus"/><AnimatePresence>{expanded&&<motion.span initial={{opacity:0,x:8}} animate={{opacity:1,x:0}} exit={{opacity:0,x:8}}>新建任务</motion.span>}</AnimatePresence></motion.button>
    {rootTab===0||rootTab===2?<><MagazineCarousel paused={expanded}/></>:<div className="root-content glass" key={rootTab}>
      <p className="eyebrow">{rootTab===1?'YOUR JOURNAL':'YOUR TRAVEL SPACE'}</p><h2>{rootTab===1?'把旅程，留在这里。':'按自己的节奏出发。'}</h2>
      {rootTab===1?(savedTrip?<><figure><img src={images[savedTrip.notebookConfig.cover]} alt="旅行手记封面"/><figcaption>{savedTrip.profile.destination}</figcaption></figure><h3>{savedTrip.noteTitle}</h3><p>{savedTrip.profile.dates} · {savedTrip.profile.count}</p><Primary onClick={resumeSavedTrip}>翻开旅行手记</Primary></>:<><p className="root-empty">写下想去的地方，把行程收进第一本旅行手记。</p><button className="root-action" onClick={()=>{reset();setStage('portal');}}>开始一段旅行<Icon name="plus" size={16}/></button></>):<><p className="root-empty">{message?profile.destination+' · '+profile.count+' · '+profile.pace:'还没有定下下一次出发。'}</p>{message&&<button className="root-action" onClick={()=>setStage('chat')}>修改旅行想法<Icon name="edit" size={16}/></button>}<p className="root-local">旅行草稿与手记保存在这台设备的当前浏览器。</p></>}
      {!storageAvailable&&<p role="status">当前浏览器无法保存，请从行程菜单导出 JSON 留存。</p>}
    </div>}
    <div className="production-workflows" role="group" aria-label="当前对话的任务">{live.workflows.filter(w=>w.uiKind!=='archive').map(w=><button key={w.id} onClick={()=>runtime.open(w.id)}><strong>{w.title}</strong><small>{statusLabel(w.latestExecution?.status||w.status)}</small></button>)}</div>
  </section>;
}
