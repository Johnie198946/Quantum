import React,{useState,useRef,useEffect} from 'react';
import {motion,AnimatePresence} from 'motion/react';
import {requestProposal} from '../production/proposals';
import TravelComposer from './TravelComposer';
import TravelThinkingOrb from './TravelThinkingOrb';
import {Icon,Primary,spring} from './UI';
export default function ExtraCardAssistant({onFill}){
 const [open,setOpen]=useState(false),[text,setText]=useState(''),[messages,setMessages]=useState([]),[proposal,setProposal]=useState(null),[busy,setBusy]=useState(false),timer=useRef(null),log=useRef(null);
 useEffect(()=>()=>clearTimeout(timer.current),[]);useEffect(()=>{log.current?.scrollTo({top:log.current.scrollHeight,behavior:'smooth'});},[messages,busy]);
 const send=async e=>{e.preventDefault();const request=text.trim();if(!request||busy)return;setMessages(prev=>[...prev,{role:'user',text:request}]);setText('');setProposal(null);setBusy(true);try{
 const value=await requestProposal('把这段旅行想法整理为一张补充卡片：'+request,{original:request},'title,text');
 if(typeof value.title!=='string'||typeof value.text!=='string'||!value.title.trim()||!value.text.trim())throw new Error('请补充想法后再整理。');
 setProposal({title:value.title.slice(0,80),text:value.text.slice(0,2000)});setMessages(prev=>[...prev,{role:'assistant',text:value.text}]);
 }catch(error){setMessages(prev=>[...prev,{role:'assistant',text:error.message}]);}finally{setBusy(false);}};

 return <section className="extra-card-assistant" aria-label="AI梳理旅行卡片"><button type="button" className="glass extra-chat-toggle" aria-label="与AI梳理卡片" aria-expanded={open} onClick={()=>setOpen(!open)}><Icon name="thought" size={18}/><span>聊聊想法</span></button><AnimatePresence>{open&&<motion.div className="extra-chat-content" initial={{opacity:0,y:8}} animate={{opacity:1,y:0}} exit={{opacity:0,y:8}} transition={spring}><div ref={log} className="extra-chat-log" role="log" aria-label="卡片整理对话"><div className="glass mini-chat">还有什么想留给这趟旅行？说说期待，我帮你整理。</div>{messages.map((m,i)=><motion.div key={i} className={'glass mini-chat '+m.role} initial={{y:12,opacity:0}} animate={{y:0,opacity:1}} transition={spring}>{m.text}</motion.div>)}{busy&&<div className="extra-chat-thinking" role="status"><TravelThinkingOrb/><span>整理你的想法</span></div>}</div>{proposal&&<div className="extra-proposal"><strong>{proposal.title}</strong><Primary icon="check" onClick={()=>{onFill(proposal);setProposal(null);setMessages(prev=>[...prev,{role:'assistant',text:'已经填入卡片，检查后再保存。'}]);}}>填入卡片</Primary></div>}<TravelComposer drawer label="卡片整理想法" sendLabel="发送卡片整理想法" placeholder="例如：温泉多住一晚，别太赶路…" value={text} onChange={e=>setText(e.target.value)} onSubmit={send} disabled={busy}/><p className="extra-ai-caption">填入前检查整理结果，再由你确认</p></motion.div>}</AnimatePresence></section>;
}
