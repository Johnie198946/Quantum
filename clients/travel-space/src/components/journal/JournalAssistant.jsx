import React,{useLayoutEffect,useRef,useState} from 'react';
import {AnimatePresence,motion,useReducedMotion} from 'motion/react';
import {Sheet,spring} from '../UI';
import {useTravel} from '../../TravelContext';
import LiquidNav from '../LiquidNav';
import ReaderAnnotations from './ReaderAnnotations';
import JournalAnnotationsPage from './JournalAnnotationsPage';
import JournalArrangePage from './JournalArrangePage';
import './revision68-adopt.css';

const modes=[['notes','阅读与批注','book'],['itinerary','调整行程','sliders']];
export default function JournalAssistant({day,initialMode='notes',onClose,revealFrom,burst=false}){
 const {profile,entries,days}=useTravel(),root=useRef(null),reduced=useReducedMotion();
 const [mode,setMode]=useState(initialMode),[direction,setDirection]=useState(1),[readerDayId,setReaderDayId]=useState(day.id),[showNotes,setShowNotes]=useState(false),[node,setNode]=useState(null),[height,setHeight]=useState(null);
 const current=days.find(item=>item.id===day.id)||day,readerDay=days.find(item=>item.id===readerDayId)||current;
 useLayoutEffect(()=>{if(!node)return;const measure=()=>setHeight(node.offsetHeight);const observer=new ResizeObserver(measure);observer.observe(node);measure();return()=>observer.disconnect();},[node]);
 const switchMode=next=>{if(next===mode)return;setDirection(next==='itinerary'?1:-1);setMode(next);setShowNotes(false);};
 return <Sheet label="与AI沟通旅行手记" onClose={onClose} className={'journal-workbench journal-assistant revision68-journal-assistant'+(burst?' orb-chat':'')} revealFrom={revealFrom} burst={burst}><div ref={root} className="journal-assistant-reading-root" data-reader-scope="assistant"><header className="journal-assistant-heading"><p className="journal-kicker">MARGIN / MOMENT / JOURNEY</p><h2>留一点想法，<br/>给这一天。</h2><p>{current.date} · {current.place}</p></header><LiquidNav className="journal-chat-modes" label="手记协作方式" items={modes} value={mode} onChange={switchMode}/><motion.div className="journal-mode-window" initial={false} animate={{height:height??'auto'}} transition={reduced?{duration:0}:spring}><AnimatePresence initial={false} mode="wait" custom={direction}><motion.div key={mode} ref={setNode} className="journal-mode-content" custom={direction} variants={{enter:dir=>({x:reduced?0:dir*40,opacity:reduced?1:0}),shown:{x:0,opacity:1},leave:dir=>({x:reduced?0:-dir*40,opacity:reduced?1:0})}} initial="enter" animate="shown" exit="leave" transition={reduced?{duration:0}:{duration:.22,ease:[.2,.8,.2,1]}}>{mode==='notes'?<JournalAnnotationsPage day={readerDay} days={days} profile={profile} entries={entries} onDay={setReaderDayId} onList={()=>setShowNotes(true)}/>:<JournalArrangePage day={current}/>}</motion.div></AnimatePresence></motion.div><ReaderAnnotations root={root} day={readerDay} showList={showNotes} onClose={()=>setShowNotes(false)} onJump={id=>{setReaderDayId(id);switchMode('notes');}}/></div></Sheet>;
}
