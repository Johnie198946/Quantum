import { useEffect, useRef, useState } from 'react';

// A stationary hold unlocks dragging. Until then, touch scrolling stays native.
export function useHoldReorder(items, onReorder, options={}) {
  const blockedTap = useRef(false);
  const refs = useRef(new Map()), session = useRef(null), latest = useRef({ items, onReorder });
  const [lift, setLift] = useState(null), [announcement, announce] = useState('');
  latest.current = { items, onReorder, options };
  function reorder(id, target) {
    const { items: current, onReorder: update } = latest.current;
    const index = current.findIndex(item => item.id === id);
    if (index < 0 || index === target) return;
    const next = [...current], [item] = next.splice(index, 1);
    next.splice(target, 0, item); update(next);
    announce((item.title||item.place) + '，第' + (target + 1) + '项');
    return next;
  }
  useEffect(() => {
    let scrollFrame=null;
    // Motion emits keyboard press/cancel events with pointerId 0. Only the
    // pointer that started this hold may move or end the current gesture.
    const point = event => event.touches ? [...(event.touches.length ? event.touches : event.changedTouches)].find(t => t.identifier === session.current?.pointer) : event.pointerId === session.current?.pointer ? event : null;
    const finish = (event, canceled = false) => {
      const current = session.current;
      if (!current || (event && !point(event))) return;
      clearTimeout(current.timer);
      cancelAnimationFrame(scrollFrame);scrollFrame=null;
      if (current.active && canceled) latest.current.onReorder(current.original);
      else if(current.active) latest.current.options?.onDrop?.(latest.current.items);
      session.current = null; setLift(null);
    };
    const place = (current,p) => {
      const dy=p.clientY-current.y;
      setLift({ ...current.rect, id: current.id, y: dy, item: current.item });
      // Derive destinations from layout offsets, never from animating transforms.
      const list = refs.current.get(current.id)?.parentElement;
      if (!list) return;
      const listTop = list.getBoundingClientRect().top-list.scrollTop;
      const centers = latest.current.items.map(item => {
        const el = refs.current.get(item.id);
        return listTop + el.offsetTop + el.offsetHeight / 2;
      });
      const targetY = current.rect.top + current.rect.height / 2 + dy;
      let target = 0;
      centers.forEach((center, index) => { if (Math.abs(center - targetY) < Math.abs(centers[target] - targetY)) target = index; });
      reorder(current.id, target);
    };
    const autoScroll=()=>{
      const current=session.current;
      if(!current?.active||!current.lastPoint){scrollFrame=null;return;}
      const scroller=refs.current.get(current.id)?.closest('.route-detail-content, .sheet, .adopt-canvas');
      if(scroller){
        const r=scroller.getBoundingClientRect(),y=current.lastPoint.clientY;
        const amount=y>r.bottom-44?Math.min(10,(y-r.bottom+44)/3):y<r.top+44?-Math.min(10,(r.top+44-y)/3):0;
        if(amount){scroller.scrollTop+=amount;place(current,current.lastPoint);}
      }
      scrollFrame=requestAnimationFrame(autoScroll);
    };
    const move = event => {
      const current = session.current, p = point(event);
      if (!current || !p || (event.pointerType === 'touch')) return;
      const dx = p.clientX - current.x, dy = p.clientY - current.y;
      if (!current.active) {
        if(current.surface&&Math.hypot(dx,dy)>5)current.activate();
        else if (Math.hypot(dx, dy) > 9) { blockedTap.current=true; finish(); }
        if(!current.active)return;
      }
      if (event.cancelable) event.preventDefault();
      current.lastPoint={clientX:p.clientX,clientY:p.clientY};place(current,p);
      if(scrollFrame===null)scrollFrame=requestAnimationFrame(autoScroll);
    };
    const end = event => { if (event.pointerType !== 'touch') finish(event); };
    const cancel = event => { if (event.pointerType !== 'touch') finish(event, true); };
    const touchCancel = event => finish(event, true);
    const escape = event => { if (event.key === 'Escape' && session.current?.active) { event.preventDefault(); event.stopImmediatePropagation(); finish(null, true); } };
    window.addEventListener('pointermove', move, { passive:false });
    window.addEventListener('pointerup', end); window.addEventListener('pointercancel', cancel);
    window.addEventListener('touchmove', move, { passive:false });
    window.addEventListener('touchend', finish); window.addEventListener('touchcancel', touchCancel);
    window.addEventListener('keydown', escape, true);
    const blur = () => finish(null, true); window.addEventListener('blur', blur);
    return () => {
      clearTimeout(session.current?.timer); session.current = null;
      cancelAnimationFrame(scrollFrame);
      window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', end); window.removeEventListener('pointercancel', cancel);
      window.removeEventListener('touchmove', move); window.removeEventListener('touchend', finish); window.removeEventListener('touchcancel', touchCancel);
      window.removeEventListener('keydown', escape, true); window.removeEventListener('blur', blur);
    };
  }, []);
  function start(event, item) {
    const control = event.target.closest('button,input,textarea,label'),handle=!!event.target.closest('[data-reorder-handle]');
    if(!handle&&event.currentTarget?.hasAttribute('data-pending-key'))return;
    if ((control && !control.matches('.itinerary-time,[data-reorder-handle]')) || session.current || (event.type === 'pointerdown' && (!event.pointerType || event.pointerType === 'touch' || event.button !== 0))) return;
    blockedTap.current=false;
    const p = event.touches ? event.touches[0] : event;
    const current = { id:item.id, item, x:p.clientX, y:p.clientY, pointer:p.identifier ?? p.pointerId, original:[...latest.current.items], active:false, surface:!!event.target.closest('[data-reorder-surface]') };
    const activate=() => {
      const el = refs.current.get(item.id);
      if (!el || session.current !== current) return;
      const r = el.getBoundingClientRect();
      current.rect = { top:r.top, left:r.left, width:r.width, height:r.height };
      current.active = true; blockedTap.current=true;
      setLift({ ...current.rect, id:item.id, y:0, item });
      announce((item.title||item.place) + '已拿起，拖动调整顺序');
    };
    // The dedicated grip works immediately; the rest of the row uses a hold
    // so a vertical swipe can still scroll the drawer naturally.
    current.activate=activate;
    session.current = current;
    if(current.surface)return;
    if(handle){event.preventDefault();activate();}
    else current.timer=setTimeout(activate,280);
  }
  const keyDown = (event, item) => {
    const handle=event.target.matches('[data-reorder-handle]');
    if ((!handle&&(event.target !== event.currentTarget || !event.altKey)) || !['ArrowUp','ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    const index = latest.current.items.findIndex(i => i.id === item.id);
    const next=reorder(item.id, Math.max(0, Math.min(items.length - 1, index + (event.key === 'ArrowUp' ? -1 : 1))));
    if(next)latest.current.options?.onDrop?.(next);
  };
  return { refs, lift, announcement, start, keyDown, allowTap:()=>!blockedTap.current, resetTap:()=>{if(!session.current)blockedTap.current=false;} };
}
