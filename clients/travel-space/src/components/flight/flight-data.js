import {serviceCache} from '../../production/service-provider';
import {isoAdd,clock,minutes} from '../services/planning';
export const defaultPreferences=['直达优先','一次中转','票价最便宜','红眼航班','不坐廉航','需要携带宠物'];
export const money=n=>Number.isFinite(n)?'¥'+n.toLocaleString('zh-CN'):'费用待核对';
export const dateText=d=>d?d.slice(5).replace('-','月')+'日':'选择日期';
export function dayMinute(date,total){const offset=Math.floor(total/1440),minute=((total%1440)+1440)%1440;return {date:isoAdd(date,offset),time:clock(minute)};}
export function flightWindow({date,time,origin,destination,direction='outbound'}){
 return serviceCache.flights.filter(f=>f.date===date&&f.from===(direction==='outbound'?origin:destination)&&f.to===(direction==='outbound'?destination:origin));
}
export function nearbyDayFares(query){if(!query.date)return [];return [-3,-2,-1,0,1,2,3].map(offset=>{const date=isoAdd(query.date,offset),flights=flightWindow({...query,date}).filter(f=>f.price!=null&&f.priceCurrency);return {date,offset,flight:flights.reduce((a,b)=>!a||b.priceCurrency===a.priceCurrency&&b.price<a.price?b:a,null)};});}
export function transferWindow(){return serviceCache.routes.filter(r=>r.kind==='transfer');}
