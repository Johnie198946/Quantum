import FloatingField from './FloatingField';
import React,{useState,useId} from 'react';
import {motion,useReducedMotion} from 'motion/react';
import {useTravel} from '../TravelContext';
import {images,interestOptions} from '../data';
import {Icon,Primary,spring} from './UI';
const rows=[['destination','想去的地方','sakurajima'],['dates','出行日期','senganen'],['count','同行人数','ibusuki'],['budget','预算与节奏','kirishima'],['interests','风景与期待','senganen']];
export default function RequirementPhotoTray(){
 const {profile,setProfile,updateDates}=useTravel(),[open,setOpen]=useState(false),[draft,setDraft]=useState(null),[status,setStatus]=useState(''),id=useId(),reduced=useReducedMotion();
 const change=(key,value)=>setDraft(prev=>({...prev,[key]:value}));
 const edit=()=>{setOpen(true);setDraft({...profile,count:Number.isFinite(parseInt(profile.count))?String(parseInt(profile.count)):'',interests:[...profile.interests],dateRange:[...(profile.dateRange||['',''])]});setStatus('');};
 const count=draft&&draft.count!==''?Number(draft.count):'未定',validDates=!draft||!draft.dateRange.some(Boolean)||draft.dateRange.every(Boolean)&&draft.dateRange[1]>=draft.dateRange[0];
 const invalid=draft&&(!draft.destination.trim()||count!=='未定'&&(!Number.isInteger(count)||count<1||count>20)||!validDates);
 const save=()=>{if(invalid)return;const range=draft.dateRange,duration=range.every(Boolean)?Math.round((Date.parse(range[1])-Date.parse(range[0]))/86400000)+1:profile.duration;
  setProfile(prev=>({...prev,destination:draft.destination.trim(),origin:draft.origin?.trim()||'未定',count:count==='未定'?'人数未定':count+'人',budget:draft.budget,pace:draft.pace,transport:draft.transport,interests:draft.interests,additional:draft.additional,manualAdditional:draft.additional,duration,requirementsConfirmed:true,requirements:{...prev.requirements,date:range[0]||prev.requirements?.date||'未定',duration,count,origin:draft.origin?.trim()||'未定',budget:draft.budget,pace:draft.pace,transport:draft.transport,interests:draft.interests,interestsDecided:true,notes:prev.requirements?.notes||[]}}));
  if(range.every(Boolean))updateDates(range.map(x=>Date.parse(x+'T00:00:00Z')/86400000));setDraft(null);setStatus('旅行需求已保存');};
 const summary=key=>({destination:profile.destination+' · '+(profile.origin||'出发地未定'),dates:profile.dates,count:profile.count,budget:profile.budget+'预算 · '+profile.pace+'节奏 · '+profile.transport,interests:profile.interests.join('、')||'偏好未定'}[key]);
 const select=(key,label,options)=><label>{label}<select aria-label={'页内'+label} value={draft[key]||'未定'} onChange={e=>change(key,e.target.value)}>{options.map(x=><option key={x}>{x}</option>)}</select></label>;
 return <article className={'requirement-photo-tray'+(draft?' is-editing':'')} aria-label="旅行需求卡片"><img className="recap-photo" src={images.sakurajima} alt="旅行风景示意"/><motion.div className="recap-tray glass" layout transition={reduced?{duration:0}:spring}>
  <button className="recap-tray-toggle" type="button" aria-expanded={open} aria-controls={id} onClick={()=>{if(!draft)setOpen(!open);}}><span className="recap-handle" aria-hidden="true"/><span><strong>{profile.destination}旅行</strong><small>{profile.dates} · {profile.count}</small></span><Icon name={open?'down':'chevron'} size={16}/></button>
  <div id={id} hidden={!open} className="recap-details">{draft?<form aria-label="页内修改旅行需求" onSubmit={e=>{e.preventDefault();save();}}><div className="recap-edit-heading"><img src={images.senganen} alt=""/><div><h3>调整这趟旅行</h3><p>改好后，留在这里保存。</p></div></div>
   <label>目的地<FloatingField aria-label="页内目的地" value={draft.destination} onChange={e=>change('destination',e.target.value)}/></label><label>出发城市<FloatingField aria-label="页内出发城市" value={draft.origin==='未定'?'':draft.origin||''} onChange={e=>change('origin',e.target.value)} placeholder="还没决定"/></label>
   <div className="recap-two-fields">{['出发日期','返回日期'].map((name,i)=><label key={name}>{name}<FloatingField type="date" aria-label={'页内'+name} min={i?draft.dateRange[0]:undefined} value={draft.dateRange[i]} onChange={e=>change('dateRange',draft.dateRange.map((x,n)=>n===i?e.target.value:x))}/></label>)}</div>
   <div className="recap-two-fields"><label>同行人数<FloatingField aria-label="页内同行人数" type="number" min="1" max="20" step="1" value={draft.count} onChange={e=>change('count',e.target.value)}/></label>{select('budget','预算',['经济','适中','舒适','不限','未定'])}</div>
   <div className="recap-two-fields">{select('pace','旅行节奏',['轻松','适中','充实','未定'])}{select('transport','交通',['公共交通','自驾','包车','未定'])}</div>
   <fieldset><legend>喜欢的风景</legend><div className="recap-interest-chips">{interestOptions.map(x=><button type="button" key={x} aria-pressed={draft.interests.includes(x)} onClick={()=>change('interests',draft.interests.includes(x)?draft.interests.filter(v=>v!==x):[...draft.interests,x])}>{x}</button>)}</div></fieldset>
   <label>其他期待<FloatingField as="textarea" rows={2} aria-label="页内其他期待" value={draft.additional||''} onChange={e=>change('additional',e.target.value)}/></label>{invalid&&<p role="status">请填写目的地、1—20位同行和有效的往返日期。</p>}<div className="recap-actions"><button type="button" className="text-btn" onClick={()=>{setDraft(null);setStatus('已保留原来的旅行需求');}}>取消修改</button><Primary type="submit" disabled={invalid} icon="check">保存</Primary></div>
  </form>:<><div className="recap-detail-rows">{rows.map(([key,title,photo])=><div className="recap-detail-row" key={key}><img src={images[photo]} alt=""/><div><small>{title}</small><strong>{summary(key)}</strong></div></div>)}</div><button type="button" className="recap-edit-button" onClick={edit}><Icon name="edit" size={14}/>修改旅行需求</button></>}</div><p className="recap-status" role="status">{status}</p></motion.div></article>;
}
