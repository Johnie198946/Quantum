const labels={flights:'航班',transport:'当地交通',hotel:'住宿',restaurant:'餐饮',activity:'体验'};
const keys={dayId:'所在日',dateISO:'日期',time:'期望时刻',arrival:'来源抵达时刻',arrivalDate:'抵达日期',people:'人数',pax:'人数',price:'来源报价',priceCurrency:'报价币种',reference:'已有订单凭据',channel:'预订渠道',source:'资料来源',sourceUrl:'资料来源',checkout:'退房日期',from:'出发地',to:'抵达地'};
export function preparationDescription(profile){
 const plan=profile.servicePlan||{},lines=[];
 for(const [kind,label] of Object.entries(labels))for(const [id,row] of Object.entries(plan[kind]||{}).sort(([a],[b])=>a.localeCompare(b))){
  if(!row||typeof row!=='object')continue;
  const status=row.status==='recorded'?'已有预订（用户录入）':row.status==='todo'?'待预订':'意向安排，未完成预订';
  lines.push(`${label} ${row.name||id} · ${status}`,...Object.entries(keys).filter(([key])=>row[key]!=null&&row[key]!=='').map(([key,label])=>`${label}：${row[key]}`));
 }
 const flight=plan.filters?.flight;
 if(flight){const selected={};for(const key of ['origin','routeCities','returnCity','outDate','backDate','outTime','backTime','pax','preferences','transfer'])if(flight[key]!=null&&flight[key]!==''&&(!Array.isArray(flight[key])||flight[key].length))selected[key]=flight[key];if(Object.keys(selected).length)lines.push('航班筛选与期望（不代表已确认班次）：'+JSON.stringify(selected));}
 return lines.length?'交通与预订补充：仅意向或用户录入的已有订单，不执行购票/预约；制作必须保留这些条件。\n'+lines.join('\n'):'';
}

export function personalState(state){const {travelDocument,...profile}=state.profile;return {version:1,...state,profile,days:state.days.map(({image,...day})=>day),extraCards:state.extraCards.map(({image,...card})=>card)};}
