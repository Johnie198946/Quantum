import React from 'react';
import NativeMap from '../../production/NativeMap';
import {mapExtent} from '../mapRoute';
export default function RouteMap({from,to,fromName,toName,mode,alternate=false}){
 if(!from||!to)return <div className="route-map-empty">确定起终点后显示路线地图</div>;
 const merc=lat=>Math.log(Math.tan(Math.PI/4+lat*Math.PI/360)),cx=(from.lon+to.lon)/2,cy=(merc(from.lat)+merc(to.lat))/2;
 const span=Math.max(Math.abs(from.lon-to.lon)*Math.PI/180,Math.abs(merc(from.lat)-merc(to.lat))*1.6,.025*Math.PI/180)*1.5,scale=1000/span;
 const p=geo=>({x:500+(geo.lon-cx)*Math.PI/180*scale,y:300+(cy-merc(geo.lat))*scale});
 const a=p(from),b=p(to),bounds={west:cx-span*180/Math.PI/2,east:cx+span*180/Math.PI/2,
 south:(2*Math.atan(Math.exp(cy-300/scale))-Math.PI/2)*180/Math.PI,north:(2*Math.atan(Math.exp(cy+300/scale))-Math.PI/2)*180/Math.PI};
 const path=offset=>`M${a.x} ${a.y} Q${(a.x+b.x)/2+offset} ${(a.y+b.y)/2+offset} ${b.x} ${b.y}`;
 return <figure className="route-map"><NativeMap className="production-route-base" bounds={bounds}/><svg viewBox="0 0 1000 600" role="img" aria-label={fromName+'到'+toName+'，'+mode+'路线示意'}><path d={path(alternate?-65:70)} stroke="#adb4ae" strokeWidth="12" fill="none"/><path d={path(alternate?70:-65)} stroke="#fafbf5" strokeWidth="20" fill="none"/><path d={path(alternate?70:-65)} stroke="#526c73" strokeWidth="10" fill="none" strokeDasharray={['步行','单车'].includes(mode)?'14 10':undefined}/>{[a,b].map((point,i)=><g key={i}><circle cx={point.x} cy={point.y} r="25" fill={i?'#526c73':'#f8faf2'} stroke="#526c73" strokeWidth="6"/><text x={point.x} y={point.y+10} fill={i?'#fff':'#3a5052'} fontSize="28" textAnchor="middle">{i?'B':'A'}</text></g>)}</svg><figcaption><span>A {fromName}</span><span>B {toName}</span></figcaption><a href="https://maps.apple.com" target="_blank" rel="noreferrer">Apple 地图 · 连线仅示意</a></figure>;
}
