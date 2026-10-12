import React,{useEffect} from 'react';
import RuntimePanel,{useRuntime} from './production/RuntimePanel';
import {runtime} from './production/runtime';
import { AnimatePresence, LayoutGroup, MotionConfig, motion, useIsPresent } from 'motion/react';
import { useTravel } from './TravelContext';
import { stages } from './data';
import { Space } from './components/Space';
import { Icon,useConfirmationGlow } from './components/UI';
import { WorkflowEntry } from './screens/Entry';
import Chat from './screens/Chat';
import Discover from './screens/Discover';
import Preferences from './screens/Preferences';
import Route from './screens/Route';
import FlowSupport from './components/FlowSupport';
import Services from './screens/Services';
import Generating from './screens/Generating';
import CardPageUnfold from './components/CardPageUnfold';
import OrbPageUnfold from './components/OrbPageUnfold';
import Adopt from './screens/Adopt';
import JourneyHome from './screens/JourneyHome';
import { Guide, Notebook } from './screens/Notebook';
const screenMap={trip:JourneyHome,services:Services,workflow:WorkflowEntry,chat:Chat,discover:Discover,preferences:Preferences,route:Route,generating:Generating,adopt:Adopt,guide:Guide,notebook:Notebook};
function StageFrame({children,arrival,onArrivalComplete}) {
  const present=useIsPresent();
  return <motion.div className="screen-host" aria-hidden={present?undefined:true} inert={present?undefined:''}
    style={{pointerEvents:present?'auto':'none'}} initial={{opacity:arrival?1:0}} animate={{opacity:1}}
    variants={{leave:fromOrb=>fromOrb?{opacity:0,transition:{duration:.08}}:{opacity:0,filter:'blur(10px)',scale:.94,transition:{duration:.38}}}}
    exit="leave" transition={{duration:.38}}>
    {arrival?.fromCard?<CardPageUnfold origin={arrival.origin} onComplete={()=>onArrivalComplete(arrival.token)}>{children}</CardPageUnfold>:arrival?.stage==='guide'?<OrbPageUnfold onComplete={()=>onArrivalComplete(arrival.token)}>{children}</OrbPageUnfold>:children}
  </motion.div>;
}
export default function App(){
  useConfirmationGlow();
  const {stage,setStage,reset,selected,orbArrival,finishOrbArrival,storageAvailable}=useTravel();
  const Screen=screenMap[stage]||WorkflowEntry;
  const current=stages.find(x=>x.id===stage);
  const paper=stage==='guide'||stage==='notebook'||stage==='services'||stage==='trip';
  const live=useRuntime();
  useEffect(()=>{runtime.boot();return()=>runtime.stop();},[]);
  useEffect(()=>{const open=e=>{if(typeof e.detail?.workflowId==='string')runtime.route(e.detail.workflowId);};window.addEventListener('quantum-open-workflow',open);window.__quantumWorkflowReady=true;return()=>{window.__quantumWorkflowReady=false;window.removeEventListener('quantum-open-workflow',open);};},[]);
  return <MotionConfig reducedMotion="user"><LayoutGroup><div className={'phone '+(paper?'paper-phone':'')} data-stage={stage} data-theme="light">
    <Space tunnel={stage==='portal'} active={!paper}/><AnimatePresence mode="sync" initial={false} custom={!!orbArrival}><StageFrame key={stage} arrival={orbArrival} onArrivalComplete={finishOrbArrival}><Screen/></StageFrame></AnimatePresence>
    <FlowSupport/><RuntimePanel/>{stage!=='workflow'&&<span className="production-sync" role="status">{live.sync}</span>}
  </div></LayoutGroup></MotionConfig>;
}
