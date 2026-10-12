import { dayNumber } from './mapRoute';
import React from 'react';
import RoutePlaceSurface from './RoutePlaceSurface';
import { images } from '../data';

export function activityPhoto(item,day){
  return item.image||(/城山|市区/.test(item.title)?images.sakurajima:day.image);
}
function playDescription(item){
  if(item.playDescription)return item.playDescription;
  if(/温泉/.test(item.title))return '先留一段时间休息，再按场所规则体验温泉。结束后慢慢补水、放松，不急着赶往下一站。';
  if(/午餐|餐|味/.test(item.title))return '在沿途找一处顺路的餐馆，坐下来慢慢吃一顿。餐后留一点散步的时间，再接着出发。';
  if(/前往|交通|返回/.test(item.title))return '把这段时间留给路上的风景。到达后先熟悉周边，给交通衔接和短暂休息留一点余量。';
  if(/园/.test(item.title))return '沿着小路慢慢走，停下来看看庭园与远处的风景。遇到喜欢的视角，可以多留一会儿拍照。';
  return '先慢慢走一段，把注意力留给眼前的风景。看到喜欢的地方就停下来，拍照、休息，按自己的节奏继续。';
}
export default function ActivityDetail({item,day,origin,onClose}){
  const time=item.time+(item.endTime?' — '+item.endTime:'');
  return <RoutePlaceSurface day={{...day,place:item.title,image:activityPhoto(item,day)}} origin={origin} photoMeta={'DAY '+String(dayNumber(day)).padStart(2,'0')+' / '+time} label={item.title+'玩法详情'} className="activity-photo-sheet" onClose={onClose}>
    <div className="detail-heading"><div><p className="eyebrow">{day.place} · {time}</p><h2>{item.title}</h2></div></div>
    <div className="activity-detail-copy"><p className="activity-intro">{item.description}</p><h3>怎么玩</h3><p>{playDescription(item)}</p></div>
  </RoutePlaceSurface>;
}
