import React,{useState,useEffect,useRef} from 'react';
import {runtime} from '../production/runtime';
import {AnimatePresence,motion} from 'motion/react';
import TravelThinkingOrb from '../components/TravelThinkingOrb';
import {useTravel} from '../TravelContext';
import {TopBar,spring,Icon,Sheet,Primary} from '../components/UI';
import FloatingField from '../components/FloatingField';
import TravelComposer from '../components/TravelComposer';
import RequirementCards from '../components/RequirementCards';
import {seedRequirements,destinationFrom,mergeRequirementText,deferRequirements,profileFromRequirements} from '../components/travel-requirements';
const question='你想去哪里？';
export default function Chat(){
 const {setStage,message,setMessage,profile,setProfile,confirmRequirements,showDiscovery}=useTravel();
 const [phase,setPhase]=useState(profile.requirements?'refining':'typing'),[typed,setTyped]=useState(profile.requirements?question:''),[input,setInput]=useState(''),[noteOpen,setNoteOpen]=useState(false),[note,setNote]=useState('');
 const step=profile.refinementStep||0,draft=profile.requirements,scroll=useRef(null);
 const request=useRef(0),history=useRef([]),[summary,setSummary]=useState(profile.conversationSummary||''),[nextQuestion,setNextQuestion]=useState('');
 useEffect(()=>()=>{request.current++;},[]);
 useEffect(()=>{if(phase!=='typing')return;const ids=question.split('').map((_,i)=>setTimeout(()=>setTyped(question.slice(0,i+1)),200+i*85));ids.push(setTimeout(()=>setPhase('ready'),1100));return()=>ids.forEach(clearTimeout);},[phase]);
 const changeDraft=next=>setProfile(prev=>({...prev,requirements:next,requirementsConfirmed:false}));
 const changeStep=next=>{setProfile(prev=>({...prev,refinementStep:next}));scroll.current?.scrollTo({top:0,behavior:'instant'});};
 const submit=async e=>{
  e.preventDefault();const text=input.trim();if(!text||!['ready','refining'].includes(phase))return;
  const initial=phase==='ready',nextDraft=initial?seedRequirements(text):mergeRequirementText(draft,text),nextProfile={...profile,...(initial?{original:text,destination:destinationFrom(text),refinementStep:0}:{}),requirements:nextDraft,requirementsConfirmed:false};
  if(initial)setMessage(text);setProfile(nextProfile);
  history.current.push({role:'user',text});const serial=++request.current;
  setInput('');
  setPhase('thinking');
  try{const result=await runtime.converge(nextProfile,initial?text:message,history.current);if(serial!==request.current)return;
    setSummary(result.summary);setNextQuestion(result.question);history.current.push({role:'assistant',text:result.question||result.summary});
    if(result.ready){const ready=[0,1,2].reduce((value,i)=>deferRequirements(value,i),nextDraft);await showDiscovery({...profileFromRequirements(nextProfile,ready),conversationSummary:result.summary});}
    else{setProfile(prev=>({...prev,conversationSummary:result.summary}));setPhase('refining');}
  }catch(error){if(serial===request.current){runtime.publish({error:error.message});setPhase('refining');}}
 };
 const complete=async()=>{const ready=[0,1,2].reduce((value,i)=>deferRequirements(value,i),draft);confirmRequirements(ready);setPhase('thinking');try{await showDiscovery(profileFromRequirements(profile,ready));}catch{setPhase('refining');}};
 return <section className={'chat-screen phase-'+phase}><TopBar title="旅行空间" onBack={()=>setStage('workflow')}/><div className="chat-geometry">
  <div className="chat-scroll" ref={scroll}>
   <motion.div layout layoutId="question-glass" className={'glass question '+(phase==='typing'?'question-large':phase==='folding'?'question-drawer':'question-small')} transition={spring}><div className="question-mark"><TravelThinkingOrb size={20}/></div><div><p>{phase==='refining'?(nextQuestion||'再聊聊，你想怎么旅行。'):typed}<span className={phase==='typing'?'type-caret':'hidden'}/></p>{phase==='typing'&&<span className="question-sub">一个目的地，就可以开始。</span>}</div></motion.div>
   <AnimatePresence>{draft&&message&&phase!=='typing'&&phase!=='ready'&&<motion.div className="glass user-bubble" initial={{y:50,scale:.9,opacity:0}} animate={phase==='folding'?{scale:.05,opacity:0}:{y:0,scale:1,opacity:1}} transition={spring}><p>{message}</p></motion.div>}</AnimatePresence>
   {phase==='refining'&&draft&&<>{summary&&<div className="glass travel-conversation-summary"><small>先把想法记下来</small><p>{summary}</p></div>}<RequirementCards draft={draft} onChange={changeDraft} step={step} onStep={changeStep} onComplete={complete}/><div className="chat-note-entry"><button type="button" aria-label="补充旅行备注" onClick={()=>setNoteOpen(true)}><Icon name="edit" size={18}/></button></div>{draft.notes.length>0&&<div className="chat-kept-note" role="status"><span>也记下了</span><p>{draft.notes.at(-1)}</p></div>}</>}
   <AnimatePresence>{phase==='thinking'&&<motion.div className="thinking-center" role="status" aria-label="正在思考旅行灵感" initial={{opacity:0,scale:.5}} animate={{opacity:1,scale:1}} exit={{opacity:0,scale:.4}}><TravelThinkingOrb/><p>按你的选择，寻找旅行灵感</p></motion.div>}</AnimatePresence>
  </div>

  <AnimatePresence>{['ready','refining'].includes(phase)&&<TravelComposer label="旅行想法" sendLabel="发送旅行想法" placeholder={phase==='refining'?'也可以直接说，还有什么想法…':'想去哪里？'} value={input} onChange={e=>setInput(e.target.value)} onSubmit={submit} disabled={phase==='thinking'}/>}</AnimatePresence>
 </div><AnimatePresence>{noteOpen&&<Sheet label="旅行备注" className="travel-note-sheet" onClose={()=>setNoteOpen(false)}><h2>补充一句备注</h2><FloatingField as="textarea" rows={3} label="旅行备注" aria-label="旅行备注内容" value={note} onChange={e=>setNote(e.target.value)} maxLength={1200}/><Primary disabled={!note.trim()} icon="check" onClick={()=>{changeDraft(mergeRequirementText(draft,note.trim()));setNote('');setNoteOpen(false);}}>保存备注</Primary></Sheet>}</AnimatePresence></section>;
}
