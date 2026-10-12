import React,{useEffect,useLayoutEffect,useRef,useState} from 'react';
import {useReducedMotion} from 'motion/react';
import {images} from '../../data';
import LiquidCard from '../LiquidCard';
import {Icon,spring} from '../UI';
import './NoteCoverCarousel.css';

const covers=[['sakurajima','樱岛'],['senganen','仙岩园'],['ibusuki','指宿'],['kirishima','雾岛']];
const clamp=(value,min,max)=>Math.min(max,Math.max(min,value));

export default function NoteCoverCarousel({value,onChange}){
 const track=useRef(null),slots=useRef([]),buttons=useRef([]),gesture=useRef(null),touch=useRef(null),suppress=useRef(false),userScrolling=useRef(false),timer=useRef(null),initialized=useRef(false);
 const selected=Math.max(0,covers.findIndex(([key])=>key===value)),selectedRef=useRef(selected),changeRef=useRef(onChange);
 selectedRef.current=selected;changeRef.current=onChange;
 const [weights,setWeights]=useState([]),[nearest,setNearest]=useState(-1),[interaction,setInteraction]=useState('idle'),[dragging,setDragging]=useState(false),reduced=useReducedMotion();
 const transition=reduced?{duration:0}:spring;

 function centeredIndex(){const rail=track.current;if(!rail)return selectedRef.current;const center=rail.getBoundingClientRect().left+rail.clientWidth/2,distances=slots.current.map(slot=>Math.abs(slot.getBoundingClientRect().left+slot.offsetWidth/2-center));return distances.indexOf(Math.min(...distances));}
 function go(index,instant=false){const rail=track.current,slot=slots.current[index];if(!rail||!slot)return;const bounds=rail.getBoundingClientRect(),photo=slot.getBoundingClientRect(),left=clamp(rail.scrollLeft+photo.left+slot.offsetWidth/2-bounds.left-rail.clientWidth/2,0,rail.scrollWidth-rail.clientWidth);rail.scrollTo({left,behavior:instant||reduced?'instant':'smooth'});}
 function sample(x,kind){const distances=slots.current.map(slot=>{const bounds=slot.getBoundingClientRect();return Math.abs(bounds.left+slot.offsetWidth/2-x);});setWeights(distances.map(distance=>Math.max(0,1-distance/110)));setNearest(distances.indexOf(Math.min(...distances)));setInteraction(kind);}
 function clearProximity(){setWeights([]);setNearest(-1);setInteraction('idle');setDragging(false);}
 function cancelCommit(){clearTimeout(timer.current);userScrolling.current=false;}
 function settle(){clearTimeout(timer.current);timer.current=setTimeout(()=>{if(!userScrolling.current||gesture.current||touch.current)return;userScrolling.current=false;const index=centeredIndex();if(index<0)return;if(index!==selectedRef.current)changeRef.current?.(covers[index][0]);go(index);},160);}
 function choose(index){cancelCommit();if(index!==selectedRef.current)changeRef.current?.(covers[index][0]);go(index);}

 useLayoutEffect(()=>{const rail=track.current;if(!rail)return;const align=()=>{if(!gesture.current&&!touch.current&&!userScrolling.current)go(selectedRef.current,true);};const observer=new ResizeObserver(align);observer.observe(rail);align();return()=>observer.disconnect();},[]);
 useEffect(()=>{cancelCommit();go(selected,!initialized.current);initialized.current=true;},[value,reduced]);
 useEffect(()=>()=>clearTimeout(timer.current),[]);

 function startPointer(event){if(!event.isPrimary||event.button!==0)return;suppress.current=false;sample(event.clientX,event.pointerType==='touch'?'touch':'mouse');if(event.pointerType==='mouse'){cancelCommit();gesture.current={id:event.pointerId,x:event.clientX,y:event.clientY,left:track.current.scrollLeft,moved:false,currentX:event.clientX};}}
 function movePointer(event){const current=gesture.current;if(!current){if(event.pointerType==='mouse')sample(event.clientX,'mouse');return;}if(current.id!==event.pointerId)return;current.currentX=event.clientX;const dx=event.clientX-current.x,dy=event.clientY-current.y;if(!current.moved&&Math.abs(dx)>5&&Math.abs(dx)>Math.abs(dy)){current.moved=true;userScrolling.current=true;setDragging(true);track.current.style.scrollSnapType='none';track.current.setPointerCapture(event.pointerId);}if(current.moved){event.preventDefault();track.current.scrollLeft=current.left-dx;}sample(event.clientX,'mouse');}
 function finishPointer(event,cancel=false){const current=gesture.current;if(!current||current.id!==event.pointerId)return;gesture.current=null;track.current.style.scrollSnapType='';suppress.current=!cancel&&current.moved;if(track.current.hasPointerCapture(event.pointerId))track.current.releasePointerCapture(event.pointerId);clearProximity();if(cancel){cancelCommit();go(selectedRef.current);}else if(current.moved){go(centeredIndex());settle();}}
 function startTouch(event){const point=event.touches[0];if(!point)return;cancelCommit();suppress.current=false;touch.current={x:point.clientX,y:point.clientY,currentX:point.clientX,moved:false};sample(point.clientX,'touch');}
 function moveTouch(event){const current=touch.current,point=event.touches[0];if(!current||!point)return;current.currentX=point.clientX;const dx=Math.abs(point.clientX-current.x),dy=Math.abs(point.clientY-current.y);if(dx>5&&dx>dy){current.moved=true;userScrolling.current=true;}sample(point.clientX,'touch');}
 function finishTouch(cancel=false){const current=touch.current;touch.current=null;clearProximity();suppress.current=!cancel&&!!current?.moved;if(cancel){cancelCommit();go(selectedRef.current);}else if(current?.moved)settle();}
 function keyDown(event,index){const next=event.key==='ArrowRight'?(index+1)%covers.length:event.key==='ArrowLeft'?(index+covers.length-1)%covers.length:event.key==='Home'?0:event.key==='End'?covers.length-1:null;if(next===null)return;event.preventDefault();choose(next);buttons.current[next]?.focus({preventScroll:true});}

 return <section className="note-cover-carousel" aria-label="目的地封面" data-interaction={interaction}>
  <div className="note-cover-caption" aria-live="polite"><span>{covers[selected][1]}</span><small aria-label={'第'+(selected+1)+'张，共4张'}>{String(selected+1).padStart(2,'0')} / 04</small></div>
  <div ref={track} className={'cover-options note-cover-rail'+(dragging?' is-dragging':'')} role="group" aria-label="四张封面照片"
   onPointerDown={startPointer} onPointerMove={movePointer} onPointerUp={event=>finishPointer(event)} onPointerCancel={event=>finishPointer(event,true)} onLostPointerCapture={event=>finishPointer(event,true)} onPointerLeave={()=>{if(!gesture.current&&!touch.current)clearProximity();}}
   onTouchStart={startTouch} onTouchMove={moveTouch} onTouchEnd={()=>finishTouch()} onTouchCancel={()=>finishTouch(true)}
   onScroll={()=>{if(touch.current)sample(touch.current.currentX,'touch');else if(gesture.current)sample(gesture.current.currentX,'mouse');if(userScrolling.current)settle();}}>
   {covers.map(([key,label],index)=>{const active=selected===index,weight=weights[index]||0,scale=reduced?1:1+(active?.025:0)+weight*.13;return <div key={key} ref={element=>slots.current[index]=element} className="note-cover-slot">
    <button ref={element=>buttons.current[index]=element} type="button" className={'note-cover-option'+(active?' selected':'')+(nearest===index?' is-nearest':'')} aria-label={'封面'+key} aria-pressed={active} tabIndex={active?0:-1} data-cover={key} data-proximity={weight.toFixed(3)}
     onFocus={()=>{const slot=slots.current[index],bounds=slot?.getBoundingClientRect();if(bounds)sample(bounds.left+slot.offsetWidth/2,'keyboard');}} onBlur={()=>{if(!gesture.current&&!touch.current)clearProximity();}} onKeyDown={event=>keyDown(event,index)}
     onClick={event=>{if(suppress.current&&event.detail!==0){suppress.current=false;return;}suppress.current=false;choose(index);}}>
     <LiquidCard className="note-cover-image" drag={false} animate={{scale,y:reduced?0:-weight*4}} transition={transition} whileTap={reduced?undefined:{scale}}>
      <img src={images[key]} alt={label+'封面风景'} draggable="false"/>{active&&<span className="note-cover-check" aria-hidden="true"><Icon name="check" size={11}/></span>}
     </LiquidCard>
    </button>
   </div>;})}
  </div>
 </section>;
}
