import React,{useState} from 'react';
import {motion,useReducedMotion} from 'motion/react';
import {Icon,Primary,Disclosure} from '../UI';
import FloatingField from '../FloatingField';
import InlinePassengers from '../flight/InlinePassengers';
import RichMessage from '../journal/RichMessage';
import VoiceText from '../journal/VoiceText';
import AssistantRoute from './AssistantRoute';
import {answerKinds} from './assistant-model';
import './assistant-cards.css';
const titles={schedule:'把时间，衔接得更从容。',party:'这一程，和谁一起？',route:'从这里，到下一处风景。',weather:'把天气，放进行程里。',flight:'选一班，接住出发的期待。',hotel:'把夜晚，留在喜欢的附近。',image:'先收下一张喜欢的风景。',rich:'把想留下的，收进手记。',code:'用一段清楚的结构，收好安排。',flow:'每次确认，都有一个结果。'};
const phases=['提需求','给方案','待确认','回填','结果'];
function WorkflowSteps({status}){const active=status==='applied'?4:status==='applying'?3:2;return <ol className="answer-workflow" aria-label="需求到回填流程">{phases.map((phase,i)=><li key={phase} className={i<active?'is-done':i===active?'is-active':''} aria-current={i===active?'step':undefined}><span>{i<active?<Icon name="check" size={10}/>:i+1}</span><small>{phase}</small></li>)}</ol>;}
function Counter({label,value,onChange}){return <div className="answer-counter"><span>{label}</span><div><button type="button" aria-label={'减少'+label} disabled={Number(value)<=1} onClick={()=>onChange(Number(value)-1)}>−</button><output>{value}</output><button type="button" aria-label={'增加'+label} disabled={Number(value)>=20} onClick={()=>onChange(Number(value)+1)}>+</button></div></div>;}
export default function StructuredAnswer({card,day,days,onChange,onApply,onRegenerate,onOpenService}){
 const [editing,setEditing]=useState(false),[copied,setCopied]=useState(false),reduced=useReducedMotion(),values=card.values||{},kind=card.kind,done=card.status==='applied',busy=card.status==='applying',definition=answerKinds.find(k=>k[0]===kind),selectedPhoto=days.find(d=>String(d.id)===String(values.photoId))||day;
 const update=(key,value)=>onChange({...card,values:{...values,[key]:value},status:'proposal',error:'',result:''});
 const code=JSON.stringify({place:day.place,date:day.date,items:day.items.map(i=>({time:i.time,title:i.title}))},null,2);
 const copy=async()=>{try{await navigator.clipboard.writeText(code);setCopied(true);}catch{setCopied(false);}};
 return <motion.article layout className={'assistant-answer glass answer-'+kind+' status-'+card.status} data-answer-id={card.id} aria-label={definition?.[1]+'建议卡片'} initial={reduced?false:{opacity:0,y:12}} animate={{opacity:1,y:0}} transition={{duration:reduced?0:.22}}>
  <header className="answer-heading"><span className="answer-kind-icon"><Icon name={definition?.[2]||'spark'} size={18}/></span><div><small>DAY {day.order||day.id} · {day.date} · {day.place}</small><h2>{titles[kind]}</h2></div></header>
  <WorkflowSteps status={card.status}/>
  <fieldset className="answer-body" disabled={done||busy}>
  {card.quote&&<blockquote className="answer-extract">{card.quote}</blockquote>}
  {kind==='schedule'&&<div className="answer-fields"><label>调整哪一项<select aria-label="建议调整的安排" value={values.itemIndex} disabled={done} onChange={e=>update('itemIndex',Number(e.target.value))}>{day.items.map((i,index)=><option key={index} value={index}>{i.time} · {i.title}</option>)}</select></label><label>建议开始时间<FloatingField type="time" aria-label="建议开始时间" value={values.time} disabled={done} onChange={e=>update('time',e.target.value)}/></label><p className="answer-time-note"><Icon name="clock" size={14}/>预留衔接时间；确认时检查当天时间顺序。</p></div>}
  {kind==='party'&&<div className="answer-control-tray"><InlinePassengers scope="建议" value={values.count} onChange={n=>update('count',n)}/><Counter label="同行人数" value={values.count} onChange={n=>update('count',n)}/><label className="answer-switch"><span>把这个人数用于同行需求</span><input type="checkbox" aria-label="同步同行人数需求" checked={!!values.automatic} onChange={e=>update('automatic',e.target.checked)}/></label></div>}
  {kind==='route'&&<AssistantRoute days={days} values={values} onChange={update}/>}
  {kind==='weather'&&<div className="answer-weather"><div><Icon name="sun" size={28}/><strong>{values.temperature===''?'—':values.temperature}°</strong><span>{values.condition}</span></div><div className="answer-fields"><label>当天气温<FloatingField type="number" aria-label="当天气温" min={-60} max={60} value={values.temperature} onChange={e=>update('temperature',e.target.value)}/></label><label>天气<select aria-label="天气状况" value={values.condition} onChange={e=>update('condition',e.target.value)}>{['晴','多云','雨','雪'].map(x=><option key={x}>{x}</option>)}</select></label></div><p>填写你查到的天气，确认后存入当天日记。</p></div>}
  {['flight','hotel'].includes(kind)&&<div className="answer-booking"><div className="answer-booking-route"><Icon name={kind==='flight'?'plane':'bed'} size={24}/><strong>{kind==='flight'?day.place+' · 航班安排':day.place+' · 当晚住宿'}</strong><span>{day.date}</span></div><Counter label="出行人数" value={values.count} onChange={n=>update('count',n)}/>{kind==='hotel'&&<Counter label="房间数" value={values.roomCount} onChange={n=>update('roomCount',n)}/>}<p>先留下一张预订需求卡，再挑选班次或酒店。</p><button type="button" className="answer-secondary" onClick={()=>onOpenService(kind,day.id)}>{kind==='flight'?'查看航班':'挑选酒店'}<Icon name="chevron" size={14}/></button></div>}
  {kind==='image'&&<><figure className="answer-photo"><img src={selectedPhoto.image} alt={selectedPhoto.place+'目的地照片'}/><figcaption>{selectedPhoto.place} · {selectedPhoto.name}</figcaption></figure><div className="answer-photo-tray" aria-label="目的地照片托盘">{days.map(d=><button type="button" key={d.id} aria-label={'选择'+d.place+'照片'} aria-pressed={String(values.photoId)===String(d.id)} onClick={()=>update('photoId',d.id)}><img src={d.image} alt=""/></button>)}</div></>}
  {kind==='rich'&&<><RichMessage text={values.note}/><Disclosure title="编辑这段内容" open={editing}><VoiceText rich label="答案卡片笔记" rows={3} value={values.note} onChange={text=>update('note',text)}/></Disclosure></>}
  {kind==='code'&&<div className="answer-code"><header><span>JSON · 当天行程</span><button type="button" aria-label="复制行程代码" onClick={copy}>{copied?'已复制':'复制'}</button></header><pre tabIndex={0}><code>{code}</code></pre></div>}
  {kind==='flow'&&<div className="answer-flow-chart" aria-label="旅行回填流程图"><div><Icon name="thought" size={16}/>用户需求</div><span>↓</span><div><Icon name="spark" size={16}/>生成可修改方案</div><span>↓</span><div><Icon name="edit" size={16}/>核对字段与时间</div><span>↓</span><div><Icon name="check" size={16}/>用户确认 → 回填手记</div><span>↓</span><div><Icon name={done?'check':card.error?'replay':'clock'} size={16}/>{done?'成功 · 已收好':card.error?'失败 · 修改或重新生成':'等待确认'}</div></div>}
  {['route','image','code','flow'].includes(kind)&&<label className="answer-note">随卡片收下的文字<FloatingField as="textarea" rows={2} aria-label="卡片收录文字" value={values.note} onChange={e=>update('note',e.target.value)}/></label>}
  </fieldset>
  {card.error&&<div className="answer-result is-failed" role="alert"><Icon name="replay" size={18}/><div><strong>还没有回填</strong><p>{card.error}</p><button type="button" onClick={()=>onRegenerate(card)}>重新生成这张卡片</button></div></div>}
  {done?<div className="answer-result is-success" role="status"><Icon name="check" size={18}/><div><strong>已收好这次确认</strong><p>{card.result}</p></div></div>:<footer className="answer-actions"><button type="button" className="answer-secondary" onClick={()=>{setEditing(true);onChange({...card,status:'proposal',error:''});}}>修改提议<Icon name="edit" size={14}/></button><Primary icon="check" disabled={busy} onClick={()=>onApply(card)}>{busy?'正在回填':['flight','hotel'].includes(kind)?'确认预订需求':kind==='schedule'?'确认时间':kind==='party'?'确认人数':kind==='weather'?'确认天气':'收进当天手记'}</Primary></footer>}
 </motion.article>;
}
