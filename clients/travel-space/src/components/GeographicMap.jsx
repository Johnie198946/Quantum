import React from 'react';
import { motion, useReducedMotion } from 'motion/react';
import NativeMap from '../production/NativeMap';
import { destinations, project, routeThrough, dayNumber,mapExtent } from './mapRoute';
export default function GeographicMap({days,focus,animated=false,children}){
 const reduced=useReducedMotion(),path=routeThrough(days);
 return <div className="geographic-map" data-projection="EPSG:3857"><NativeMap className="geographic-base" bounds={mapExtent}/><svg className="geographic-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><defs><mask id={'route-reveal-'+(focus||'all')}><motion.path d={path} fill="none" stroke="white" strokeWidth="5" pathLength="1" strokeDasharray="1 1" initial={animated&&!reduced?{strokeDashoffset:1}:{strokeDashoffset:0}} animate={{strokeDashoffset:0}} transition={{duration:2.8,ease:'easeInOut',delay:.25}}/></mask></defs><g mask={'url(#route-reveal-'+(focus||'all')+')'}><path d={path} className="geo-route-underlay" fill="none"/><path d={path} className="geo-route-dashed" fill="none"/></g></svg>{!children&&days.filter(d=>d.geo).map(day=>{const p=project(day.geo||destinations[day.id]);return <span key={day.id} className={'geo-mini-dot'+(day.id===focus?' is-focus':'')} style={{left:p.x+'%',top:p.y+'%'}}><b>{dayNumber(day)}</b></span>;})}{children}<span className="geo-north" aria-hidden="true">N ↑</span><span className="geo-attribution">Apple 地图 · 连线为游览顺序</span></div>;
}
