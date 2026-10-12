import {serviceCache,routeQueryKey} from '../../production/service-provider';
import {distance,minutes,clock,isoAdd} from './planning';
export const routeModes=[['公交车','bus'],['地铁','train'],['火车','train'],['出租车','taxi'],['自驾','car'],['单车','leaf'],['步行','person'],['渡轮','globe']];
export const transferMode=value=>value==='地铁/火车'?'火车':value==='出租'?'出租车':value;
export const airportGeo=null;
export const validRouteGeo=geo=>!!geo&&Number.isFinite(geo.lat)&&Number.isFinite(geo.lon)&&Math.abs(geo.lat)<=85&&Math.abs(geo.lon)<=180;
export const routeModeIcon=mode=>routeModes.find(([name])=>name===mode)?.[1]||(/船|轮|艇/.test(mode)?'globe':/直升机|飞机|航空/.test(mode)?'plane':/铁|车站/.test(mode)?'train':'car');
export function inheritedTransfer(day,days,plan,profile){
 const first=day.id===days[0]?.id,flight=first?plan.flights.outbound:null,record=first?plan.transport[day.id+'-airport']:null;
 const total=flight?minutes(flight.arrival)+45:480,time=record?.time||clock(total%1440),date=record?.date||record?.dateISO||flight&&isoAdd(flight.arrivalDate,Math.floor(total/1440))||'';
 return {mode:transferMode(first&&plan.filters.flight?.transfer||flight?.transfer||record?.mode)||(profile.transport==='自驾'?'自驾':'公交车'),time,date,flight,record};
}
const text=value=>typeof value==='string'?value.trim():'';
const numeric=(value,fallback=0)=>value!==''&&value!==null&&value!==undefined&&Number.isFinite(Number(value))?Number(value):fallback;
function structuredRows({settings={},generatedRoutes,fromName,toName}){
 const data=generatedRoutes??settings.generatedRoutes;
 if(data===undefined||data===null)return null;
 const key=fromName+'→'+toName,keySpaced=fromName+' → '+toName;
 const scoped=data.byEndpoints?data.byEndpoints[key]??data.byEndpoints[keySpaced]??[]:data[key]??data[keySpaced]??data;
 const flatten=(node,inheritedMode='',inherited={})=>{
  if(Array.isArray(node))return node.flatMap(item=>flatten(item,inheritedMode,inherited));
  if(!node||typeof node!=='object')return [];
  const mode=text(node.mode||node.name||inheritedMode);
  if(node.modes)return flatten(node.modes);
  if(node.routes||node.options)return flatten(node.routes||node.options,mode,{...inherited,icon:node.icon,label:node.label,source:node.source});
  if(node.route&&typeof node.route==='object')return flatten({...node,...node.route,route:undefined,mode:node.mode||inheritedMode},inheritedMode,inherited);
  if(mode)return [{...inherited,...node,mode}];
  return Object.entries(node).flatMap(([name,rows])=>flatten(rows,name));
 };
 return flatten(scoped);
}
function normalizeRoute(raw,args,index){
 const mode=text(raw.mode),start=minutes(args.time);
 const stops=(Array.isArray(raw.stops)?raw.stops:Array.isArray(raw.segments)?raw.segments:[]).filter(stop=>stop&&typeof stop==='object').map(stop=>({
  name:text(stop.name||stop.title||stop.location),time:text(stop.time||stop.departure),icon:text(stop.icon)||routeModeIcon(mode),instruction:text(stop.instruction||stop.description||stop.detail)
 })).filter(stop=>stop.name||stop.instruction);
 const sourceStart=minutes(raw.time||raw.departure||stops[0]?.time),sourceEnd=minutes(raw.arrival||stops.at(-1)?.time);
 const inferred=Number.isFinite(sourceStart)&&Number.isFinite(sourceEnd)?(sourceEnd-sourceStart+1440)%1440:NaN;
 const duration=Math.round(numeric(raw.duration??raw.durationMinutes,inferred)),price=numeric(raw.price??raw.cost,NaN);
 if(!mode||!Number.isFinite(start)||!Number.isFinite(duration)||duration<0||Number.isFinite(price)&&price<0||!stops.length)return null;
 if(!Number.isFinite(sourceStart)||sourceStart!==start)return null;
 const total=sourceStart+duration;
 return {...raw,id:text(raw.id)||mode+'-provided-'+index,source:text(raw.source)||'用户提供',mode,icon:text(raw.icon)||routeModeIcon(mode),duration,price:Number.isFinite(price)?price:null,
 distance:Number.isFinite(raw.distance)&&raw.distance>=0?raw.distance:null,arrival:text(raw.arrival)||clock(total%1440),arrivalDate:raw.arrivalDate||isoAdd(args.date,Math.floor(total/1440)),
 stops,walk:numeric(raw.walk,null),wait:numeric(raw.wait,null),transfer:numeric(raw.transfer,null),ferry:numeric(raw.ferry,null),label:text(raw.label)||'路线 '+(index+1),line:text(raw.line)||mode+'路线'};

}
export function availableRouteModes(args){
 if(!validRouteGeo(args.from)||!validRouteGeo(args.to))return [];
 const provided=structuredRows(args);
 if(provided!==null){
  const seen=new Set();return provided.flatMap((row,index)=>{const normalized=normalizeRoute(row,args,index);if(!normalized||seen.has(normalized.mode))return [];seen.add(normalized.mode);return [[normalized.mode,normalized.icon]];});
 }
 return [...new Set(serviceCache.routes.filter(r=>r.queryKey===routeQueryKey(args)).map(r=>r.mode))].map(name=>[name,routeModeIcon(name)]);
}
export function routeOptions(args){
 const {mode,from,to,fromName,toName,time,date,water=false}=args;
 if(!validRouteGeo(from)||!validRouteGeo(to)||!Number.isFinite(minutes(time)))return [];
 const provided=structuredRows(args);
 if(provided!==null)return provided.filter(row=>row.mode===mode).map((row,index)=>normalizeRoute(row,args,index)).filter(Boolean);
 return serviceCache.routes.filter(r=>r.queryKey===routeQueryKey(args)&&r.mode===mode&&r.date===date&&r.departure===time).map((r,index)=>normalizeRoute(r,args,index)).filter(Boolean);
}
