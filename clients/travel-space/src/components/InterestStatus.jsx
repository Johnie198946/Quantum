import React, { useLayoutEffect, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { Icon } from './UI';
import './InterestStatus.css';

export default function InterestStatus({ choice, active, onClick }) {
 const measureRef = useRef(null), [width, setWidth] = useState(null);
 const reduced = useReducedMotion();
 useLayoutEffect(() => {
  const measure = () => {
   const contentWidth = measureRef.current?.offsetWidth;
   if (contentWidth) setWidth(Math.ceil(contentWidth) + 18);
  };
  measure();
  const observer = new ResizeObserver(measure);
  observer.observe(measureRef.current);
  return () => observer.disconnect();
 }, [active]);
 const transition = reduced ? { duration: 0 } : { type: 'spring', stiffness: 420, damping: 30, mass: .75 };

 return <motion.button type="button"
  className={'requirement-value interest-status' + (active ? ' has-value' : '')}
  aria-label={(active ? '移除' : '添加') + choice} aria-pressed={active}
  initial={false} animate={{ width: width ?? 'auto' }} transition={transition}
  onClick={event => { event.stopPropagation(); onClick(event); }}>
  <span ref={measureRef} className="interest-status-measure" aria-hidden="true">
   {active && <Icon name="check" size={12}/>}<span>{active ? '已选' : '添加'}</span>
  </span>
  <span className="interest-status-face" aria-hidden="true">
   <motion.span className="interest-status-check" initial={false}
    animate={{ width: active ? 15 : 0, opacity: active ? 1 : 0, scale: active ? 1 : .6 }} transition={transition}>
    <Icon name="check" size={12}/>
   </motion.span>
   <span className="interest-status-window">
    <motion.span className="interest-status-roll" initial={false}
     animate={{ y: active ? -16 : 0 }} transition={transition}>
     <span>添加</span><span>已选</span>
    </motion.span>
   </span>
  </span>
 </motion.button>;
}
