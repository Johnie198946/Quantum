import {invoke} from '../production/bridge';
export const destinations={};
export let mapExtent={west:-180,east:180,south:-80,north:80};
export function setMapDays(days){
 const points=days.map(d=>d.geo).filter(p=>Number.isFinite(p?.lat)&&Number.isFinite(p?.lon));
 if(!points.length)return;
 const lats=points.map(p=>p.lat),lons=points.map(p=>p.lon),lat=Math.max(...lats)-Math.min(...lats),lon=Math.max(...lons)-Math.min(...lons);
 mapExtent={west:Math.min(...lons)-Math.max(lon*.2,.02),east:Math.max(...lons)+Math.max(lon*.2,.02),south:Math.min(...lats)-Math.max(lat*.2,.02),north:Math.max(...lats)+Math.max(lat*.2,.02)};
}
export const dayNumber=day=>day.order??day.id;
const mercator=lat=>Math.log(Math.tan(Math.PI/4+Math.min(85,Math.max(-85,lat))*Math.PI/360));
export function project(point){if(!point)return {x:NaN,y:NaN};return {x:(point.lon-mapExtent.west)/(mapExtent.east-mapExtent.west)*100,y:(mercator(mapExtent.north)-mercator(point.lat))/(mercator(mapExtent.north)-mercator(mapExtent.south))*100};}
export function routeThrough(days){let connected=false;return days.map(day=>{if(!day.geo){connected=false;return '';}const p=project(day.geo),command=connected?'L':'M';connected=true;return command+' '+p.x+' '+p.y;}).join(' ');}
const xml=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
export function routeKML(days){const known=days.filter(d=>d.geo);if(!known.length)throw new Error('尚无已确认的地点坐标。');return '<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>旅行地点</name>'+known.map(d=>'<Placemark><name>'+xml(d.place)+'</name><description>'+xml(d.date||'日期未定')+'</description><Point><coordinates>'+d.geo.lon+','+d.geo.lat+',0</coordinates></Point></Placemark>').join('')+'</Document></kml>';}
export function downloadKML(days){return invoke('export',{content:routeKML(days),filename:'travel-route.kml'});}
export function navigationURL(day){return day.geo?'https://www.google.com/maps/dir/?api=1&destination='+day.geo.lat+','+day.geo.lon:'https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(day.place);}
