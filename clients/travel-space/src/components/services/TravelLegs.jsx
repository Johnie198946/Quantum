import ServiceSearch from '../../production/ServiceSearch';
import {useRuntime} from '../../production/RuntimePanel';
import {displayServicePrice,serviceCache} from '../../production/service-provider';
import FloatingField from '../FloatingField';
import React,{useState,useRef} from 'react';
import {Icon,Primary} from '../UI';
import {images} from '../../data';
import NewTravelLeg from './NewTravelLeg';
import RouteEndpoints from './RouteEndpoints';
import RouteTickets from './RouteTickets';
import RouteDetails from './RouteDetails';
import {inheritedTransfer,airportGeo,transferMode} from './route-model';
import {modes,distance,footprint,clock,minutes,dayISO,recordState,stayFor,candidate,providerSearch} from './planning';
import ServiceExpenseForm from './ServiceExpenseForm';
import {serviceExpenseEntry} from './service-expenses';
import {parseMoney} from '../budget/budget-model';
import {currencyCode} from '../flight/price-currency';
import './revision68-services.css';
export default function TravelLegs({day,days,profile,plan,update,initialSegment='city',onSettings=()=>{}}){
 useRuntime();
 const index=days.findIndex(d=>d.id===day.id),previous=days[index-1];
 const inherited=inheritedTransfer(day,days,plan,profile);
 const [segment,setSegment]=useState(initialSegment);const key=segment==='city'&&!previous&&inherited.flight?day.id+'-airport':segment==='city'?String(day.id):day.id+'-'+segment,old=plan.transport[key];
 const [route,setRoute]=useState(null),[routeSettings,setRouteSettings]=useState(plan.filters['transport-'+day.id]||old?.routeSettings||{});
 const settingsRef=useRef(routeSettings);settingsRef.current=routeSettings;
 const setting=(key,value)=>{const next={...settingsRef.current,[key]:value};settingsRef.current=next;setRouteSettings(next);onSettings(next);};
 const hotel=stayFor(day,days,plan),food=candidate(plan.restaurant[day.id+'-午餐']?.candidateId),activity=candidate(plan.activity[day.id]?.candidateId);
 const custom=routeSettings.customSegments||[],customLeg=custom.find(x=>x.id===segment);
 const segmentOptions={city:[previous?.place||(inherited.flight?inherited.flight.to+'机场':'到达机场待确认'),!previous&&hotel?hotel.name:day.place,candidate(plan.hotel[previous?.id]?.candidateId)?.geo||previous?.geo||(!previous?airportGeo:null),!previous&&hotel?hotel.geo:day.geo],hotel:['酒店',day.geo?.anchor||day.place,hotel?.geo,day.geo],lunch:[day.geo?.anchor||day.place,'午餐餐厅',day.geo,food?.geo],play:['午餐餐厅','下午体验',food?.geo,activity?.geo],return:['当天末站','酒店',activity?.geo||day.geo,hotel?.geo]};
 const [defaultFromName,defaultToName,defaultFrom,defaultTo]=segmentOptions[segment]||['','',null,null],endpoints=routeSettings.endpoints?.[segment]||{},from=endpoints.from?endpoints.from.geo:defaultFrom,to=endpoints.to?endpoints.to.geo:defaultTo,fromName=endpoints.from?endpoints.from.name:defaultFromName,toName=endpoints.to?endpoints.to.name:defaultToName,missing=segment!=='city'&&(!from||!to);
 const [mode,setMode]=useState(transferMode(old?.mode)||inherited.mode),[depart,setDepart]=useState(old?.time||inherited.time),[buffer,setBuffer]=useState(old?.buffer||20),[carReturn,setCarReturn]=useState(old?.carReturn||'取车点还车');
 const [cost,setCost]=useState(!previous&&transferMode(old?.mode)!==inherited.mode?'':old?.price||''),[details,setDetails]=useState(old?.details||''),[selectedTicket,setSelectedTicket]=useState(old?.ticket||null),[record,setRecord]=useState(false),[provider,setProvider]=useState(old?.provider||''),[reference,setReference]=useState(old?.reference||'');
 const [expenseDraft,setExpenseDraft]=useState(null),[saveError,setSaveError]=useState('');
 const routeDate=segment==='city'&&!previous&&inherited.date?inherited.date:dayISO(day,days,profile);
 const km=from&&to?distance(from,to):NaN,estimate=route?route.duration+buffer:NaN;
 const water=false,farBike=mode==='单车'&&Number.isFinite(km)&&km>15;

 const time=minutes(depart),arrival=Number.isFinite(time)?clock((time+estimate)%1440):'',targetTime=segment==='lunch'?plan.restaurant[day.id+'-午餐']?.time:segment==='play'?plan.activity[day.id]?.time:segment==='return'?null:day.items[0]?.time,start=minutes(targetTime),late=Number.isFinite(start)&&Number.isFinite(time)&&time+estimate>start;
 const tooEarly=segment==='city'&&!previous&&plan.flights.outbound&&minutes(depart)<minutes(plan.flights.outbound.arrival)+30;
 const previousEnd=segment==='play'?minutes(plan.restaurant[day.id+'-午餐']?.time)+(plan.restaurant[day.id+'-午餐']?.duration||0):segment==='return'?minutes(plan.activity[day.id]?.time)+(plan.activity[day.id]?.duration||0):NaN,leaveBeforeEnd=Number.isFinite(previousEnd)&&minutes(depart)<previousEnd;
 const valid=!!route&&!!from&&!!to&&!leaveBeforeEnd&&(cost===''||parseMoney(cost,route?.priceCurrency||currencyCode(profile.currency))!==null)&&!tooEarly&&(!record||provider.trim()&&reference.trim())&&Number.isFinite(time)&&time+estimate<1440&&!farBike;
 const priceUnit=selectedTicket?.priceUnit||(['出租车','自驾'].includes(mode)?'／车':'／人'),people=Math.max(1,parseInt(profile.count)||1),unitAmount=cost===''?(route?.price??null):Number(cost),quoteCurrency=route?.priceCurrency||currencyCode(profile.currency),amount=unitAmount==null?null:unitAmount*(priceUnit==='／人'?people:1);
 const save=()=>{const value={kind:'transport',key,segment,dayId:day.id,name:customLeg?customLeg.name+' · '+fromName+' → '+toName:fromName+' → '+toName,mode,time:depart,duration:estimate,dateLabel:day.date,dateISO:routeDate,buffer,carReturn,water,routeSettings,ticket:selectedTicket,route:route?{...route}:null,source:route?.source||'用户填写',priceCurrency:quoteCurrency,price:cost===''?route?.price??null:cost,priceUnit,people,details,provider,reference,status:record?'recorded':['火车','自驾','出租车','渡轮'].includes(mode)?'todo':'planned',footprint:footprint(day,days,plan,'transport'),expenseDraft};try{serviceExpenseEntry(profile,days,'transport',key,value,expenseDraft);const error=update('transport',key,value);setSaveError(error||'');}catch(error){setSaveError(error.message);}};
 const selectSegment=next=>{const stored=plan.transport[next==='city'&&!previous&&inherited.flight?day.id+'-airport':next==='city'?String(day.id):day.id+'-'+next];setSegment(next);setDepart(stored?.time||({city:inherited.time,hotel:'08:00',lunch:'12:00',play:'14:00',return:'18:00'})[next]||'08:00');setMode(transferMode(stored?.mode)||(custom.find(x=>x.id===next)?.mode||(next==='city'?inherited.mode:'公交车')));setRecord(false);setRoute(null);setSelectedTicket(stored?.ticket||null);setCost(stored?.price||'');setDetails(stored?.details||'');setProvider(stored?.provider||'');setReference(stored?.reference||'');setCarReturn(stored?.carReturn||'取车点还车');setBuffer(stored?.buffer||20);setExpenseDraft(null);setSaveError('');};
 return <div className="travel-leg-panel" key={day.id}>
 <ServiceSearch kind={'route'} query={{from,fromName,to,toName,date:routeDate,time:depart,mode}}/><div className="leg-heading"><small>{customLeg?customLeg.name:segment==='city'?(previous?'城际衔接':'抵达接驳'):'市内逐段出行'}</small><h2>{fromName||'起点'} <span>→</span> {toName||'终点'}</h2><p>{day.date} · {from&&to?km.toFixed(1)+' km直线距离':'地点待查询，确认后展开路线'}</p></div><NewTravelLeg onAdd={leg=>{setting('customSegments',[...custom,leg]);setSegment(leg.id);setMode(leg.mode);setDepart('08:00');setRoute(null);setCost('');setDetails('');setRecord(false);setSelectedTicket(null);}}/><div className="leg-segments" role="group" aria-label="交通分段">{[['city','城际／接驳'],['hotel','酒店 → 兴趣点'],['lunch','兴趣点 → 午餐'],['play','午餐 → 体验'],['return','末站 → 酒店'],...custom.map(x=>[x.id,x.name])].map(([id,label])=><button type="button" key={id} aria-pressed={segment===id} onClick={()=>selectSegment(id)}>{label}</button>)}</div>{!previous&&segment==='city'&&inherited.flight&&<p className="transfer-inherited"><Icon name="plane" size={13}/>承接往返页 · {inherited.flight.arrival}落地 · {inherited.record?.line||inherited.mode}</p>}{(!defaultFrom||!defaultTo)&&<p className="service-quiet-caption">补充起点和终点的实际位置后查询路线。</p>}<RouteEndpoints key={segment} day={day} days={days} from={from} to={to} fromName={fromName} toName={toName} value={endpoints} resolvedLocations={routeSettings.resolvedLocations} onChange={value=>{setSelectedTicket(null);setting('endpoints',{...routeSettings.endpoints,[segment]:value});}}/><RouteDetails mode={mode} onMode={value=>{setMode(value);setCost('');setRecord(false);setSelectedTicket(null);}} from={from} to={to} fromName={fromName} toName={toName} time={depart} date={routeDate} water={water} onRoute={setRoute} settings={routeSettings} onSettings={setting}/>
  <div className="service-form-grid"><label>出发时间<FloatingField aria-label="交通出发时间" type="time" value={depart} onChange={e=>{setSelectedTicket(null);setDepart(e.target.value);}}/></label><label>接驳缓冲／分钟<FloatingField aria-label="接驳缓冲" type="number" min="0" max="180" value={buffer} onChange={e=>{setSelectedTicket(null);setBuffer(Math.max(0,Math.min(180,+e.target.value)));}}/></label></div>
  {mode==='自驾'&&<label>取还车方式<select aria-label="取还车方式" value={carReturn} onChange={e=>setCarReturn(e.target.value)}><option>取车点还车</option><option>异地还车，费用待核验</option><option>机场取还车</option></select></label>}
  <RouteTickets route={route} fromName={fromName} toName={toName} date={routeDate} time={depart} mode={mode} buffer={buffer} selected={selectedTicket} onSelect={ticket=>{setSelectedTicket(ticket);if(ticket){setDepart(ticket.time);setCost(String(ticket.price));}else setCost('');}}/>
  <p className="transport-time-advice"><Icon name="clock" size={13}/>{selectedTicket?selectedTicket.time+' 出发，'+selectedTicket.arrival+' 抵达。':'先选一班或一份交通安排。'}{targetTime?'下一项 '+targetTime+' 开始，建议至少提前 '+buffer+' 分钟抵达。':'抵达后留 '+buffer+' 分钟找入口、放行李。'}</p>
  {tooEarly&&<p role="status" className="service-conflict">机场接驳不能早于落地后30分钟，请调整出发时间与首日安排。</p>}
  {farBike&&<p role="status" className="service-conflict">距离超过15 km，请改用其他方式或拆成更短的单车段。</p>}
  {leaveBeforeEnd&&<p role="status" className="service-conflict">出发早于上一站结束，请给餐饮或游玩留够停留时间。</p>}
  {late&&<p role="status" className="service-conflict">晚于下一项 {targetTime} 安排。可提前出发或回到路线页调整行程。</p>}
  <section className="transport-cost-card" aria-label="交通费用"><label className="transport-cost">预计费用{priceUnit}<span><FloatingField type="number" min="0" aria-label="交通预计费用" placeholder={route?.price==null?'费用待核对':String(route.price)} value={cost} onChange={e=>setCost(e.target.value)}/><b aria-hidden="true">{quoteCurrency}</b></span></label><small>{priceUnit==='／人'?people+' 人 × 每人票价':'整车／整段费用'} · 合计 {displayServicePrice(route?amount:null,quoteCurrency)}</small></section>
  <ServiceExpenseForm key={key} profile={profile} kind="transport" recordKey={key} estimate={route?amount:null} currency={quoteCurrency} date={routeDate} onChange={setExpenseDraft}/><p className="service-save-error" role="alert">{saveError}</p>
  <Primary className="transport-confirm" icon="check" aria-label="确认交通安排" disabled={!valid||late||!route||!selectedTicket} onClick={save}>{record?'保存':'确认'}</Primary>
  {old&&<p className="service-policy">当前：{old.mode} · {old.time}出发 · {recordState(old,day,days,plan)}</p>}
 </div>;
}
