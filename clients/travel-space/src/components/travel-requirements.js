export const interestChoices=['自然风光','温泉','当地美食','购物','徒步','小众'];
export function seedRequirements(text){
 const duration=text.match(/(?:玩|旅行|去|待|住)?\s*(\d{1,2})\s*[天日]/)?.[1];
 const count=text.match(/(\d{1,2})\s*[人位]/)?.[1];
 const rawDate=text.match(/\d{4}-\d{2}-\d{2}/)?.[0];
 const parsed=rawDate?new Date(rawDate+'T00:00:00Z'):null;
 const date=parsed&&Number.isFinite(parsed.getTime())&&parsed.toISOString().slice(0,10)===rawDate?rawDate:null;
 const origin=text.match(/从([^，,。\s]{1,12}?)(?:出发|飞|去)/)?.[1]||null;
 const budget=/经济|省钱/.test(text)?'经济':/舒适/.test(text)?'舒适':null;
 const pace=/轻松|慢慢|不赶/.test(text)?'轻松':/充实|多看/.test(text)?'充实':null;
 const transport=/自驾/.test(text)?'自驾':/公共交通|公交|巴士/.test(text)?'公共交通':/包车/.test(text)?'包车':null;
 const monetary=text.match(/(?:预算|人均)[^，,。\d]{0,6}(\d{1,3}(?:,\d{3})+|\d{1,7}(?:\.\d{1,2})?)/i),amount=monetary?.[1].replace(/,/g,'');
 const moneyText=monetary?text.slice(monetary.index,monetary.index+monetary[0].length+12).split(/[，。；;]/)[0]:'';
 const currency=amount?(/美元|USD/i.test(moneyText)?'美元':/日元|JPY/i.test(moneyText)?'日元':/欧元|EUR/i.test(moneyText)?'欧元':/人民币|CNY/i.test(moneyText)?'人民币':null):null;
 const interestText=text.replace(/不(?:想|要)?(?:吃|去|泡|看|逛|爬|徒步|购物|喜欢)[^，,。；;\n]*/g,'');
 const hints={自然风光:/火山|观景|自然|山海|风景/,温泉:/温泉|泡汤/,当地美食:/美食|吃|海鲜/,购物:/购物|买|逛街/,徒步:/徒步|爬山|登山/,小众:/小众|人少/};
 return {date:date||null,duration:duration&&Number(duration)>0&&Number(duration)<=30?Number(duration):null,count:count&&Number(count)>0&&Number(count)<=20?Number(count):null,origin,budget,pace,transport,amount:amount||null,currency,interests:interestChoices.filter(x=>hints[x].test(interestText)),interestsDecided:interestChoices.some(x=>hints[x].test(interestText)),notes:[]};
}
export function destinationFrom(text){return text.includes('鹿儿岛')?'鹿儿岛':text.replace(/^(我)?(想要|想|要)?(去|到)/,'').split(/[，,。\s\d]/)[0].slice(0,16)||'这趟旅行';}
export function mergeRequirementText(draft,text){
 const found=seedRequirements(text),next={...draft,notes:[...draft.notes,text]};
 for(const key of ['date','duration','count','origin','budget','pace','transport','amount','currency'])if(found[key])next[key]=found[key];
 if(found.interests.length){next.interests=[...new Set([...draft.interests,...found.interests])];next.interestsDecided=true;}
 if(/轻松|慢慢|不赶/.test(text))next.pace='轻松';
 if(/自驾/.test(text))next.transport='自驾';
 if(/公共交通|公交|巴士/.test(text))next.transport='公共交通';
 return next;
}
export function requirementReady(draft,step){
 return step===0?['date','duration','count','origin'].every(key=>!!draft[key]):step===1?['budget','pace','transport'].every(key=>!!draft[key]):draft.interestsDecided;
}
export function deferRequirements(draft,step){
 const next={...draft};for(const key of step===0?['date','duration','count','origin']:step===1?['budget','pace','transport']:[])if(!next[key])next[key]='未定';
 if(step===2)next.interestsDecided=true;return next;
}
export function profileFromRequirements(profile,draft){
 let dates='日期未定',dateRange;
 if(draft.date&&draft.date!=='未定'){
  const start=new Date(draft.date+'T00:00:00Z'),end=new Date(start);
  if(Number.isFinite(draft.duration))end.setUTCDate(end.getUTCDate()+draft.duration-1);
  const label=d=>(d.getUTCMonth()+1)+'月'+d.getUTCDate()+'日';dates=Number.isFinite(draft.duration)?label(start)+' — '+label(end):label(start)+'出发';
  dateRange=[draft.date,end.toISOString().slice(0,10)];
 }
 return {...profile,requirements:draft,requirementsConfirmed:true,dates,dateRange,duration:draft.duration,origin:draft.origin,amount:draft.amount||profile.amount||'',currency:draft.currency||profile.currency,count:Number.isFinite(draft.count)?draft.count+'人':'人数未定',party:draft.count===1?'一个人':draft.count==='未定'?'同行未定':'同行',budget:draft.budget,pace:draft.pace,transport:draft.transport,interests:draft.interests,additional:[...new Set([...draft.notes,profile.manualAdditional].filter(Boolean)),'出发地：'+draft.origin,'交通：'+draft.transport,'天数：'+(Number.isFinite(draft.duration)?draft.duration+'天':'未定')].join('；')};
}
