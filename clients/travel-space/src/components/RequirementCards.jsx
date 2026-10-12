import FloatingField from './FloatingField';
import React,{useState,useEffect,useRef} from 'react';
import {motion,useReducedMotion} from 'motion/react';
import {images} from '../data';
import {Calendar,Ruler} from './flight/InlinePickers';
import RequirementSteps from './RequirementSteps';
import IntentTray from './IntentTray';
import InterestScrub from './InterestScrub';
import {Icon,spring} from './UI';
import {interestChoices} from './travel-requirements';
const sections=[['时间与同行','从哪出发，给旅程留几天'],['按你的节奏','预算、交通，还有每天的松紧'],['把喜欢的放进旅程','可以多选，也可以先留白']];
const fields=[
 [{id:'date',title:'什么时候出发',hint:'选一个出发的日子',image:images.sakurajima},{id:'duration',title:'想玩几天',hint:'给风景留多少时间',image:images.senganen,options:[3,4,5,7,'未定'],unit:'天'},{id:'count',title:'几个人一起去',hint:'一个人、两人，或结伴同行',image:images.ibusuki,options:[1,2,3,4,'未定'],unit:'人'},{id:'origin',title:'从哪里出发',hint:'安排往返交通的起点',image:images.kirishima}],
 [{id:'budget',title:'预算想怎么安排',hint:'先选倾向，金额可随后补充',image:images.ibusuki,options:['经济','适中','舒适','不限','未定']},{id:'pace',title:'每天想怎么过',hint:'慢慢走，还是多看一些',image:images.senganen,options:['轻松','适中','充实','未定']},{id:'transport',title:'当地怎么移动',hint:'公交与渡轮，或自由自驾',image:images.sakurajima,options:['公共交通','自驾','包车','未定']}]
];
const interestImages=[images.sakurajima,images.ibusuki,images.senganen,images.kirishima,images.kirishima,images.ibusuki];
const interestHints=['火山、海岸与远眺','泡汤与温泉休息','当地餐桌与街巷味道','商店与手作','森林、山间与步道','安静角落与人少的地方'];
const label=(field,value)=>value===null?'选择':value==='未定'?'未定':value+(field.unit||'');
export default function RequirementCards({draft,onChange,step,onStep,onComplete}){
 const [editing,setEditing]=useState(null),[origin,setOrigin]=useState(''),reduced=useReducedMotion(),heading=useRef(null),rows=useRef({});
 useEffect(()=>{setEditing(null);heading.current?.focus();},[step]);
 const update=(key,value)=>{onChange({...draft,[key]:value});setEditing(null);requestAnimationFrame(()=>rows.current[key]?.focus());};
 const choices=fields[step];
 return <div className="requirement-flow">
  <RequirementSteps sections={sections} step={step} onStep={onStep}/>
  <motion.section key={step} className="glass requirement-card" aria-labelledby={'requirement-title-'+step} initial={reduced?false:{opacity:0,y:14}} animate={{opacity:1,y:0}} transition={spring}>
   <header><div><h2 ref={heading} tabIndex={-1} id={'requirement-title-'+step}>{sections[step][0]}</h2><p>{sections[step][1]}</p></div><div className="requirement-heading-actions"><span>{String(step+1).padStart(2,'0')} / 03</span><button type="button" className="icon-btn requirement-confirm" aria-label="确认旅行需求" onClick={onComplete}><Icon name="check" size={17}/></button></div></header>
   <ul>{step<2?choices.map(field=>{const open=editing===field.id;return <li key={field.id} className={open?'is-editing':''}>
    <button ref={el=>rows.current[field.id]=el} data-pending-key={'requirement-'+field.id} className="requirement-row" type="button" aria-label={'设置'+field.title} aria-expanded={open} aria-controls={'choices-'+field.id} onClick={()=>{setEditing(open?null:field.id);setOrigin(draft.origin&&draft.origin!=='未定'?draft.origin:'');}}><img src={field.image} alt=""/><span className="requirement-copy"><strong>{field.title}</strong><small>{field.hint}</small></span><span className={'requirement-value'+(draft[field.id]?' has-value':'')}>{draft[field.id]===null?'选择':label(field,draft[field.id])}<Icon name="chevron" size={12}/></span></button>
    {step===1?<IntentTray field={field} open={open} value={draft[field.id]} onSelect={value=>onChange({...draft,[field.id]:value})} onFinish={()=>{setEditing(null);requestAnimationFrame(()=>rows.current[field.id]?.focus({preventScroll:true}));}}/>:<div className="requirement-options" id={'choices-'+field.id} hidden={!open}>
     {['duration','count'].includes(field.id)&&<Ruler value={Number.isFinite(draft[field.id])?draft[field.id]:field.id==='count'?2:4} min={1} max={field.id==='count'?20:30} unit={field.unit} label={field.title+'刻度'} onChange={value=>onChange({...draft,[field.id]:value})} onClose={()=>update(field.id,Number.isFinite(draft[field.id])?draft[field.id]:field.id==='count'?2:4)}/>}
     {field.id==='date'&&open&&<Calendar label="出发日期" value={draft.date&&draft.date!=='未定'?draft.date:undefined} onSelect={value=>update('date',value)} onClose={()=>{setEditing(null);requestAnimationFrame(()=>rows.current.date?.focus({preventScroll:true}));}}/>}
     {field.id==='origin'&&<><label>出发城市<FloatingField aria-label="出发城市" placeholder="填写城市" value={origin} onChange={e=>setOrigin(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.nativeEvent.isComposing&&origin.trim()){e.preventDefault();update('origin',origin.trim());}}}/></label><div className="popular-origins" role="group" aria-label="常用出发城市">{['上海','北京','广州','深圳','香港','台北'].map(city=><button key={city} onClick={()=>update('origin',city)}>{city}</button>)}</div><button type="button" className="confirm-capsule" disabled={!origin.trim()} onClick={()=>update('origin',origin.trim())}>确定城市</button></>}
    </div>}
   </li>;}):<InterestScrub choices={interestChoices} images={interestImages} hints={interestHints} selected={draft.interests} onChange={interests=>onChange({...draft,interestsDecided:true,interests})}/>}</ul>
  </motion.section>

 </div>;
}
