import {invoke} from './bridge';
export const serviceCache={flights:[],routes:[],candidates:[],weather:{}};
let cacheGeneration=0;
export function resetServiceCache(){cacheGeneration++;serviceCache.flights=[];serviceCache.routes=[];serviceCache.candidates.splice(0);for(const key of Object.keys(serviceCache.weather))delete serviceCache.weather[key];}
export const routeQueryKey=query=>JSON.stringify([query.fromName||'',query.toName||'',query.from?.lat??null,query.from?.lon??null,query.to?.lat??null,query.to?.lon??null,query.date||'',query.time||'']);
const url=value=>{try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password;}catch{return false;}};
const finite=value=>typeof value==='number'&&Number.isFinite(value);
const coordinates=value=>finite(value?.lat)&&finite(value?.lon)&&Math.abs(value.lat)<=85&&Math.abs(value.lon)<=180;
export function parseServiceResults(answer,kind){
  let data;try{data=JSON.parse(String(answer).replace(/^```(?:json)?\s*/,'').replace(/\s*```$/,''));}catch{throw new Error('没有收到可核验的结构化结果，请在旅行 AI 中查看原始回答。');}
  if(!Array.isArray(data.results)||data.results.length>50)throw new Error('查询结果格式无效。');
  return data.results.filter(row=>row&&typeof row.id==='string'&&typeof row.name==='string'&&url(row.source_url)&&typeof row.checked_at==='string'&&Number.isFinite(Date.parse(row.checked_at))&&Date.parse(row.checked_at)<=Date.now()+300000&&row.name.length<=240&&row.id.length<=100)
    .filter(row=>row.price==null||finite(row.price)&&row.price>=0)
    .filter(row=>row.price==null||/^[A-Z]{3}$/.test(row.priceCurrency||''))
    .map(row=>({...row,geo:coordinates(row.geo)?row.geo:null,kind,source:row.source_url,sourceUrl:row.source_url,price:row.price??null,rating:finite(row.rating)&&row.rating>=0&&row.rating<=5?row.rating:null,
      capacity:Number.isInteger(row.capacity)&&row.capacity>0?row.capacity:null,tags:Array.isArray(row.tags)?row.tags:[],amenities:Array.isArray(row.amenities)?row.amenities:[],diets:Array.isArray(row.diets)?row.diets:[]}));
}
export async function searchServices(kind,query,isCurrent=()=>true){
  const generation=cacheGeneration;
  const schema=kind==='flight'?'id,name,source_url,checked_at,date,time,arrivalDate,arrival,duration,price,priceCurrency,carrier,flightNumber,from,to,stops,originOffset,destinationOffset':
    kind==='route'?'id,name,source_url,checked_at,mode,duration,price,priceCurrency,distance,line,stops:[{name,time,instruction}],departure,date':
    kind==='weather'?'id,name,source_url,checked_at,temperature,condition,hours:[{time,temperature,condition}]':
    'id,name,label,source_url,checked_at,geo:{lat,lon},price,priceCurrency,rating,capacity,tags,amenities,diets,meal,open,duration,stars';
  const response=await invoke('ask',{question:'请检索公开资料，只提供查到且有来源的信息，不执行购买、预约或设备操作。查询：'+JSON.stringify({kind,...query})+
    '\n仅返回 JSON：{"results":[]}。每项字段：'+schema+'。缺失字段为 null。不要估造班次、价格、评分、坐标或房态；查不到返回空数组。来源必须为实际检索的 https 页面，checked_at 为真实查询日期。'});
  if(!isCurrent()||generation!==cacheGeneration)throw new Error('行程已切换，查询结果未写入。');
  if(response.hasActions)throw new Error('请先在首页对话中查看待确认操作。');
  const rows=parseServiceResults(response.answer,kind).map(row=>kind==='route'?{...row,queryKey:routeQueryKey(query)}:row);
  if(kind==='flight')serviceCache.flights=rows.filter(row=>row.date&&/^\d\d:\d\d$/.test(row.time||'')&&row.arrivalDate&&/^([01]\d|2[0-3]):[0-5]\d$/.test(row.arrival||'')&&finite(row.duration)&&row.duration>0);
  else if(kind==='route')serviceCache.routes=rows.filter(row=>Array.isArray(row.stops)&&finite(row.duration)&&row.duration>=0);
  else if(kind==='weather')serviceCache.weather[query.dayId]=rows[0]||null;
  else serviceCache.candidates.splice(0,serviceCache.candidates.length,...serviceCache.candidates.filter(row=>row.kind!==kind),...rows);
  return rows;
}
export function displayServicePrice(value,currency=''){return value==null?'费用待核对':(currency?currency+' ':'')+Number(value).toLocaleString();}
export function displayServiceDistance(value){return Number.isFinite(value)?value.toFixed(1)+' km':'距离待核对';}
