import React, { useState, useRef, useEffect, useCallback } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import TravelThinkingOrb from '../components/TravelThinkingOrb';
import { useTravel } from '../TravelContext';
import { places } from '../data';
import { Icon, Sheet, Primary, spring } from '../components/UI';
import LiquidCard from '../components/LiquidCard';
import TravelComposer from '../components/TravelComposer';
import RequirementPhotoTray from '../components/RequirementPhotoTray';
const arrangements = [
 [{left:5,top:5,width:44,height:43,rotate:-4},{left:54,top:3,width:41,height:36,rotate:3},{left:6,top:54,width:43,height:35,rotate:3},{left:54,top:46,width:42,height:46,rotate:-3}],
 [{left:5,top:3,width:43,height:36,rotate:3},{left:55,top:7,width:40,height:42,rotate:-4},{left:6,top:47,width:43,height:46,rotate:-3},{left:56,top:57,width:39,height:34,rotate:4}],
 [{left:6,top:7,width:41,height:42,rotate:-3},{left:55,top:3,width:40,height:35,rotate:4},{left:5,top:56,width:42,height:35,rotate:3},{left:54,top:46,width:41,height:46,rotate:-4}]
];
const gravitySlots=[{left:6,top:4,width:44,height:40,rotate:-4},{left:54,top:18,width:42,height:34,rotate:3},{left:6,top:55,width:43,height:36,rotate:3},{left:54,top:62,width:42,height:31,rotate:-3}];
export default function Discover() {
  const { setStage, selected, selectPlace, setSelected, message, followUps, setFollowUps, followUpDraft, setFollowUpDraft, profile, setProfile,confirmPlaceFolder } = useTravel();
  const reduced=useReducedMotion();
  const serial = useRef(0), epoch = useRef(0), collectingKeys = useRef(new Set()), selectedRef = useRef(selected);
  selectedRef.current = selected;
  const entry = (place, layout) => ({ key:'discovery-'+(++serial.current),place,layout });
  const createBatch = n => Array.from({length:Math.min(4,places.length)},(_,i)=>entry(places[(n*4+i)%places.length],arrangements[n%arrangements.length][i]));
  const [deck,setDeck] = useState(()=>createBatch(0)), [collecting,setCollecting] = useState({}), [fall,setFall] = useState(0);
  const [batch, setBatch] = useState(0), [outgoing, setOutgoing] = useState(null);
  const [detail, setDetail] = useState(null), [drawer, setDrawer] = useState(false), [folderOpen, setFolderOpen] = useState(false);
  const [folderHover, setFolderHover] = useState(false), [dragActive,setDragActive]=useState(false), [justAdded, setJustAdded] = useState(false), [thinking, setThinking] = useState(false);
  const folder = useRef(null), canvas = useRef(null), drawerMessages = useRef(null), timers = useRef([]);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);
  useEffect(()=>{if(drawer)drawerMessages.current?.scrollTo({top:drawerMessages.current.scrollHeight,behavior:'smooth'});},[drawer,followUps.length]);
  const closeDetail = useCallback(() => setDetail(null), []), closeDrawer = useCallback(() => setDrawer(false), []), closeFolder = useCallback(() => setFolderOpen(false), []);
  const sendFollowUp = event => {
    event.preventDefault();
    const text=followUpDraft.trim();if(!text)return;
    setFollowUps(prev=>[...prev,{id:'follow-up-'+Date.now()+'-'+prev.length,text}]);
    setProfile(prev=>({...prev,additional:[prev.additional,text].filter(Boolean).join('；'),requirements:prev.requirements?{...prev.requirements,notes:[...prev.requirements.notes,text]}:undefined}));
    setFollowUpDraft('');
  };
  const add = (card,dragOffset=null) => {
    if (!card.place || collectingKeys.current.has(card.key) || outgoing) return false;
    collectingKeys.current.add(card.key);
    const generation=epoch.current;
    selectPlace(card.place.id);
    selectedRef.current=[...new Set([...selectedRef.current,card.place.id])];
    setJustAdded(true);setDetail(null);
    const f=folder.current.getBoundingClientRect(),c=canvas.current.getBoundingClientRect(),l=card.layout;
    setCollecting(prev=>({...prev,[card.key]:dragOffset?{x:dragOffset.x*.92,y:dragOffset.y*.92}:{x:f.x+f.width/2-(c.x+c.width*(l.left+l.width/2)/100),y:f.y+f.height/2-(c.y+c.height*(l.top+l.height/2)/100)}}));
    timers.current.push(setTimeout(()=>setJustAdded(false),550));
    const loading=entry(null,gravitySlots[0]);
    timers.current.push(setTimeout(()=>{
      if (generation!==epoch.current) return;
      setDeck(prev=>[loading,...prev.filter(x=>x.key!==card.key).sort((a,b)=>a.layout.top-b.layout.top).map((x,i)=>({...x,layout:gravitySlots[i+1]}))]);
      setFall(prev=>prev+1);
      setCollecting(prev=>{const next={...prev};delete next[card.key];return next;});
      collectingKeys.current.delete(card.key);
    },180));
    timers.current.push(setTimeout(()=>{
      if (generation!==epoch.current) return;
      setDeck(prev=>{
        if (!prev.some(x=>x.key===loading.key)) return prev;
        const visible=new Set(prev.filter(x=>x.place).map(x=>x.place.id));
        const available=places.filter(x=>!visible.has(x.id)),fresh=available.filter(x=>!selectedRef.current.includes(x.id));
        const next=(fresh.length?fresh:available)[0];
        return next?prev.map(x=>x.key===loading.key?{...x,place:next}:x):prev.filter(x=>x.key!==loading.key);
      });
    },1680));
    return true;
  };
  const dismiss = info => {
    if (outgoing) return;
    epoch.current+=1;
    const length = Math.hypot(info.offset.x,info.offset.y) || 1;
    setOutgoing({ x: info.offset.x / length * 650, y: info.offset.y / length * 650 });
    timers.current.push(setTimeout(() => { const next=batch+1;setBatch(next);setDeck(createBatch(next));setFall(0);setCollecting({});collectingKeys.current.clear();setOutgoing(null); }, 400));
  };
  const drop = (card, event, info) => {
    setFolderHover(false);setDragActive(false);
    const r = folder.current.getBoundingClientRect();
    const p = info.point;
    if (p.x > r.left-45 && p.x < r.right+45 && p.y > r.top-45 && p.y < r.bottom+45) return add(card,info.offset);
    if (Math.hypot(info.offset.x,info.offset.y) > 70 || Math.hypot(info.velocity.x,info.velocity.y) > 450) { dismiss(info); return true; }
    return false;
  };
  const magneticPull=(event,info)=>{const r=folder.current.getBoundingClientRect(),dx=r.left+r.width/2-info.point.x,dy=r.top+r.height/2-info.point.y,distance=Math.hypot(dx,dy);setFolderHover(distance<100);const scale=canvas.current.closest('.phone').getBoundingClientRect().width/canvas.current.closest('.phone').clientWidth;return distance<100?{x:dx*.16/scale,y:dy*.16/scale}:null;};
  const confirm = () => setFolderOpen(true);
  return <section className="discover-screen">
    <div className="discovery-top">
      <motion.button layoutId="question-glass" aria-label="旅行想法" className="glass idea-drawer" onClick={() => setDrawer(true)} whileTap={{ scale: 0.94 }}><Icon name="thought" size={20} /></motion.button>
      <motion.button ref={folder} aria-label={'想去的地方，已选' + selected.length + '个'} onClick={() => setFolderOpen(true)} className={'glass folder-target ' + (folderHover ? 'folder-hover' : '')} animate={reduced?{scale:1}:justAdded ? { scale: [1,1.28,0.97,1] } : folderHover&&dragActive?{scale:[1.08,1.22,1.08]}:{scale:1}} transition={{ duration: .55,repeat:folderHover&&dragActive&&!justAdded&&!reduced?Infinity:0 }}>
        <Icon name="folder" size={21} />
        {selected.length > 0 && <span key={selected.length} className="folder-count" aria-hidden="true">{selected.length}</span>}
      </motion.button>
    </div>
    {justAdded&&<span className="discovery-collection-state" role="status">已收进想去的地方 · {selected.length} 个</span>}
    <header className="discovery-heading"><p className="eyebrow">给旅程一点想象</p><h1>先看看，<br />哪些地方让你心动。</h1></header>
    <div className="discovery-canvas" ref={canvas} data-testid="discovery-canvas" aria-busy={deck.some(x=>!x.place)}>
      {deck.map((card,i) => { const {place,layout}=card;const absorbed=collecting[card.key];return <motion.div layout key={card.key} className="photo-position" data-card-key={card.key} data-slot={i} style={{left:layout.left+'%',top:layout.top+'%',width:layout.width+'%',height:layout.height+'%',zIndex:absorbed?12:4-i,pointerEvents:absorbed?'none':undefined}} initial={{y:place?100+i*20:-18,opacity:0,scale:0.85,rotate:0}} animate={absorbed?{...absorbed,scale:.08,opacity:0,rotate:0}:outgoing?{x:outgoing.x,y:outgoing.y,opacity:0,rotate:outgoing.x/30}:{x:0,y:place&&fall?[0,20+(fall%2)*2,-5,0]:0,opacity:1,scale:1,rotate:layout.rotate}} transition={absorbed?{duration:.18,ease:'easeIn'}:{...spring,layout:{type:'spring',stiffness:210,damping:18,mass:1.4},y:fall?{type:'tween',duration:.72,times:[0,.62,.82,1],ease:'easeInOut'}:spring}}>
        {place?<motion.div key={place.id} className="replacement-reveal" initial={{opacity:0,scale:.9,y:-12}} animate={{opacity:1,scale:1,y:0}} transition={spring}><LiquidCard className="glass discovery-card" data-pending-key={'place-'+place.id} data-testid={'place-'+place.id} onDrop={(e,info)=>drop(card,e,info)} onTap={()=>!outgoing&&!absorbed&&setDetail(place)} onDragStart={()=>setDragActive(true)} onDragMove={magneticPull}><img src={place.image} alt={place.name+'视觉参考'} draggable="false"/><div className="photo-caption"><h2>{place.name}</h2><p>{place.short}</p>{selected.includes(place.id)&&<span className="collected"><Icon name="check" size={13}/>已收集</span>}</div><button className="card-open" aria-label={'查看'+place.name} onClick={()=>setDetail(place)}><Icon name="chevron" size={18}/></button></LiquidCard></motion.div>:<div className="glass discovery-loading" role="status" aria-label="正在寻找新的景点"><TravelThinkingOrb/><p>再找一处心动的风景</p></div>}
      </motion.div>;})}
    </div>
    <footer className="discovery-footer"><button className="text-btn" onClick={() => dismiss({ offset: { x: -100,y: 0 } })}>滑走卡片，换一组惊喜 <span>↗</span></button><motion.button className="glass round-confirm" aria-label="确定" onClick={confirm} whileTap={{ scale: 0.9 }}><Icon name="check" size={16} /></motion.button></footer>
    <AnimatePresence>
      {detail && <Sheet label={detail.name + '详情'} onClose={closeDetail} className="place-sheet"><img className="place-detail-photo" src={detail.image} alt={detail.name + '视觉参考'} /><p className="eyebrow">{detail.area}</p><h2>{detail.name}</h2><p>{detail.detail}</p><Primary onClick={()=>{const card=deck.find(x=>x.place?.id===detail.id);if(card)add(card);}}><Icon name="folder" />{selected.includes(detail.id) ? '已在想去的地方' : '收进想去的地方'}</Primary></Sheet>}
      {drawer && <Sheet label="旅行想法" onClose={closeDrawer} className="conversation-sheet"><div className="drawer-messages" ref={drawerMessages} role="log" aria-label="旅行对话记录"><div className="glass mini-chat">你想去哪里？</div><div className="glass mini-chat user">{message || profile.destination || '旅行想法'}</div><RequirementPhotoTray/>{profile.requirements?.notes.map((text,index)=><div className="glass mini-chat user" key={'requirement-note-'+index}>{text}</div>)}{followUps.map(item=><motion.div layout key={item.id} className="glass mini-chat user" initial={{y:30,opacity:0,scale:.9}} animate={{y:0,opacity:1,scale:[1.03,.98,1]}} transition={{...spring,scale:{duration:.45}}}>{item.text}</motion.div>)}</div><TravelComposer drawer label="补充旅行想法" sendLabel="发送补充旅行想法" placeholder="再补充一点旅行想法…" value={followUpDraft} onChange={event=>setFollowUpDraft(event.target.value)} onSubmit={sendFollowUp}/></Sheet>}
      {folderOpen && <Sheet label="想去的地方" onClose={closeFolder}><h2>想去的地方</h2><p>{selected.length ? '把喜欢的风景，放在一起。' : '还没有收集，拖一张卡片进来吧。'}</p>{selected.map(id => { const p = places.find(place => place.id === id); if(!p)return null;return <div className="folder-row" key={id}><img src={p.image} alt="" /><span>{p.name}</span><button className="icon-btn" aria-label={'移出' + p.name} onClick={() => setSelected(prev => prev.filter(item => item !== id))}><Icon name="close" size={18} /></button></div>; })}<Primary onClick={confirmPlaceFolder}>完善旅行计划</Primary></Sheet>}
      {thinking && <motion.div className="thinking-veil" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><div className="thinking-center"><TravelThinkingOrb /><p>把想去的地方，连成一段旅程</p></div></motion.div>}
    </AnimatePresence>
  </section>;
}
