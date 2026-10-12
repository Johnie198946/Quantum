import FloatingField from '../components/FloatingField';
import React, { useState, useRef, useCallback, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useTravel } from '../TravelContext';
import { images, places, interestOptions } from '../data';
import { Icon, TopBar, Sheet, Primary, spring } from '../components/UI';
import { useScrollAction, ScrollAction } from '../components/ScrollAction';
import { useCylinderRows } from '../components/useCylinderRows';
import ExtraCardAssistant from '../components/ExtraCardAssistant';
import CurrencyPicker from '../components/CurrencyPicker';
import RangePicker,{readDates} from '../components/RangePicker';
const groups = [
  { id:'destination', title:'想去的地方', image:images.sakurajima },
  { id:'dates', title:'什么时候出发', image:images.senganen },
  { id:'party', title:'和谁一起', image:images.ibusuki },
  { id:'budget', title:'预算与旅行节奏', image:images.kirishima },
  { id:'interests', title:'喜欢怎样的风景', image:images.senganen },
  { id:'additional', title:'还有哪些小期待', image:images.ibusuki }
];
export default function Preferences() {
  const { setStage, profile, setProfile, updateDates, extraCards:extras, setExtraCards:setExtras } = useTravel();
  const [scale, setScale] = useState(1), [editing, setEditing] = useState(null), [adding, setAdding] = useState(false);
  const [extraTitle, setExtraTitle] = useState(''), [extraText, setExtraText] = useState(''), [extraPhoto, setExtraPhoto] = useState('senganen');
  const points = useRef(new Map()), pinch = useRef(null), scroll = useRef(null), grid = useRef(null), moved = useRef(false);
  useEffect(() => { const clear = e => { points.current.delete(e.pointerId); if (!points.current.size) pinch.current = null; }; window.addEventListener('pointerup',clear); window.addEventListener('pointercancel',clear); return () => { window.removeEventListener('pointerup',clear); window.removeEventListener('pointercancel',clear); }; }, []);
  const action = useScrollAction();
  const mode = scale > 0.85 ? 'large' : scale > 0.48 ? 'three' : 'text';
  const cards = [...groups,...extras];
  useCylinderRows(scroll, grid, mode, cards.length);
  const change = (key,value) => setProfile(prev => {const next={...prev,[key]:value};if(key==='additional')next.manualAdditional=value;if(prev.requirements){next.requirements={...prev.requirements};if(['budget','pace','interests','destination'].includes(key))next.requirements[key]=value;if(key==='count')next.requirements.count=/^\d+人?$/.test(value)?Number(value.replace('人','')):'未定';if(key==='interests')next.requirements.interestsDecided=true;}return next;});
  const summary = id => ({ destination:profile.destination,dates:profile.dates,party:profile.party+' · '+profile.count,budget:profile.budget+' · '+profile.pace,interests:profile.interests.join('、') || '未定',additional:profile.additional || '未决定的条件可以保留' }[id] || extras.find(x=>x.id===id)?.text);
  const pointerDown = e => {
    if (e.target.closest('input, textarea, select')) return;
    if (!points.current.size) moved.current=false;
    points.current.set(e.pointerId,{ x:e.clientX,y:e.clientY });
    if (points.current.size === 2) { const p=[...points.current.values()]; pinch.current={ distance:Math.hypot(p[0].x-p[1].x,p[0].y-p[1].y),scale }; moved.current=true; }
  };
  const pointerMove = e => {
    if (!points.current.has(e.pointerId)) return;
    const prior=points.current.get(e.pointerId);
    points.current.set(e.pointerId,{ x:e.clientX,y:e.clientY });
    if (points.current.size === 2 && pinch.current) { const p=[...points.current.values()]; setScale(Math.max(0.3,Math.min(1.3,pinch.current.scale*Math.hypot(p[0].x-p[1].x,p[0].y-p[1].y)/pinch.current.distance))); }
    else if (!pinch.current) { const delta=e.clientY-prior.y; if(Math.abs(delta)>2)moved.current=true; scroll.current.scrollTop -= delta;  }
  };
  const pointerEnd = e => { points.current.delete(e.pointerId); if (!points.current.size) pinch.current=null; };
  const closeEdit = useCallback(() => setEditing(null), []), closeAdd = useCallback(() => setAdding(false), []);
  const add = () => {
    if (!extraTitle.trim()) return;
    const selectedPhoto=places.find(x=>x.id===extraPhoto);
    setExtras(prev => [...prev,{ id:'extra-'+Date.now(),title:extraTitle.trim(),text:extraText,image:selectedPhoto.image,imageId:extraPhoto }]);
    change('additional',[profile.additional,extraTitle.trim()+': '+extraText].filter(Boolean).join('；'));
    setAdding(false); setExtraTitle(''); setExtraText('');
  };
  const toggleInterest = value => change('interests',profile.interests.includes(value) ? profile.interests.filter(x=>x!==value) : [...profile.interests,value]);
  return <section className="preferences-screen"><TopBar title="完善旅行计划" onBack={() => setStage('discover')}><button className="icon-btn glass add-card" aria-label="增加一张卡片" onClick={() => setAdding(true)}><Icon name="plus" /></button></TopBar>
    <div className="preference-scroll" ref={scroll} {...action.handlers}>
      <motion.div ref={grid} layout className={'preference-grid mode-'+mode} data-testid="semantic-grid" data-mode={mode} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerEnd} onPointerCancel={pointerEnd} onWheel={e=>{ if(e.ctrlKey){ e.preventDefault();setScale(prev=>Math.max(0.3,Math.min(1.3,prev-e.deltaY*0.004))); } }}>
        {cards.map((card,i)=><motion.div layout key={card.id} className={'cylinder-slot slot-'+i} transition={spring}><div className="cylinder-surface"><motion.button data-pending-key={'preference-'+card.id} className={'glass information-card info-'+i} transition={spring} onClick={e=>{if(!moved.current||e.detail===0)setEditing(card);}} whileTap={{scale:0.96}}><motion.img layout="position" src={card.image} alt="" /><div>{card.id==='destination'&&<div className="hero-caption"><h1>先说说，<br/>你想怎样出发。</h1><p>未决定的条件可以保留</p></div>}<p>{card.title}</p><strong>{summary(card.id)}</strong></div><Icon name="chevron" size={16}/></motion.button></div></motion.div>)}
      </motion.div>
      <div className="preference-bottom"><Icon name="leaf" /><p>留一点空白，<br />让旅程慢慢有模样。</p></div>
    </div>
    <ScrollAction {...action} onClick={()=>setStage('route')} disabled={!profile.destination.trim()}/>
    <AnimatePresence>
      {editing?.id==='dates'&&<RangePicker kind="dates" initial={readDates(profile)} onClose={closeEdit} onConfirm={range=>{updateDates(range);closeEdit();}}/>}
      {editing && editing.id!=='dates' && <Sheet label={editing.title} onClose={closeEdit} className="preference-edit-sheet" closeIcon="check" closeIconSize={20} closeLabel={'确认'+editing.title}><p className="eyebrow">这趟旅行的条件</p><h2>{editing.title}</h2><img className="field-photo" src={editing.image} alt="目的地视觉参考"/>
        {editing.id==='destination' && <label>目的地<FloatingField aria-label="目的地" value={profile.destination} onChange={e=>change('destination',e.target.value)}/></label>}
        {editing.id==='dates' && <label>出行日期<FloatingField aria-label="出行日期" value={profile.dates} onChange={e=>change('dates',e.target.value)}/></label>}
        {editing.id==='party' && <><div className="chips">{['一个人','情侣','朋友','家人'].map(x=><button key={x} className={profile.party===x?'selected':''} onClick={()=>change('party',x)}>{x}</button>)}</div><label>同行人数与补充<FloatingField aria-label="同行人数与补充" value={profile.count} onChange={e=>change('count',e.target.value)}/></label></>}
        {editing.id==='budget' && <><p>预算范围</p><div className="chips">{['经济','适中','舒适','不限','未定'].map(x=><button key={x} aria-pressed={profile.budget===x} className={profile.budget===x?'selected':''} onClick={()=>change('budget',x)}>{profile.budget===x&&<Icon name="check" size={12}/>} {x}</button>)}</div><p>旅行节奏</p><div className="chips">{['轻松','适中','充实','未定'].map(x=><button key={x} aria-pressed={profile.pace===x} className={profile.pace===x?'selected':''} onClick={()=>change('pace',x)}>{profile.pace===x&&<Icon name="check" size={12}/>} {x}</button>)}</div><div className="staggered-fields"><label>预算金额<FloatingField aria-label="预算金额" value={profile.amount} onChange={e=>change('amount',e.target.value)} placeholder="未定"/></label><CurrencyPicker value={profile.currency} onChange={value=>change('currency',value)}/></div></>}
        {editing.id==='interests' && <div className="chips">{interestOptions.map(x=><button aria-pressed={profile.interests.includes(x)} key={x} className={profile.interests.includes(x)?'selected':''} onClick={()=>toggleInterest(x)}>{x}</button>)}</div>}
        {(editing.id==='additional'||editing.id.startsWith('extra-')) && <label>偏好与其他要求<FloatingField as="textarea" rows={4} aria-label="偏好与其他要求" value={profile.additional} onChange={e=>change('additional',e.target.value)}/></label>}

      </Sheet>}
      {adding && <Sheet label="增加旅行卡片" onClose={closeAdd} className="extra-card-sheet"><header className="extra-card-heading"><p className="eyebrow">ONE MORE LITTLE WISH</p><h2>再留一点期待</h2><p>一张照片，留住一个小期待。</p></header><ExtraCardAssistant onFill={draft=>{setExtraTitle(draft.title);setExtraText(draft.text);}}/><div className="extra-card-layout"><div className="cover-options">{places.slice(0,4).map(p=><button key={p.id} aria-label={'选择'+p.name+'照片'} className={extraPhoto===p.id?'selected':''} onClick={()=>setExtraPhoto(p.id)}><img src={p.image} alt={p.name}/></button>)}</div><label>卡片标题<FloatingField aria-label="卡片标题" value={extraTitle} onChange={e=>setExtraTitle(e.target.value)} placeholder="例如：想多留一晚温泉"/></label><label>补充内容<FloatingField as="textarea" aria-label="卡片补充内容" value={extraText} onChange={e=>setExtraText(e.target.value)} rows={2}/></label></div><div className="extra-card-save"><Primary disabled={!extraTitle.trim()} onClick={add}>增加这张卡片</Primary></div></Sheet>}
    </AnimatePresence>
  </section>;
}
