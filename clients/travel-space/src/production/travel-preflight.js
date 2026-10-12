import {images} from '../data';

const secureURL=value=>{try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password;}catch{return false;}};
export function parseDiscovery(answer){
  let data;try{data=JSON.parse(String(answer).replace(/^```(?:json)?\s*/,'').replace(/\s*```$/,''));}catch{throw new Error('景点资料暂未整理好，请重试或补充想法。');}
  if(!Array.isArray(data.places)||data.places.length>30)throw new Error('景点资料格式暂不可用，请重试。');
  const seen=new Set();
  const places=data.places.filter(p=>p&&typeof p.id==='string'&&p.id.length<=100&&typeof p.name==='string'&&p.name.length<=240&&secureURL(p.source_url)&&Number.isFinite(Date.parse(p.checked_at))&&Date.parse(p.checked_at)<=Date.now()+300000)
    .filter(p=>{if(seen.has(p.id))return false;seen.add(p.id);return true;})
    .map(p=>({id:p.id,name:p.name,area:String(p.area||'地址待核对').slice(0,500),short:String(p.short||'').slice(0,300),detail:String(p.detail||'详情待核对').slice(0,6000),
      sourceUrl:p.source_url,checkedAt:p.checked_at,image:secureURL(p.photo_url)?p.photo_url:images.neutral,imageSource:secureURL(p.photo_url)?'来源照片':'风景示意',
      geo:Number.isFinite(p.lat)&&Number.isFinite(p.lon)&&Math.abs(p.lat)<=85&&Math.abs(p.lon)<=180?{lat:p.lat,lon:p.lon}:null}));
  if(!places.length)throw new Error('还没有查到可核验的景点资料，可以继续补充想去的区域后重试。');
  return {summary:String(data.summary||'按这些想法，先收集想去的风景。').slice(0,4000),places};
}

export function draftDays(profile,places){
  const n=Number(profile.requirements?.duration||profile.duration),count=Number.isInteger(n)&&n>0&&n<=30?n:Math.max(1,places.length);
  const start=profile.dateRange?.[0],valid=start&&/^\d{4}-\d{2}-\d{2}$/.test(start)&&Number.isFinite(Date.parse(start));
  return Array.from({length:count},(_,i)=>{
    const p=places[i],date=valid?new Date(Date.parse(start+'T00:00:00Z')+i*86400000).toISOString().slice(0,10):null;
    return {id:'draft-day-'+(i+1),order:i+1,name:p?.name||'留给接下来安排的时间',place:p?.area||profile.destination,
      date:date||'日期未定',dateISO:date,image:p?.image||images.neutral,imageSource:p?.imageSource||'风景示意',geo:p?.geo||null,
      provisional:true,items:p?[{id:'draft-place-'+p.id,title:p.name,description:p.detail,time:'',endTime:'',kind:'experience',status:'意向安排',source_ids:[p.id]}]:[]};
  });
}

export function discoveryPrompt(profile,description){
  return '先收集这趟旅行的景点灵感，不创建工作流、不生成完整日程、不执行购买或预订。请实际检索公开资料并返回 JSON：'+
    '{"summary":"旅行需求总结","places":[{"id":"稳定标识","name":"景点名称","area":"地址或区域","short":"一句话介绍","detail":"可核验的介绍与季节限制","source_url":"https 来源页","checked_at":"实际查询日期","lat":null,"lon":null,"photo_url":null}]}。最多12处。未知坐标和照片为null；没有查到的来源不填写，不能用其他目的地示例替代。\n'+description;
}
