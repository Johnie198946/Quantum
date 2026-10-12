import React, { useRef, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import InterestStatus from './InterestStatus';

export default function InterestScrub({ choices, images, hints, selected, onChange }) {
 const refs = useRef([]), gesture = useRef(null), suppress = useRef(false);
 const [weights, setWeights] = useState([]), [current, setCurrent] = useState(-1);
 const reduced = useReducedMotion();
 const reset = () => { gesture.current = null; setWeights([]); setCurrent(-1); };

 function start(event) {
  if (event.button !== 0) return;
  suppress.current = false;
  gesture.current = {
   id: event.pointerId, startY: event.clientY, moved: false, index: -1,
   centers: refs.current.map(element => { const bounds = element.getBoundingClientRect(); return bounds.y + bounds.height / 2; })
  };
  event.currentTarget.setPointerCapture(event.pointerId);
 }
 function move(event) {
  const gestureState = gesture.current;
  if (!gestureState || gestureState.id !== event.pointerId) return;
  if (Math.abs(event.clientY - gestureState.startY) > 5) gestureState.moved = true;
  if (!gestureState.moved) return;
  const distances = gestureState.centers.map(center => Math.abs(center - event.clientY));
  const nearest = distances.indexOf(Math.min(...distances));
  gestureState.index = nearest;
  setCurrent(nearest);
  setWeights(distances.map(distance => Math.max(0, 1 - distance / 105)));
 }
 function finish(event, cancel = false) {
  const gestureState = gesture.current;
  if (!gestureState || gestureState.id !== event.pointerId) return;
  suppress.current = !cancel && gestureState.moved;
  if (!cancel && gestureState.moved && gestureState.index >= 0 && !selected.includes(choices[gestureState.index])) {
   onChange([...selected, choices[gestureState.index]]);
  }
  reset();
 }
 function toggle(event, choice) {
  // A release after scrubbing selects once; keyboard activation remains independent.
  if (suppress.current && event.detail !== 0) { suppress.current = false; return; }
  suppress.current = false;
  onChange(selected.includes(choice) ? selected.filter(value => value !== choice) : [...selected, choice]);
 }
 const transition = reduced ? { duration: 0 } : { type: 'spring', stiffness: 520, damping: 34 };

 return <>{choices.map((choice, index) => {
  const active = selected.includes(choice), weight = weights[index] || 0;
  return <motion.li key={choice} ref={element => refs.current[index] = element}
   className={'interest-scrub-item' + (current === index ? ' is-nearest' : '')}
   animate={{ paddingTop: weight * 8, paddingBottom: weight * 8 }} transition={transition}>
   <motion.div className="requirement-row interest-row-shell" style={{ touchAction: 'none' }}
    animate={{ scale: reduced ? 1 : 1 + weight * .065 }} transition={transition}
    onPointerDown={start} onPointerMove={move} onPointerUp={event => finish(event)}
    onPointerCancel={event => finish(event, true)} onLostPointerCapture={event => finish(event, true)}
    onClick={event => { if (event.target === event.currentTarget) toggle(event, choice); }}>
    <button type="button" className="interest-row interest-row-main"
     aria-label={(active ? '取消选择' : '选择') + choice} aria-pressed={active}
     onClick={event => toggle(event, choice)}>
     <motion.img src={images[index]} alt="" draggable="false"
      animate={{ width: 43 + weight * 10, height: 43 + weight * 10 }} transition={transition}/>
     <span className="requirement-copy"><strong>{choice}</strong><small>{hints[index]}</small></span>
    </button>
    <InterestStatus choice={choice} active={active} onClick={event => toggle(event, choice)}/>
   </motion.div>
  </motion.li>;
 })}<li className="interest-scrub-hint">沿喜欢的风景滑动，松手收进旅程。</li></>;
}
