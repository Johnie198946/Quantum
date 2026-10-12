import React from 'react';
import {motion} from 'motion/react';
import NativeMap from '../../production/NativeMap';
import {mapExtent} from '../mapRoute';
import {Icon} from '../UI';
import {visibleMapMarkers} from './nearby-markers';
import './revision68-services.css';
const R=6371,merc=lat=>R*Math.log(Math.tan(Math.PI/4+lat*Math.PI/360));
export default function NearbyMap({center,radius,results,selected,onSelect}){
 if(!Number.isFinite(center?.lat)||!Number.isFinite(center?.lon))return <figure className="nearby-map nearby-map-empty"><figcaption>地点确定后显示附近地图。</figcaption></figure>;
 const selectedPoint=results.find(c=>c.id===selected&&Number.isFinite(c.geo?.lat)&&Number.isFinite(c.geo?.lon)),camera=selectedPoint?{lat:(center.lat+selectedPoint.geo.lat)/2,lon:(center.lon+selectedPoint.geo.lon)/2}:center;
 const scale=220/(radius/Math.cos(center.lat*Math.PI/180)),cx=R*camera.lon*Math.PI/180,cy=merc(camera.lat);
 const point=p=>({x:500+(R*p.lon*Math.PI/180-cx)*scale,y:310+(cy-merc(p.lat))*scale});
 const centerPoint=point(center),bounds={west:(cx-500/scale)/R*180/Math.PI,east:(cx+500/scale)/R*180/Math.PI,
 south:(2*Math.atan(Math.exp((cy-310/scale)/R))-Math.PI/2)*180/Math.PI,north:(2*Math.atan(Math.exp((cy+310/scale)/R))-Math.PI/2)*180/Math.PI};
 const points=results.map(item=>Number.isFinite(item.geo?.lat)&&Number.isFinite(item.geo?.lon)?{...point(item.geo),id:item.id}:null),visible=visibleMapMarkers(points.filter(Boolean),selected);
 return <figure className="nearby-map service-poi-map" data-center={center.lat+','+center.lon} data-radius={radius} data-camera={camera.lat+','+camera.lon}><div className="nearby-canvas"><NativeMap className="production-nearby-base" bounds={bounds}/><svg viewBox="0 0 1000 620" preserveAspectRatio="none" role="img" aria-label={center.label+'附近地点地图，'+results.length+'处候选'}><circle cx={centerPoint.x} cy={centerPoint.y} r="220" fill="#f1f4ea25" stroke="#6c8c8050" strokeWidth="3"/><circle cx={centerPoint.x} cy={centerPoint.y} r="13" fill="#527c9a" stroke="white" strokeWidth="7"/></svg><div className="nearby-marker-layer">{results.map((item,index)=>{const p=points[index];return visible.has(item.id)&&<motion.button key={item.id} type="button" className={'nearby-map-marker poi-pin'+(selected===item.id?' is-selected':'')} aria-label={'地图标记'+(index+1)+'，'+item.name} aria-pressed={selected===item.id} animate={{left:p.x/10+'%',top:p.y/6.2+'%'}} transition={{duration:.3}} onClick={()=>onSelect(item)}><span className="poi-pin-glyph"><Icon name={item.kind==='hotel'?'bed':item.kind==='restaurant'?'dining':'ticket'} size={12}/></span><span className="poi-pin-title">{item.label||item.name}</span></motion.button>;})}</div></div><figcaption><span><i/> {center.label}</span><span>{results.length} 处{selectedPoint?' · 已聚焦':''}</span></figcaption><div className="nearby-legend">{results.map((item,index)=><button key={item.id} aria-label={'地图选择'+item.name} aria-pressed={selected===item.id} onClick={()=>onSelect(item)}><Icon name={item.kind==='hotel'?'bed':item.kind==='restaurant'?'dining':'ticket'} size={12}/><span>{item.label||item.name}</span></button>)}</div></figure>;
}
