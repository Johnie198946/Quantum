import {displayServiceDistance} from '../../production/service-provider';
import {filterCandidates,comparisonPrice} from './planning';
export const hotelTags=['靠近兴趣点','含早餐','免费取消'];
export function budgetFromText(text){
 const m=String(text||'').match(/(?:预算|不超过|最多|每晚|上限|≤|¥|￥)\s*(?:¥|￥)?\s*(\d+(?:\.\d+)?)\s*(万|千|k)?/i);
 if(!m)return null;const value=Number(m[1])*(m[2]==='万'?10000:m[2]==='千'||m[2]?.toLowerCase()==='k'?1000:1);return value>0?value:null;
}
export function hotelReferences({center,filter,profile,people}){
 const tags=filter.preferences??hotelTags,budget=budgetFromText(tags.join(' '));
 return filterCandidates('hotel',center,{...filter,maxPrice:filter.maxPrice||budget||'',sort:filter.sort||'兴趣'},profile,'午餐','12:30',Math.min(people,2))
 .filter(c=>(!tags.includes('含早餐')||c.amenities.includes('早餐'))&&(!tags.includes('免费取消')||c.amenities.includes('免费取消'))&&(!tags.includes('温泉')||c.amenities.includes('温泉')));
}
export function assessHotels({selected,available,filter,profile,note,center,nextPlace}){
 const budget=budgetFromText(note)||Number(filter.maxPrice)||budgetFromText((filter.preferences||[]).join(' ')),tags=filter.preferences||hotelTags;
 const wantSpa=tags.includes('温泉')||/想要温泉|需要温泉/.test(note),wantCancel=tags.includes('免费取消')||/必须免费取消|需要免费取消/.test(note),wantBreakfast=tags.includes('含早餐')||/需要早餐|必须含早餐/.test(note);
 const ranked=selected.map(c=>{
  const price=comparisonPrice(c,profile),currency=profile.budgetLedger?.baseCurrency||profile.currency||'CNY';
  const reasons=[],concerns=[],eligible=available.some(x=>x.id===c.id)&&(!budget||price!=null&&price<=budget)&&(!wantSpa||c.amenities.includes('温泉'))&&(!wantCancel||c.amenities.includes('免费取消'))&&(!wantBreakfast||c.amenities.includes('早餐'));
  if(c.interestMatches)reasons.push('贴合'+c.tags.filter(t=>profile.interests.includes(t)).join('、')+'兴趣');
  (Number.isFinite(c.distance)?reasons:concerns).push('距'+center.label+' · '+displayServiceDistance(c.distance));
  if(budget){if(price===null)concerns.push('报价或换算汇率待核对，暂不能与预算比较');else (price<=budget?reasons:concerns).push(price<=budget?'每晚在 '+currency+' '+budget.toLocaleString()+' 预算内':'超过每晚 '+currency+' '+budget.toLocaleString()+' 预算');}
  if(wantSpa)(c.amenities.includes('温泉')?reasons:concerns).push(c.amenities.includes('温泉')?'有温泉设施资料':'未提供温泉设施');
  if(wantCancel)(c.amenities.includes('免费取消')?reasons:concerns).push(c.amenities.includes('免费取消')?'资料标注免费取消条件':'不满足免费取消要求');
  if(wantBreakfast)(c.amenities.includes('早餐')?reasons:concerns).push(c.amenities.includes('早餐')?'资料标注早餐':'不满足含早餐要求');
  if(!available.some(x=>x.id===c.id))concerns.push('不符合当前半径、星级、人数或标签条件');
  if(/安静|隔音|宠物|无障碍|儿童|亲子|停车|车站|交通|步行/.test(tags.join(' ')+note))concerns.push('安静、房型、停车、宠物及车站步行路线等补充条件需进一步核验');
  const score=c.interestMatches*22+Math.max(0,30-c.distance*7)+(budget&&price!=null?Math.max(0,20-price/budget*10):0)+(wantSpa&&c.amenities.includes('温泉')?22:0)+(wantCancel&&c.amenities.includes('免费取消')?10:0)+c.rating*2;
  return {id:c.id,name:c.name,eligible,score,reasons,concerns,price:c.price};
 }).sort((a,b)=>Number(b.eligible)-Number(a.eligible)||b.score-a.score);
 const recommended=ranked.find(c=>c.eligible);
 return {recommended:recommended?.id||null,ranked,budget:budget||null,summary:recommended?'建议优先考虑'+recommended.name+'，兼顾兴趣、位置与已明确的住宿条件。':'待选酒店暂未满足全部明确条件，建议调整候选或要求后再次比较。',context:'以'+center.label+'为中心，照顾下一站'+nextPlace+'；预算偏好为'+(profile.budget||'待补充')+'。',input:note||'尚未补充其他要求',scope:'候选字段对照；房态、隔音、价格及退改细则需以实际预订页面核对。'};
}
