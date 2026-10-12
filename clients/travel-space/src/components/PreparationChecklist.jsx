import FloatingField from './FloatingField';
import React from 'react';
import {useTravel} from '../TravelContext';
const topics=[
 {intro:'按自己的国籍、居住地与旅行目的逐项确认。',items:[['护照与身份资料','核对姓名、有效期及随身备份。'],['签证或入境资格','向适用的官方渠道确认当前要求并记录结果。'],['行程与住宿证明','准备往返行程、住宿地址与联系方式。'],['保险与紧急联络','保存保险资料和可信联系人的联系方式。']]},
 {intro:'围绕已选路线，把需要预约和容易错过的时间留下来。',items:[['往返与接驳','核对航班、车站、码头与衔接时刻。'],['营业与最后入场','按出行日确认景点和餐厅营业时间。'],['票券与取还车','确认预约、取票、取还车点与取消条件。'],['离线资料','保存地址、地图和重要预约凭据。']]},
 {intro:'把入住和泡汤所需的信息放在同一处。',items:[['入住与退房','核对人数、房型、到达时间与延迟入住。'],['温泉使用规则','确认开放时段、预约和个人适用条件。'],['餐饮与设施','核对早餐、过敏、停车及无障碍需求。'],['支付与取消','保存费用构成、取消期限和联系渠道。']]},
 {intro:'临近出发和当天再次查看官方最新信息。',items:[['天气与穿着','记录最新预报与所需装备。'],['火山与区域公告','核对官方通告和所选区域开放状况。'],['渡轮与交通变动','确认是否停航、改班或关闭道路。'],['备用安排','留下室内备选与返程衔接方式。']]}
];
export default function PreparationChecklist({index}){
 const {profile,setProfile}=useTravel(),topic=topics[index],value=profile.preparations?.[index]||{},checked=value.checked||[],update=patch=>setProfile(prev=>({...prev,preparations:{...prev.preparations,[index]:{...prev.preparations?.[index],...patch}}}));
 return <section className="preparation-checklist"><p>{topic.intro}</p><div className="todo-progress"><strong>{checked.length} / {topic.items.length}</strong><span>已确认</span><progress aria-label="待办确认进度" value={checked.length} max={topic.items.length}/></div><ul>{topic.items.map(([title,text],i)=><li key={title}><label><input type="checkbox" aria-label={'确认'+title} checked={checked.includes(i)} onChange={()=>update({checked:checked.includes(i)?checked.filter(x=>x!==i):[...checked,i],updatedAt:new Date().toISOString()})}/><span><strong>{title}</strong><small>{text}</small></span></label></li>)}</ul><label>确认记录<FloatingField as="textarea" aria-label="待办确认记录" rows={3} value={value.notes||''} placeholder="核验渠道、时间、联系人与待解决的问题" onChange={e=>update({notes:e.target.value})}/></label><label>资料来源<FloatingField type="url" aria-label="待办资料来源" placeholder="https://…" value={value.source||''} onChange={e=>update({source:e.target.value})}/></label>{/^https:\/\//.test(value.source||'')&&<a href={value.source} target="_blank" rel="noreferrer">打开记录的资料来源 ↗</a>}<p className="service-quiet-caption">由你核验后勾选。{value.updatedAt?'最近记录：'+new Date(value.updatedAt).toLocaleDateString('zh-CN'):''}</p></section>;
}
