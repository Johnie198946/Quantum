import {runtime} from '../../production/runtime';
import {confirmExistingBooking} from '../../production/bookings';
import FloatingField from '../FloatingField';
import React,{useState} from 'react';
import {createPortal} from 'react-dom';
import {Sheet,Icon} from '../UI';
import {images} from '../../data';
import {dayISO,isoAdd,conflicts,freeTime,footprint,minutes,providerSearch} from './planning';
import ServiceExpenseForm from './ServiceExpenseForm';
import {serviceExpenseEntry} from './service-expenses';
import './revision68-services.css';
export default function ServiceSheet({container,item,day,days,profile,plan,meal,initialTime,people,criteria={},onClose,onSave}){
 const open=item.open||[0,1440],capacity=item.capacity??null;
 const key=item.kind==='restaurant'?day.id+'-'+meal:String(day.id),old=plan[item.kind][key];
 const [time,setTime]=useState(old?.time||initialTime),[date,setDate]=useState(old?.dateISO||dayISO(day,days,profile)),[checkout,setCheckout]=useState(old?.checkout||isoAdd(dayISO(day,days,profile),1));
 const [party,setParty]=useState(old?.people||people),[units,setUnits]=useState(old?.units||(item.kind==='hotel'?capacity?Math.ceil(people/capacity):1:1)),[note,setNote]=useState(old?.note||[profile.additional,criteria.diet?'饮食要求：'+criteria.diet:''].filter(Boolean).join('；')),[provider,setProvider]=useState(old?.provider||''),[reference,setReference]=useState(old?.reference||'');
 const [roomType,setRoomType]=useState(old?.roomType||'双床房'),[specification,setSpecification]=useState(old?.specification||'标准体验');
 const [mode,setMode]=useState('plan'),[ack,setAck]=useState(false),[actionId,setActionId]=useState(''),[saving,setSaving]=useState(false);
 const linkable=(runtime.document?.actions||[]).filter(a=>String(a.day_id)===String(day.id)&&!a.locked&&!a.booking_reference&&['planned','delayed'].includes(a.status)&&(!a.start||Date.parse(a.start)>Date.now()));
 const [expenseDraft,setExpenseDraft]=useState(null),[saveError,setSaveError]=useState('');
 const duration=item.duration||0,base={key,kind:item.kind,dayId:day.id,candidateId:item.id,name:item.name,time,duration,dateISO:date,dateLabel:day.date,checkout,people:party,units,roomType,specification,criteria,note,provider,reference,price:item.price,priceCurrency:item.priceCurrency,source:item.source,footprint:footprint(day,days,plan,item.kind)};
 const issues=conflicts(day,days,plan,base),suggestion=freeTime(day,days,plan,base,open);
 const expected=dayISO(day,days,profile),timeValid=item.kind==='hotel'||Number.isFinite(minutes(time))&&minutes(time)>=open[0]&&minutes(time)+duration<=open[1];
 const dateValid=!date||!expected||date===expected;
 const valid=Number.isInteger(units)&&units>0&&units<=8&&Number.isInteger(party)&&timeValid&&dateValid&&!issues.length&&party>0&&(capacity==null||party<=capacity*(item.kind==='hotel'?units:1))&&(item.kind!=='hotel'||!date||checkout>date);
 const ready=valid&&!!date&&(mode!=='record'||!!provider.trim()&&!!reference.trim()&&ack);
 const amount=item.price==null?null:item.kind==='hotel'?item.price*units*Math.max(1,Math.round((Date.parse(checkout)-Date.parse(date))/86400000)||1):item.price*party;
 const save=async()=>{if(saving)return;setSaving(true);const record={...base,actionId:mode==='record'?actionId:null,status:mode==='record'?'recorded':mode==='todo'?'todo':'planned',expenseDraft};try{serviceExpenseEntry(profile,days,item.kind,key,record,expenseDraft);if(mode==='record'&&actionId)await confirmExistingBooking(actionId,reference);const error=onSave(record);if(error)setSaveError(error);}catch(error){setSaveError(error.message);}finally{setSaving(false);}};
 return createPortal(<Sheet label={item.name+'预订准备'} onClose={onClose} className="service-sheet revision68-service-sheet"><figure className="service-sheet-photo"><img src={images[item.image]||item.image||day.image} alt="目的地区域照片，非商户实拍"/><figcaption>DAY {day.order||day.id} · {day.date}</figcaption></figure><p className="eyebrow">PLAN THE DETAILS</p><h2>{item.name}</h2>
  <nav className="service-sheet-modes" aria-label="预订操作">{[['plan','加入行程'],['todo','准备预订'],['record','录入已预订']].map(([id,label])=><button key={id} aria-pressed={mode===id} onClick={()=>setMode(id)}>{label}</button>)}</nav>
  <div className="service-form-grid"><label>{item.kind==='hotel'?'入住日期':'预约日期'}<FloatingField type="date" aria-label={item.kind==='hotel'?'入住日期':'预约日期'} value={date} onChange={e=>setDate(e.target.value)}/></label>{item.kind==='hotel'?<label>离店日期<FloatingField type="date" aria-label="离店日期" value={checkout} onChange={e=>setCheckout(e.target.value)}/></label>:<label>当地开始时间<FloatingField type="time" aria-label="预约开始时间" value={time} onChange={e=>setTime(e.target.value)}/></label>}<label>使用人数<FloatingField type="number" min="1" max={capacity==null?undefined:capacity*(item.kind==='hotel'?units:1)} aria-label="使用人数" value={party} onChange={e=>setParty(Number(e.target.value))}/></label>{item.kind==='hotel'?<label>房间数<FloatingField aria-label="房间数" type="number" min="1" max="8" value={units} onChange={e=>setUnits(Number(e.target.value))}/></label>:<p className="service-duration">停留 {duration} 分钟<br/>另留 15 分钟衔接</p>}</div>
  {item.kind==='hotel'&&<label>房型偏好<select aria-label="房型偏好" value={roomType} onChange={e=>setRoomType(e.target.value)}>{['双床房','大床房','家庭房','无障碍房'].map(x=><option key={x}>{x}</option>)}</select></label>}
  {item.kind==='activity'&&<label>体验规格<select aria-label="体验规格" value={specification} onChange={e=>setSpecification(e.target.value)}>{['标准体验','亲子体验','无障碍要求'].map(x=><option key={x}>{x}</option>)}</select></label>}
  {item.kind==='hotel'&&<p className="service-policy">{units} 间 × 每间人数 {capacity??'待核对'} · 房型：{party>2?'家庭房':'双床／大床待选择'} · 房型价格、入住时间、税费与取消截止时间向渠道确认。换酒店后附近三餐和体验会重新计算。</p>}
  {item.kind==='restaurant'&&item.open&&<p className="service-policy">{meal} · {Math.floor(open[0]/60)}:00—{Math.floor(open[1]/60)}:{String(open[1]%60).padStart(2,'0')}来源营业窗。饮食禁忌与座位要求一起交店确认；评分与指南星级分别展示。</p>}
  {item.kind==='activity'&&<p className="service-policy">{item.advance?'预约时段、门票规格、人数及退改待确认':item.price==null?'费用与开放时间待核对':item.price>0?'按每人费用计入预计花费':'免费活动，开放时间仍需核对'} · {item.outdoor?'户外项目，留雨天替代':'具体位置与参与条件可写在备注里'}。</p>}
  {!dateValid&&<p className="service-conflict" role="status">预约日期与这天行程不同，请调整日期或回到行程调整。</p>}
  {!timeValid&&<p className="service-conflict" role="status">所选时间不在可体验的营业窗口内。</p>}
  {!!issues.length&&<div className="service-conflict" role="status"><strong>需要错开时间</strong><ul>{issues.map((x,i)=><li key={i}>{x}</li>)}</ul>{suggestion?<button onClick={()=>setTime(suggestion)}>改到 {suggestion} 空档</button>:<p>当天没有合适空档，请调整原行程或换更短的体验。</p>}</div>}
  <label>偏好与备注<FloatingField as="textarea" aria-label="预订备注" rows={2} value={note} onChange={e=>setNote(e.target.value)} placeholder="餐食禁忌、房型、无障碍或游玩要求"/></label>
  {mode!=='plan'&&<section className="booking-review"><h3>{mode==='todo'?'去预订前，核对这些':'记录你已有的订单'}</h3><ol><li>日期、人数、规格与实际位置</li><li>实时价格、库存、取消与退改条件</li><li>在官网或平台完成预订，再回来记录订单</li></ol><a className="provider-search" href={providerSearch(item.kind,day,profile,base)} target="_blank" rel="noreferrer">查找真实预订入口 <Icon name="expand" size={12}/></a><p className="service-source">按真实地区、类型与日期搜索，请在渠道核对实际可订项目。订单号不会传给搜索渠道。</p><label>预订渠道<FloatingField aria-label="预订渠道" value={provider} onChange={e=>setProvider(e.target.value)} placeholder="官网／平台／电话"/></label>{mode==='record'&&<><label>订单号或确认凭据<FloatingField aria-label="订单确认凭据" value={reference} onChange={e=>setReference(e.target.value)}/></label><label>关联已有行程安排<select aria-label="关联已有行程安排" value={actionId} disabled={!runtime.adopted} onChange={e=>setActionId(e.target.value)}><option value="">仅保存预订记录</option>{linkable.map(a=><option key={a.id} value={a.id}>{a.title}</option>)}</select></label><label className="service-check"><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>我已在外部完成预订，此处只录入记录</label></>}</section>}
  <ServiceExpenseForm profile={profile} kind={item.kind} recordKey={key} estimate={amount} currency={item.priceCurrency||profile.currency||'CNY'} date={date} onChange={setExpenseDraft}/>
  <p role="alert" className="service-save-error">{saveError}</p>
  <button className="primary confirm-capsule service-apply" disabled={saving||(mode==='plan'?!valid:!ready)} aria-busy={saving} onClick={save}>{mode==='record'?'保存已有预订记录':mode==='todo'?'加入待预订清单':'加入这天行程'}<Icon name="check" size={14}/></button>
 </Sheet>,container||document.body);
}
