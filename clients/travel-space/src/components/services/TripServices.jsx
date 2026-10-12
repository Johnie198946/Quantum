import {displayServiceDistance} from '../../production/service-provider';
import ServiceSearch from '../../production/ServiceSearch';
import {useRuntime} from '../../production/RuntimePanel';
import {displayServicePrice,serviceCache} from '../../production/service-provider';
import FloatingField from '../FloatingField';
import React,{useState,useCallback,useRef} from 'react';
import {AnimatePresence,motion,useReducedMotion} from 'motion/react';
import {useTravel} from '../../TravelContext';
import {images} from '../../data';
import {Icon} from '../UI';
import InterestStatus from '../InterestStatus';
import {kinds,normalizePlan,mealTimes,searchCenter,filterCandidates,candidate,footprint,dayISO,conflicts,clock,minutes} from './planning';
import {applyServiceRecord} from './service-expenses';
import {parseMoney} from '../budget/budget-model';
import {currencyCode} from '../flight/price-currency';
import AlignedSelect from '../AlignedSelect';
import NearbyMap from './NearbyMap';
import FlightPlanner from './FlightPlanner';
import TravelLegs from './TravelLegs';
import ServiceSheet from './ServiceSheet';
import ServiceAccordion from './ServiceAccordion';
import HotelPlanner from './HotelPlanner';
import './revision68-services.css';

