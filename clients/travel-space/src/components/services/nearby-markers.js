export function visibleMapMarkers(points,selectedId,minGap=150){
 const visible=[];
 const ordered=[...points].sort((a,b)=>Number(b.id===selectedId)-Number(a.id===selectedId));
 for(const point of ordered){
  if(!Number.isFinite(point.x)||!Number.isFinite(point.y)||point.x<40||point.x>960||point.y<40||point.y>580)continue;
  if(point.id===selectedId||!visible.some(other=>Math.hypot(point.x-other.x,point.y-other.y)<minGap))visible.push(point);
 }
 return new Set(visible.map(point=>point.id));
}
