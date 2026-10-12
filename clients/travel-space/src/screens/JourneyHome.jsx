import React,{useState} from 'react';
import {AnimatePresence,motion,useReducedMotion} from 'motion/react';
import {useTravel} from '../TravelContext';
import {TopBar,Icon,Sheet,Primary,spring} from '../components/UI';
import {flightOrigin} from '../components/FlyingPanel';
import BeforePage from '../components/lifecycle/BeforePage';
import TodayPage from '../components/lifecycle/TodayPage';
import TripReview from '../components/lifecycle/TripReview';
import ChangeSheet from '../components/lifecycle/ChangeSheet';
import RecordSheet from '../components/lifecycle/RecordSheet';
import BudgetPanel from '../components/budget/BudgetPanel';
import {normalizeSession,summaryFacts} from '../components/lifecycle/trip-model';
import '../components/lifecycle/lifecycle.css';
import '../components/lifecycle/revision68-lifecycle.css';

const phases=[['before','出发前'],['during','在路上'],['after','回来后']];
export default function JourneyHome(){
 const {profile,days,setStage,openNotebook,beginJourney,endJourney,recordJourneyProgress,setJourneyDay}=useTravel(),session=normalizeSession(profile,days),facts=summaryFacts(profile,days),reduced=useReducedMotion();
 const [phase,setPhase]=useState(()=>({today:'during',review:'after',trip:session.phase})[new URLSearchParams(location.search).get('view')]||session.phase),[panel,setPanel]=useState(null),[error,setError]=useState('');
 const [transitioning,setTransitioning]=useState(false);
 const begin=async()=>{if(transitioning)return;setTransitioning(true);try{const message=await beginJourney();if(message)setError(message);else{setPhase('during');setError('');}}finally{setTransitioning(false);}};
 const openPanel=value=>setPanel({...value,instance:crypto.randomUUID()});
 const budget=(tab='账目')=>openPanel({kind:'budget',tab:typeof tab==='string'?tab:'账目'});
 const activeDay=days.find(d=>String(d.id)===String(session.activeDayId))||days[0];
 const record=(day=activeDay,action)=>openPanel({kind:'record',day:day?.items?day:days.find(d=>String(d.id)===String(day))||activeDay,action});
 const progress=async(day,action,status)=>{if(transitioning)return;setTransitioning(true);try{const message=await recordJourneyProgress(day,action,status);setError(message||'');}finally{setTransitioning(false);}};
 const notebook=()=>openNotebook('trip',{view:'diary',dayId:activeDay?.id});
 return <section className="paper-screen journey-screen"><TopBar title={profile.destination+' · 这趟旅行'} onBack={()=>setStage('notebook')}><button className="icon-btn" aria-label="打开旅行手记" onClick={notebook}><Icon name="book" size={18}/></button></TopBar>
  <nav className="lifecycle-phase-tabs" aria-label="旅行阶段">{phases.map(([value,label])=><button key={value} aria-pressed={phase===value} onClick={()=>{setPhase(value);setError('');}}>{phase===value&&<motion.span className="lifecycle-phase-pill" layoutId="lifecycle-phase" transition={reduced?{duration:0}:spring}/>}<span>{label}</span></button>)}</nav>
  {error&&<p className="lifecycle-error" role="alert">{error}</p>}
  <div className="paper-scroll lifecycle-scroll"><AnimatePresence mode="wait" initial={false}><motion.div key={phase} initial={reduced?false:{opacity:0,x:12}} animate={{opacity:1,x:0}} exit={{opacity:0,x:-12}} transition={{duration:reduced?0:.18}}>
   {phase==='before'&&<BeforePage busy={transitioning} onBegin={begin} onPlan={()=>setStage('route')} onNotebook={notebook} onBudget={()=>budget('设置')}/>}
   {phase==='during'&&<TodayPage onBegin={begin} onRecord={record} onChange={(day=activeDay,action)=>openPanel({kind:'change',day,action})} onBudget={budget} onEnd={()=>openPanel({kind:'finish'})} onPlan={notebook} onProgress={progress} onDayChange={setJourneyDay}/>}
   {phase==='after'&&<TripReview onBudget={budget} onRecord={record}/>}
  </motion.div></AnimatePresence></div>
  <AnimatePresence>
   {panel?.kind==='record'&&<RecordSheet key={'record-'+panel.instance} {...panel} onClose={()=>setPanel(null)}/>}
   {panel?.kind==='change'&&<ChangeSheet key={'change-'+panel.instance} {...panel} onClose={()=>setPanel(null)}/>}
   {panel?.kind==='budget'&&<Sheet key={'budget-'+panel.instance} label="旅行账本" onClose={()=>setPanel(null)} className="lifecycle-budget-sheet"><BudgetPanel initialTab={panel.tab}/></Sheet>}
   {panel?.kind==='finish'&&<Sheet key={'finish-'+panel.instance} label="结束这趟旅行" onClose={()=>setPanel(null)} className="lifecycle-finish-sheet"><p className="eyebrow">AFTER THE JOURNEY</p><h2>带着这些日子，<br/>回到生活里。</h2><p>实际完成 {facts.completed} / {facts.total} 项 · 留下 {facts.records} 条记录</p>{facts.unfinished>0&&<p className="lifecycle-hint">还有 {facts.unfinished} 项未完成，会按原状态保留。</p>}<p className="lifecycle-hint">下一步写回顾、核对实际花费并分账。结束旅程后仍可补充笔记和账目。</p>{error&&<p className="lifecycle-error" role="alert">{error}</p>}<Primary icon="check" disabled={transitioning} onClick={async()=>{if(transitioning)return;setTransitioning(true);try{const message=await endJourney();if(message)setError(message);else{setPanel(null);setPhase('after');}}finally{setTransitioning(false);}}}>确认结束旅程</Primary></Sheet>}
  </AnimatePresence>
 </section>;
}
export function JourneyLink(){const {profile,days,setStage}=useTravel(),session=normalizeSession(profile,days);return <button className="glass lifecycle-entry-link" aria-label="打开这趟旅行" onClick={event=>setStage('trip',{fromCard:flightOrigin(event.currentTarget)})}><Icon name={session.phase==='after'?'leaf':session.phase==='during'?'pin':'calendar'} size={20}/><span><strong>{session.phase==='after'?'回顾这趟旅行':session.phase==='during'?'继续今天的旅程':'出发前 · 带上这份手记'}</strong><small>{session.phase==='after'?'写总结、核对花费与分账':session.phase==='during'?'跟着安排玩，随手记下变化':'确认准备，再开始实际游玩'}</small></span><Icon name="chevron" size={15}/></button>;}
