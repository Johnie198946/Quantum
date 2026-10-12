import React, { useRef, useEffect } from 'react';
import { motion, animate, useMotionValue, useSpring } from 'motion/react';
import { spring } from './UI';
export default function LiquidCard({ children, className = '', onDrop, onTap, drag = true, reset = true, onDragStart, onDragMove, ...props }) {
  const vx = useSpring(1, { stiffness: 170, damping: 19 });
  const vy = useSpring(1, { stiffness: 170, damping: 19 });
  const skew = useSpring(0, { stiffness: 130, damping: 19 });
  const tl = useSpring(22, { stiffness: 130, damping: 20 });
  const tr = useSpring(22, { stiffness: 130, damping: 20 });
  const br = useSpring(22, { stiffness: 130, damping: 20 });
  const bl = useSpring(22, { stiffness: 130, damping: 20 });
  const x = useMotionValue(0), y = useMotionValue(0);
  const dragged = useRef(false);
  const idle = useRef(null);
  const settle = () => { vx.set(1); vy.set(1); skew.set(0); [tl,tr,br,bl].forEach(v=>v.set(22)); };
  useEffect(() => () => clearTimeout(idle.current), []);
  return <motion.div className={'liquid-card ' + className} drag={drag} dragMomentum={false} style={{ x, y, scaleX: vx, scaleY: vy, skewX: skew, borderTopLeftRadius:tl, borderTopRightRadius:tr, borderBottomRightRadius:br, borderBottomLeftRadius:bl }} initial={{ scaleX: 1, scaleY: 1 }} onDragStart={() => { dragged.current = true; onDragStart?.(); }} onDrag={(e, info) => {
    const speed = Math.min(1800, Math.hypot(info.velocity.x, info.velocity.y));
    const horizontal = Math.abs(info.velocity.x) / (Math.hypot(info.velocity.x, info.velocity.y) || 1);
    const strength = speed / 1800 * 0.18;
    vx.set(1 + strength * (horizontal * 2 - 0.8));
    vy.set(1 + strength * ((1-horizontal) * 2 - 0.8));
    skew.set(Math.max(-10, Math.min(10, info.velocity.x / 120)));
    const cx=info.velocity.x,cy=info.velocity.y;
    [-cx-cy,cx-cy,cx+cy,-cx+cy].forEach((value,i)=>[tl,tr,br,bl][i].set(22+Math.min(24,Math.max(0,value)*0.013)));
    const pull=onDragMove?.(e,info);
    if(pull){x.set(info.offset.x+pull.x);y.set(info.offset.y+pull.y);}
    clearTimeout(idle.current);
    idle.current = setTimeout(settle, 90);
  }} onDragEnd={(event, info) => {
    const consumed = onDrop?.(event, info);
    settle();
    if (reset && !consumed) { animate(x,0,spring); animate(y,0,spring); }
    setTimeout(() => { dragged.current = false; }, 120);
  }} onPointerDownCapture={settle} onTap={e => { if (!dragged.current) onTap?.(e); }} whileTap={drag ? { cursor: 'grabbing' } : { scale: 0.97 }} transition={spring} {...props}>{children}</motion.div>;
}
