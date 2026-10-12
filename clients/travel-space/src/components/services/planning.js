import {parseMoney,convertMinor,CURRENCIES,DEFAULT_RATES} from '../budget/budget-model';
import {serviceCache} from '../../production/service-provider';
import {destinations} from '../mapRoute';
export const kinds=[['flight','往返','plane'],['transport','交通','car'],['hotel','住宿','bed'],['restaurant','三餐','dining'],['activity','体验','ticket']];
export const mealTimes={早餐:'07:30',午餐:'12:30',晚餐:'18:30'};
export const modes={火车:{speed:65,wait:25,note:'核对车站、末班车与余票；两端接驳单独留时间。'},自驾:{speed:42,wait:15,note:'取还车点、驾驶资格、停车、油费与过路费一起确认。'},出租车:{speed:35,wait:10,note:'短途与行李接驳；跨城费用、预约与车型待确认。'},公交车:{speed:22,wait:20,note:'确认站点、步行接驳、班次与末班时间。'},单车:{speed:12,wait:10,note:'考虑坡度、天气、行李与还车点；长途建议换方式。'},步行:{speed:4,wait:0,note:'保留体力与无障碍要求，距离为直线估算。'},渡轮:{speed:20,wait:25,note:'核对港口、航班与可否携车；火山和天气条件另行核验。'}};
const rad=x=>x*Math.PI/180;
export function distance(a,b){if(!a||!b||![a.lat,a.lon,b.lat,b.lon].every(Number.isFinite))return Infinity;const dlat=rad(b.lat-a.lat),dlon=rad(b.lon-a.lon);const q=Math.sin(dlat/2)**2+Math.cos(rad(a.lat))*Math.cos(rad(b.lat))*Math.sin(dlon/2)**2;return 6371*2*Math.atan2(Math.sqrt(q),Math.sqrt(Math.max(0,1-q)));}
export const minutes=t=>/^\d\d:\d\d$/.test(t||'')?Number(t.slice(0,2))*60+Number(t.slice(3)):NaN;
export const clock=n=>String(Math.floor(n/60)).padStart(2,'0')+':'+String(n%60).padStart(2,'0');
export const isoAdd=(date,n)=>{if(!/^\d{4}-\d{2}-\d{2}$/.test(date||''))return '';const d=new Date(date+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);};
export function dayISO(day,days,profile){if(day.dateISO)return day.dateISO;const start=profile.dateRange?.[0]||profile.requirements?.date;return isoAdd(start,days.findIndex(d=>d.id===day.id));}
export function normalizePlan(value){const next={};for(const key of ['flights','transport','hotel','restaurant','activity','filters'])next[key]=value?.[key]&&typeof value[key]==='object'&&!Array.isArray(value[key])?value[key]:{};if(Number.isFinite(value?.position?.lat)&&Number.isFinite(value?.position?.lon))next.position=value.position;return next;}
export const makeCatalog=()=>serviceCache.candidates;
export const catalog=serviceCache.candidates;
export const candidate=id=>serviceCache.candidates.find(c=>c.id===id);
export function stayFor(day,days,plan,previous=false){const index=days.findIndex(d=>d.id===day.id);return candidate(plan.hotel[previous?days[Math.max(0,index-1)]?.id:day.id]?.candidateId);}
export function searchCenter(day,days,plan,filter,meal='午餐',kind='hotel'){
 const hotel=stayFor(day,days,plan,meal==='早餐')||stayFor(day,days,plan);
 if(filter.center==='current'&&plan.position)return {...plan.position,label:'当前位置'};
 if(filter.center==='hotel'&&hotel?.geo)return {...hotel.geo,label:hotel.name};
 if(filter.center==='meal'){const food=candidate(plan.restaurant[day.id+'-'+meal]?.candidateId);if(food?.geo)return {...food.geo,label:food.name};}
 if(filter.center==='cluster'&&day.geo){
  const next=days[days.findIndex(d=>d.id===day.id)+1],p=next?.geo||day.geo;
  if(day.geo&&p&&distance(day.geo,p)>30)return {...day.geo,label:'今日区域 · 次日跨城'};
  return {lat:day.geo.lat*.7+p.lat*.3,lon:day.geo.lon*.7+p.lon*.3,label:'今日重点＋次日去向'};
 }
 if(filter.center==='time'){
  if((meal==='早餐'||meal==='晚餐')&&hotel?.geo)return {...hotel.geo,label:meal+' · 酒店位置'};
  const activityRecord=plan.activity[day.id],activity=activityRecord&&minutes(activityRecord.time)<=minutes(mealTimes[meal])?candidate(activityRecord.candidateId):null;
  return {...(activity?.geo||day.geo),label:meal==='午餐'?'午间行程位置':meal+' · 行程位置'};
 }
 return {...day.geo,label:day.geo?.anchor||day.place};
}
export function comparisonPrice(row,profile){
 const currency=profile.budgetLedger?.baseCurrency||profile.currency||'CNY';
 if(row.price==null||!row.priceCurrency)return null;
 if(row.priceCurrency===currency)return row.price;
 const amount=parseMoney(String(row.price),row.priceCurrency);
 const converted=amount===null?null:convertMinor(amount,row.priceCurrency,currency,{...DEFAULT_RATES,...profile.budgetLedger?.rates});
 return converted===null?null:converted/10**CURRENCIES[currency];
}
export function filterCandidates(kind,center,filter,profile,meal,time,people){
 const radius=Number(filter.radius)||3,start=minutes(time);
 const seafood=/不吃海鲜|海鲜过敏|避开海鲜/.test(profile.additional||'');
 return serviceCache.candidates.filter(c=>c.kind===kind&&(!Number.isFinite(distance(center,c.geo))||distance(center,c.geo)<=radius+.00001))
 .filter(c=>(!filter.minRating||c.rating>=Number(filter.minRating))&&(!filter.maxPrice||comparisonPrice(c,profile)!=null&&comparisonPrice(c,profile)<=Number(filter.maxPrice))&&(c.capacity==null||c.capacity>=people))
 .filter(c=>kind!=='hotel'||(!filter.stars||c.stars>=+filter.stars)&&(!filter.amenity||c.amenities.includes(filter.amenity)))
 .filter(c=>kind!=='restaurant'||(!c.meal||c.meal===meal)&&(!seafood||!c.seafood)&&(!filter.diet||c.diets.includes(filter.diet))&&(!filter.award||c.award>=+filter.award))
 .filter(c=>kind!=='activity'||(!filter.weather||filter.weather!=='雨天'||!c.outdoor)&&(!filter.category||c.tags.includes(filter.category)))
 .filter(c=>!c.open||Number.isFinite(start)&&start>=c.open[0]&&start+c.duration<=c.open[1])
 .map(c=>({...c,distance:distance(center,c.geo),interestMatches:c.tags.filter(t=>(profile.interests||[]).includes(t)).length}))
 .sort((a,b)=>filter.sort==='评分'?b.rating-a.rating:filter.sort==='价格'?(comparisonPrice(a,profile)??Infinity)-(comparisonPrice(b,profile)??Infinity):filter.sort==='距离'?a.distance-b.distance:b.interestMatches-a.interestMatches||a.distance-b.distance);
}
export function footprint(day,days,plan,kind){if(kind==='flight')return JSON.stringify([days[0].id,days.at(-1).id,day.date,day.items.map(x=>[x.time,x.title])]);const i=days.findIndex(d=>d.id===day.id);return JSON.stringify([day.id,day.date,days[i-1]?.id||0,day.items.map(x=>[x.time,x.title]),kind==='hotel'?null:plan.hotel[day.id]?.candidateId,kind==='transport'?plan.hotel[days[i-1]?.id]?.candidateId:null,plan.flights.outbound?.time,plan.flights.outbound?.arrival,plan.flights.inbound?.time]);}
export function recordState(record,day,days,plan){if(record.footprint&&record.footprint!==footprint(day,days,plan,record.kind))return '需重新核对';return record.status==='recorded'?'已预订 · 用户录入':record.status==='todo'?'待预订':'已加入行程';}
export function conflicts(day,days,plan,record){
 if(!['restaurant','activity'].includes(record.kind))return [];
 const start=minutes(record.time),end=start+record.duration,issues=[];if(!Number.isFinite(start))return ['请选择有效时间'];
 const overlap=(a,b)=>start<b+15&&end+15>a;
 for(const item of day.items){if(record.kind==='restaurant'&&/早餐|午餐|晚餐/.test(item.title))continue;const s=minutes(item.time),e=item.endTime?minutes(item.endTime):s+60;if(overlap(s,e))issues.push(item.time+' '+item.title);}
 const others=[...Object.values(plan.restaurant),...Object.values(plan.activity)];
 for(const item of others){if(item.dayId===day.id&&item.key!==record.key&&overlap(minutes(item.time),minutes(item.time)+item.duration))issues.push(item.time+' '+item.name);}
 const first=days[0],last=days.at(-1),arrival=plan.flights.outbound,returning=plan.flights.inbound;
 if(day.id===first.id&&arrival&&start<minutes(arrival.arrival)+90)issues.push('落地后需预留90分钟入境与接驳');
 if(day.id===last.id&&returning&&end>minutes(returning.time)-180)issues.push('返程起飞前需预留180分钟前往机场与值机');
 return issues;
}
export function freeTime(day,days,plan,record,open=[420,1320]){for(let n=open[0];n+record.duration<=open[1];n+=15)if(!conflicts(day,days,plan,{...record,time:clock(n)}).length)return clock(n);return null;}
export function reservations(plan){return [...Object.values(plan.flights),...Object.values(plan.transport),...Object.values(plan.hotel),...Object.values(plan.restaurant),...Object.values(plan.activity)].filter(Boolean);}

export function providerSearch(kind,day,profile,detail={}){const category={hotel:'酒店 预订',restaurant:'餐厅 预约',activity:'特色体验 门票 预约',transport:'交通 班次 预订',flight:'机票 航班'}[kind];const query=[kind==='flight'?detail.origin:'',kind==='flight'?profile.destination:day.place,kind==='flight'?'':day.geo?.anchor,category,detail.dateISO||'',detail.checkout||'',detail.people?detail.people+'人':'',detail.mode||''].filter(Boolean).join(' ');return 'https://www.google.com/search?q='+encodeURIComponent(query);}