export default function TripServices(){
 useRuntime();
 const root=useRef(null),reduced=useReducedMotion();
 const {profile,setProfile,days,servicesFocus}=useTravel(),plan=normalizePlan(profile.servicePlan);
 const [expanded,setExpanded]=useState(servicesFocus.requestId?servicesFocus.kind:null),[kind,setKind]=useState(servicesFocus.kind||'flight'),[dayId,setDayId]=useState(servicesFocus.dayId||days[0].id),[meal,setMeal]=useState(servicesFocus.meal||'午餐'),[detail,setDetail]=useState(null),[announcement,setAnnouncement]=useState('');
 const [legSegment,setLegSegment]=useState(servicesFocus.segment==='airport'?'city':servicesFocus.segment||'city'),[flightDirection]=useState('outbound'),[query,setQuery]=useState(''),[adding,setAdding]=useState(false);
 const [custom,setCustom]=useState({name:'',time:'16:30',duration:'60',price:'',currency:currencyCode(profile.currency)});
 const day=days.find(d=>d.id===dayId)||days[0],filterKey=day.id+'-'+kind+'-'+meal;
 const filter={...(plan.filters[filterKey]||{}),center:kind==='restaurant'?'time':'poi',radius:1,sort:'兴趣'};
 const [times,setTimes]=useState({早餐:'07:30',午餐:'12:30',晚餐:'18:30',activity:'16:30'}),time=kind==='activity'?times.activity:times[meal],people=parseInt(profile.count)||1;
 const center=searchCenter(day,days,plan,filter,meal,kind),nearby=['restaurant','activity'].includes(kind);
 const results=nearby?filterCandidates(kind,center,filter,profile,meal,time,people).filter(item=>!query.trim()||[item.name,...item.tags].join(' ').toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())):[];
 const recordKey=kind==='restaurant'?day.id+'-'+meal:String(day.id),selected=plan[kind]?.[recordKey];
 const updatePlan=fn=>setProfile(prev=>({...prev,servicePlan:fn(normalizePlan(prev.servicePlan))}));
 const update=(type,key,value)=>{try{applyServiceRecord(profile,days,type,key,value);setProfile(previous=>applyServiceRecord(previous,days,type,key,value));setAnnouncement(value.name+'已保存'+(value.expenseDraft?.paid?'，实际花费已计入账本':'，预计花费已计入账本'));return '';}catch(error){setAnnouncement(error.message);return error.message;}};
 const close=useCallback(()=>setDetail(null),[]);
 const changeKind=value=>{setExpanded(value);if(value)setKind(value);setDetail(null);setQuery('');setAdding(false);};
 const selectCandidate=item=>{
  if(selected?.candidateId===item.id){updatePlan(prev=>{const group={...prev[kind]};delete group[recordKey];return {...prev,[kind]:group};});setAnnouncement(item.name+'已移出安排');return;}
  const record={key:recordKey,kind,dayId:day.id,candidateId:item.id,name:item.name,time,duration:item.duration,dateISO:dayISO(day,days,profile),dateLabel:day.date,people,units:1,price:item.price,priceCurrency:item.priceCurrency,source:item.source,footprint:footprint(day,days,plan,kind),status:'planned'};
  if(conflicts(day,days,plan,record).length){setDetail(item);setAnnouncement('这个时间与已有安排相遇了，展开后选一个空档。');return;}
  update(kind,recordKey,record);
 };
 const addCustom=event=>{event.preventDefault();const duration=Number(custom.duration),price=custom.price.trim()===''?null:Number(custom.price),start=minutes(custom.time);if(!custom.name.trim()||!Number.isInteger(duration)||duration<15||duration>480||custom.price.trim()!==''&&parseMoney(custom.price,custom.currency)===null||!Number.isFinite(start)||start+duration>1440){setAnnouncement('填写体验名称与有效时间，费用未定可以留空。');return;}const item={id:'activity-custom-'+day.id+'-'+Date.now(),kind:'activity',name:custom.name.trim().slice(0,100),image:day.image,geo:day.geo,price,priceCurrency:custom.currency,source:'用户填写',capacity:null,open:null,duration,tags:[],outdoor:false,advance:false};setDetail(item);setTimes(prev=>({...prev,activity:custom.time}));setAdding(false);};
 return <div ref={root} className="trip-services revision68-services">
 <ServiceSearch kind={kind} query={{destination:profile.destination,center,meal,date:dayISO(day,days,profile),time,people,keywords:query}}/><header className="services-heading"><p className="eyebrow">EVERY PART OF YOUR JOURNEY</p><h1>让沿途，<br/>衔接得刚刚好。</h1><p>{profile.dates} · {profile.count}</p></header><ServiceAccordion items={kinds} active={expanded} onChange={changeKind}><div className="revision68-services service-content">
  {kind!=='flight'&&<div className="services-days" role="group" aria-label="选择规划日期">{days.map((d,i)=><button aria-pressed={day.id===d.id} key={d.id} onClick={()=>{setDayId(d.id);setDetail(null);setQuery('');setAdding(false);}}><small>DAY {String(i+1).padStart(2,'0')}</small>{d.place}</button>)}</div>}
  {kind==='flight'&&<FlightPlanner onPlanTransfer={id=>{setDayId(id);setLegSegment('city');setKind('transport');setExpanded('transport');}} key={flightDirection} initialDirection={flightDirection} days={days} profile={profile} plan={plan} update={update} onSettings={settings=>updatePlan(prev=>({...prev,filters:{...prev.filters,flight:settings}}))}/>}
  {kind==='transport'&&<TravelLegs key={day.id+legSegment} initialSegment={legSegment} day={day} days={days} profile={profile} plan={plan} update={update} onSettings={settings=>updatePlan(prev=>({...prev,filters:{...prev.filters,['transport-'+day.id]:settings}}))}/>}
  {kind==='hotel'&&<HotelPlanner key={day.id} day={day} days={days} profile={profile} plan={plan} onFilter={changes=>updatePlan(prev=>({...prev,filters:{...prev.filters,[day.id+'-hotel-午餐']:{...(prev.filters[day.id+'-hotel-午餐']||{}),...changes}}}))} onDetail={setDetail}/>}
  {nearby&&<>
   {kind==='restaurant'&&<div className="meal-tabs" role="group" aria-label="用餐时段">{Object.keys(mealTimes).map(value=><button key={value} aria-pressed={meal===value} onClick={()=>{setMeal(value);setDetail(null);}}>{value}<small>{times[value]}</small></button>)}</div>}
   <section className="search-orbit service-search-simple"><motion.div className="service-search-capsule" whileTap={reduced?undefined:{scale:.985}}><Icon name="search" size={17}/><FloatingField type="search" aria-label={kind==='restaurant'?'搜索餐厅':'搜索玩法体验'} value={query} placeholder={kind==='restaurant'?'想吃什么，搜一搜':'找一个想体验的玩法'} onChange={event=>setQuery(event.target.value)}/>{query&&<button type="button" aria-label="清空搜索" onClick={()=>setQuery('')}><Icon name="close" size={13}/></button>}</motion.div>
    <label className="service-inline-time">{kind==='restaurant'?'用餐开始':'参与时间'}<FloatingField aria-label="筛选开始时间" type="time" value={time} onChange={event=>setTimes(prev=>({...prev,[kind==='activity'?'activity':meal]:event.target.value}))}/></label>
    {kind==='restaurant'&&<NearbyMap center={center} radius={1} results={results} selected={selected?.candidateId} onSelect={setDetail}/>}
   </section>
   {kind==='activity'&&<header className="experience-list-heading"><div><small>A MOMENT FOR SOMETHING NEW</small><h3>这一天，想试试什么？</h3></div><button type="button" className="experience-new" aria-label="新增玩法体验" aria-expanded={adding} onClick={()=>setAdding(!adding)}><Icon name={adding?'close':'plus'} size={17}/></button></header>}
   {adding&&kind==='activity'&&<form className="custom-experience" onSubmit={addCustom}><FloatingField aria-label="新增体验名称" value={custom.name} onChange={event=>setCustom({...custom,name:event.target.value})}/><div className="service-form-grid"><FloatingField aria-label="新增体验开始时间" type="time" value={custom.time} onChange={event=>setCustom({...custom,time:event.target.value})}/><FloatingField aria-label="新增体验时长分钟" type="number" min="15" max="480" value={custom.duration} onChange={event=>setCustom({...custom,duration:event.target.value})}/></div><AlignedSelect label="新增体验费用币种" value={custom.currency} options={['CNY','JPY','USD','EUR','THB'].map(code=>[code,code])} onChange={currency=>setCustom({...custom,currency})}/><FloatingField placeholder="费用待核对" aria-label="新增体验每人费用" type="number" min="0" value={custom.price} onChange={event=>setCustom({...custom,price:event.target.value})}/><button type="submit" className="primary confirm-capsule">展开并确认<Icon name="chevron" size={13}/></button></form>}
   {selected&&kind==='activity'&&!results.some(item=>item.id===selected.candidateId)&&<article className="experience-current"><small>已安排 · {selected.time}—{clock(minutes(selected.time)+(selected.duration||60))}</small><strong>{selected.name}</strong><p>{selected.note}</p><button type="button" onClick={()=>setDetail(candidate(selected.candidateId)||{...selected,id:selected.candidateId,capacity:null,open:null,tags:[],image:day.image})}>展开详情<Icon name="expand" size={13}/></button></article>}
   <div className={'service-results'+(kind==='activity'?' experience-results':'')} role="list" aria-label="规划候选">{results.length?results.map((item,index)=><motion.div layout role="listitem" key={item.id} className={'service-result result-offset-'+index%2+(selected?.candidateId===item.id?' is-selected':'')} data-candidate-id={item.id}><button className="service-result-detail" type="button" onClick={()=>setDetail(item)} aria-label={'查看'+item.name}><img src={item.imageUrl||images[item.image]||images.neutral} alt=""/><span><small>{kind==='activity'?time+'—'+clock(minutes(time)+item.duration):displayServiceDistance(item.distance)}</small><strong>{item.name}</strong><span className="service-result-meta">{displayServicePrice(item.price,item.priceCurrency)}／人{kind==='activity'?' · '+item.duration+'分钟':' · '+(item.rating??'评分待核对')}</span></span></button><InterestStatus choice={item.name} active={selected?.candidateId===item.id} onClick={()=>selectCandidate(item)}/></motion.div>):<div className="service-empty" role="listitem"><Icon name="search" size={21}/><p>{query?'换个关键词，再找找。':'附近暂时没有符合时间与人数的候选。'}</p>{kind==='activity'&&<button type="button" onClick={()=>setAdding(true)}>新增自己的体验<Icon name="plus" size={13}/></button>}</div>}</div>
  </>}
  </div></ServiceAccordion>
  <p role="status" aria-live="polite" className="service-announcement">{announcement}</p>
  <AnimatePresence>{detail&&<ServiceSheet container={root.current?.closest('.phone')} key={detail.id+'-'+day.id} item={detail} day={day} days={days} profile={profile} plan={plan} meal={meal} initialTime={kind==='activity'&&detail.id.startsWith('activity-custom-')?custom.time:time} people={people} criteria={filter} onClose={close} onSave={record=>{const error=update(record.kind,record.key,record);if(!error)close();return error;}}/>}</AnimatePresence>
 </div>;
}
