import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { motion, useReducedMotion, useIsPresent, useMotionValue, useSpring, useMotionValueEvent } from 'motion/react';
import {cardRevealTransition} from './CardPageUnfold';
const modalLocks=new WeakMap();
export const spring = { type: 'spring', stiffness: 280, damping: 26, mass: 0.85 };
export function Icon({ name, size = 22, ...props }) {
  const paths = {
    search:<><circle cx="10.5" cy="10.5" r="7"/><path d="m16 16 5 5"/></>,
    list:<><path d="M9 6h12M9 12h12M9 18h12"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/></>,code:<><path d="m8 7-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/></>,sun:<><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1 1M18 18l1 1M5 19l1-1M18 6l1-1"/></>,
    wallet:<><rect x="3" y="6" width="18" height="15" rx="3"/><path d="M3 7V5a2 2 0 0 1 2-2h13M16 12h5v5h-5a2 2 0 0 1 0-5ZM17 14.5h.01"/></>,bag:<><path d="M4 7h16l1 14H3ZM8 8V6a4 4 0 0 1 8 0v2"/></>,receipt:<><path d="M5 2l3 2 4-2 4 2 3-2v20l-3-2-4 2-4-2-3 2ZM8 8h8M8 12h8M8 16h5"/></>,
    boat:<><path d="M4 14l8-4 8 4-2 5H6ZM12 10V3h5v9M3 21c2 1 4 1 6 0 2 1 4 1 6 0 2 1 4 1 6 0"/></>,helicopter:<><path d="M3 3h18M12 3v4M5 10h10a5 5 0 0 1 5 5v2H6l-3-7ZM5 10 2 7M8 17v4M17 17v4M5 21h15M15 10v5h5"/></>,
    bus:<><rect x="4" y="3" width="16" height="16" rx="3"/><path d="M4 11h16M8 19v2M16 19v2M8 15h.01M16 15h.01"/></>,train:<><rect x="5" y="2" width="14" height="17" rx="4"/><path d="M5 11h14M8 19l-2 3M16 19l2 3M9 15h.01M15 15h.01"/></>,taxi:<><path d="M9 5V2h6v3M4 11l2-6h12l2 6M3 11h18v8H3ZM5 19v2M19 19v2M6 15h2M16 15h2"/></>,
    return:<path d="M19 5v8a3 3 0 0 1-3 3H4m5-5-5 5 5 5"/>,image:<><rect x="3" y="3" width="18" height="18" rx="4"/><circle cx="9" cy="9" r="2"/><path d="m3 17 5-5 4 4 4-6 5 7"/></>,play:<path d="m8 5 11 7-11 7Z"/>,pause:<path d="M8 5v14M16 5v14"/>,
    mic:<><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/></>,stop:<rect x="6" y="6" width="12" height="12" rx="2"/>,spark:<><path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4Z"/><path d="M20 2v4M18 4h4"/></>,
    plane: <path d="m22 2-7 19-3-8-9-3 19-8Z M12 13l6-7"/>,car:<><path d="m4 10 2-6h12l2 6M3 10h18v9H3Z M5 19v2M19 19v2"/><path d="M6 14h2M16 14h2"/></>,bed:<><path d="M3 4v17M21 10v11M3 17h18M7 10h11a3 3 0 0 1 3 3v4"/><circle cx="7" cy="11" r="2"/></>,dining:<><path d="M4 3v5a3 3 0 0 0 6 0V3 M7 3v18M19 3v18M19 3c-4 3-5 9 0 10"/></>,ticket:<><path d="M3 7h18v4a2 2 0 0 0 0 4v4H3v-4a2 2 0 0 0 0-4Z M15 7v3m0 3v2m0 3v1"/></>,clock:<><circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 3"/></>,sliders:<><path d="M3 6h18M3 12h18M3 18h18"/><circle cx="8" cy="6" r="2" fill="currentColor"/><circle cx="16" cy="12" r="2" fill="currentColor"/><circle cx="9" cy="18" r="2" fill="currentColor"/></>,
    back: <path d="m14 5-7 7 7 7" />, plus: <path d="M12 5v14M5 12h14" />,
    arrow: <path d="M12 19V5m-5 5 5-5 5 5" />, close: <path d="m6 6 12 12M18 6 6 18" />,
    folder: <path d="M3 7a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />,
    layers: <><path d="m12 3 10 5-10 5L2 8Z" /><path d="m2 12 10 5 10-5M2 16l10 5 10-5" /></>,
    book: <><path d="M3 4h7l2 2 2-2h7v16h-7l-2 2-2-2H3Z" /><path d="M12 6v16" /></>,
    home: <path d="m3 10 9-7 9 7v11h-7v-7h-4v7H3Z" />,
    person: <><circle cx="12" cy="7" r="4" /><path d="M4 22v-3a8 8 0 0 1 16 0v3Z" /></>,
    pin: <><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z" /><circle cx="12" cy="10" r="2" /></>,
    check: <path d="m5 12 4 4L19 6" />, edit: <><path d="m15 4 5 5M4 20l5-1L21 7l-4-4L5 15Z" /></>,
    chevron: <path d="m8 5 7 7-7 7" />, down: <path d="m5 9 7 7 7-7" />,
    lock: <><rect x="5" y="10" width="14" height="11" rx="3" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M7 3v5M17 3v5M3 11h18" /></>,
    more: <><circle cx="5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /></>,
    thought: <><path d="M20 11a8 8 0 0 1-8 7H7l-4 3 1-6a8 8 0 1 1 16-4Z" /><path d="M8 10h.01M12 10h.01M16 10h.01" strokeWidth="2.4" /></>,
    replay: <><path d="M3 11a9 9 0 1 1 2 7M3 4v7h7" /></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="2" /><rect x="14" y="3" width="7" height="7" rx="2" /><rect x="3" y="14" width="7" height="7" rx="2" /><rect x="14" y="14" width="7" height="7" rx="2" /></>,
    leaf: <><path d="M20 3C9 2 3 8 4 15c1 7 13 7 16-12Z" /><path d="M4 20 17 7" /></>,
    expand: <><path d="M8 5h11v11M19 5 5 19"/></>,
    globe: <><circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/></>,
    download: <><path d="M12 3v12m-4-4 4 4 4-4M4 17v4h16v-4"/></>,
    grip: <><path d="M9 5h.01M15 5h.01M9 12h.01M15 12h.01M9 19h.01M15 19h.01" strokeWidth="3"/></>
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name] || paths.more}</svg>;
}
export function Glass({ className = '', children, ...props }) { return <motion.div className={'glass ' + className} {...props}>{children}</motion.div>; }
export function TopBar({ title, onBack, children, className = '' }) { return <header className={'topbar ' + className}><button className="icon-btn" aria-label="返回" onClick={onBack}><Icon name="back" /></button><span>{title}</span><div className="topbar-right">{children}</div></header>; }
export function Primary({ children, className = '', icon='chevron', ...props }) { const reduced=useReducedMotion();return <motion.button whileTap={reduced?undefined:{ scale: 0.96 }} transition={spring} className={'primary confirm-capsule ' + className} {...props}>{children}<Icon name={icon} size={18} /></motion.button>; }
export function useConfirmationGlow(){
 useEffect(()=>{
  const held=new Set(),selector='button.primary,button.round-confirm,button.inline-edit-confirm,button.service-apply,button.ticket-select,button.journal-save-action,button.location-commit,button.requirement-confirm,button.voice-submit,button[aria-label^="确认"],button[aria-label^="确定"],button[aria-label^="采用"],button[aria-label="继续"],button[aria-label="下一步"],button.confirm-capsule';
  const press=e=>{const button=e.target.closest?.(selector);if(button&&!button.disabled){button.classList.add('is-touching');held.add(button);}};
  const release=()=>{held.forEach(button=>button.classList.remove('is-touching'));held.clear();};
  const starts=['pointerdown','touchstart'],ends=['pointerup','pointercancel','touchend','touchcancel'];
  starts.forEach(event=>document.addEventListener(event,press,{capture:true,passive:true}));ends.forEach(event=>document.addEventListener(event,release,true));window.addEventListener('blur',release);
  return()=>{release();starts.forEach(event=>document.removeEventListener(event,press,true));ends.forEach(event=>document.removeEventListener(event,release,true));window.removeEventListener('blur',release);};
 },[]);
}
const rootTabs = [['home','首页'],['book','阅读'],['layers','工作流'],['person','我的']];
export function BottomTabs({active:controlled,onChange}) {
  const [internal, setInternal] = useState(2);
  const active=controlled??internal;
  const setActive=value=>{setInternal(value);onChange?.(value);};
  const widthTarget=useMotionValue(0), cell=useSpring(widthTarget,{stiffness:400,damping:31});
  const nav = useRef(null), buttons = useRef([]), initialized = useRef(false), idle = useRef(null);
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const change = () => setReduced(media.matches);
    media.addEventListener('change', change);
    return () => media.removeEventListener('change', change);
  }, []);
  const target = useMotionValue(0), x = useSpring(target, { stiffness: 400, damping: 31, mass: .85 });
  const scaleX = useSpring(1, { stiffness: 240, damping: 22 });
  const scaleY = useSpring(1, { stiffness: 240, damping: 22 });
  const skewX = useSpring(0, { stiffness: 210, damping: 23 });
  const radius = useSpring(26, { stiffness: 220, damping: 22 });
  const settle = () => { scaleX.set(1); scaleY.set(1); skewX.set(0); radius.set(26); };
  useMotionValueEvent(x, 'change', () => {
    if (reduced) return;
    const velocity = x.getVelocity(), strength = Math.min(Math.abs(velocity) / 1200, 1);
    scaleX.set(1 + strength * .38); scaleY.set(1 - strength * .11);
    skewX.set(Math.max(-6, Math.min(6, velocity / 300))); radius.set(26 + strength * 9);
    clearTimeout(idle.current); idle.current = setTimeout(settle, 90);
  });
  useLayoutEffect(() => {
    const measure = () => {
      const button=buttons.current[active], width=button.offsetWidth, left=button.offsetLeft-6;
      widthTarget.set(width);target.set(left);
      if (!initialized.current || reduced) { x.jump(left);cell.jump(width);settle(); }
      initialized.current = true;
    };
    const observer = new ResizeObserver(measure); observer.observe(nav.current);buttons.current.forEach(el=>observer.observe(el));measure();
    return () => observer.disconnect();
  }, [active, reduced, target, x, widthTarget, cell]);
  useEffect(() => () => clearTimeout(idle.current), []);
  function keyDown(event, index) {
    const next = event.key === 'ArrowRight' ? (index + 1) % 4 : event.key === 'ArrowLeft' ? (index + 3) % 4 : event.key === 'Home' ? 0 : event.key === 'End' ? 3 : null;
    if (next !== null) { event.preventDefault(); setActive(next); buttons.current[next]?.focus(); }
  }
  return <nav ref={nav} className="root-tabs glass" aria-label="主导航">
    <motion.div className="tab-liquid" aria-hidden="true" style={{ width: cell, x, scaleX: reduced ? 1 : scaleX, scaleY: reduced ? 1 : scaleY, skewX: reduced ? 0 : skewX, borderRadius: reduced ? 26 : radius }} />
    {rootTabs.map(([icon,label], index) => <motion.button key={label} ref={el => buttons.current[index] = el} type="button" aria-label={label} aria-pressed={active === index} className={active === index ? 'active' : ''} onClick={() => setActive(index)} onKeyDown={event => keyDown(event, index)} whileTap={reduced ? undefined : { scale: .91 }} transition={{ type:'spring', stiffness:440, damping:25 }}><Icon name={icon} size={18}/>{active===index&&<span>{label}</span>}</motion.button>)}
  </nav>;
}
export function Sheet({ label, onClose, children, className = '', revealFrom, burst=false, closeIconSize=14, closeIcon='close', closeLabel='关闭', flyFrom, flyHeight, slideFrom }) {
  const present = useIsPresent(),reduced=useReducedMotion();
  const ref = useRef(null);
  const closeRef = useRef(null), closeAction=useRef(onClose);closeAction.current=onClose;
  useEffect(() => {
    if(!present)return;
    const prior = document.activeElement;
    const blocked=[];let node=ref.current?.parentElement;const phone=node?.closest('.phone');
    while(node&&node!==phone){for(const sibling of node.parentElement?.children||[]){if(sibling!==node&&!sibling.matches('.flow-selection,.flow-notice')){const lock=modalLocks.get(sibling)||{count:0,original:sibling.inert};lock.count++;modalLocks.set(sibling,lock);blocked.push(sibling);sibling.inert=true;}}node=node.parentElement;}
    closeRef.current?.focus({ preventScroll:true });
    const handler = e => {
      const dialogs = [...document.querySelectorAll('.sheet-overlay:not([inert]) > [role="dialog"]')];
      if (dialogs.at(-1) !== ref.current) return;
      if (e.key === 'Escape') {e.preventDefault();e.stopPropagation();closeAction.current();}
      if (e.key === 'Tab') {
        const items = [...ref.current.querySelectorAll('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex="0"]')].filter(el=>el.getClientRects().length&&!el.closest('[inert]'));
        const first = items[0], last = items.at(-1);
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener('keydown', handler);
    return () => { document.removeEventListener('keydown', handler); blocked.forEach(el=>{const lock=modalLocks.get(el);if(lock&&!--lock.count){el.inert=lock.original;modalLocks.delete(el);}});prior?.focus({ preventScroll:true }); };
  }, [present]);
  const phone=document.querySelector('.phone'),width=(phone?.clientWidth||390)-28,height=Math.min(flyHeight||680,(phone?.clientHeight||800)-92),top=50;
  const flight=flyFrom?{x:flyFrom.x-width/2-14,y:flyFrom.y-top-height/2,scaleX:Math.max(.08,flyFrom.width/width),scaleY:Math.max(.06,flyFrom.height/height)}:null;
  return <motion.div className={'sheet-overlay'+(flyFrom?' flying-overlay':'')+(slideFrom?' sliding-overlay':'')} aria-hidden={present ? undefined : true} inert={present ? undefined : ''} style={{pointerEvents:present?'auto':'none'}} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}><button aria-label="关闭弹窗背景" className="scrim" onClick={onClose} tabIndex={-1} /><motion.section ref={ref} role="dialog" aria-modal="true" aria-label={label} className={'glass sheet ' + className+(flyFrom?' flying-sheet':'')} style={flyFrom?{position:'absolute',top,left:14,right:14,height,bottom:'auto',transformOrigin:'center'}:revealFrom?{transformOrigin:revealFrom.x+'px '+revealFrom.y+'px'}:undefined} initial={reduced?false:flight?flight:slideFrom?{x:'110%',y:0}:revealFrom?{y:0,clipPath:'circle(0px at '+revealFrom.x+'px '+revealFrom.y+'px)'}:{y:'100%'}} animate={flight?{x:0,y:0,scaleX:1,scaleY:1}:slideFrom?{x:0,y:0}:revealFrom?{y:0,scale:burst&&!reduced?[.7,1.035,1]:1,clipPath:'circle('+revealFrom.radius+'px at '+revealFrom.x+'px '+revealFrom.y+'px)'}:{y:0}} exit={flight?flight:slideFrom?{x:'110%',y:0}:revealFrom?{y:0,clipPath:'circle(0px at '+revealFrom.x+'px '+revealFrom.y+'px)'}:{y:'100%'}} transition={reduced?{duration:0}:flight?{type:'spring',stiffness:235,damping:29,mass:.85}:revealFrom?cardRevealTransition:spring}><div className="sheet-grip" />{!className.includes('flow-chat-sheet')&&<button type="button" className="icon-btn sheet-ask-ai" aria-label="询问本页AI建议" onClick={e=>{const rect=e.currentTarget.getBoundingClientRect(),bounds=e.currentTarget.closest('.phone')?.getBoundingClientRect();window.dispatchEvent(new CustomEvent('quantum-ask-ai',{detail:{quote:ref.current?.querySelector('h2,h3')?.textContent||label,origin:bounds?{x:rect.left+rect.width/2-bounds.left,y:rect.top+rect.height/2-bounds.top,width:rect.width,height:rect.height}:undefined}}));}}><Icon name="thought" size={17}/></button>}<button ref={closeRef} onClick={onClose} className="icon-btn sheet-close" aria-label={closeLabel}><Icon name={closeIcon} size={closeIconSize} /></button>{children}</motion.section></motion.div>;
}
export function Disclosure({ title, children, open = false }) { return <details className="disclosure" open={open || undefined}><summary>{title}<Icon name="down" size={18} /></summary><div>{children}</div></details>; }
