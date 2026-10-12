import React, { useRef, useEffect } from 'react';
export function Space({ tunnel = false, active = true }) {
  const ref = useRef(null);
  const pointer = useRef({ x: -1000, y: -1000 });
  const phase = useRef(tunnel);
  useEffect(() => { phase.current = tunnel; }, [tunnel]);
  useEffect(() => {
    const canvas = ref.current, ctx = canvas.getContext('2d');
    const parent = canvas.parentElement;
    let width = 390, height = 844, raf, previous = 0, clock = 0;
    const particles = Array.from({ length: 95 }, (_, i) => ({ angle: i * 2.399, radius: Math.sqrt((i + 1) / 96), size: 0.6 + (i % 5) * 0.4, speed: 0.4 + (i % 7) * 0.12 }));
    const resize = () => { const b = parent.getBoundingClientRect(); width = b.width; height = b.height; const dpr = Math.min(devicePixelRatio, 1.7); canvas.width = width * dpr; canvas.height = height * dpr; canvas.style.width = width + 'px'; canvas.style.height = height + 'px'; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); };
    const observer = new ResizeObserver(resize); observer.observe(parent); resize();
    const move = e => { const b = canvas.getBoundingClientRect(); pointer.current = { x: e.clientX - b.left, y: e.clientY - b.top }; };
    const leave = () => { pointer.current = { x: -1000, y: -1000 }; };
    parent.addEventListener('pointermove', move); parent.addEventListener('pointerleave', leave);
    const frame = time => {
      const dt = previous ? Math.min(0.04, (time - previous) / 1000) : 0.016; previous = time;
      if (!document.hidden) {
        clock += dt; ctx.clearRect(0, 0, width, height);
        const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        for (const p of particles) {
          const spin = reduced ? 0 : clock * 0.03 * p.speed;
          const radius = phase.current ? ((p.radius + clock * 0.28) % 1) : p.radius;
          let x = width / 2 + Math.cos(p.angle + spin) * radius * width * 0.75;
          let y = height / 2 + Math.sin(p.angle + spin) * radius * height * 0.7;
          const dx = x - pointer.current.x, dy = y - pointer.current.y, d = Math.hypot(dx, dy);
          if (d < 100 && d > 1) { x += dx / d * (100 - d) * 0.16; y += dy / d * (100 - d) * 0.16; }
          ctx.fillStyle = 'rgba(255,255,255,' + (0.3 + 0.5 * radius) + ')';
          ctx.shadowBlur = 7; ctx.shadowColor = '#fff';
          if (phase.current) { ctx.strokeStyle = 'rgba(236,230,223,0.6)'; ctx.lineWidth = p.size; ctx.beginPath(); ctx.moveTo(x,y); ctx.lineTo(width / 2 + (x-width/2)*0.89, height/2 + (y-height/2)*0.89); ctx.stroke(); }
          ctx.beginPath(); ctx.arc(x,y,p.size,0,Math.PI*2); ctx.fill();
        }
      }
      raf = requestAnimationFrame(frame);
    };
    if (active) raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); observer.disconnect(); parent.removeEventListener('pointermove', move); parent.removeEventListener('pointerleave', leave); };
  }, [active]);
  return <div className="space" aria-hidden="true"><div className="space-cloud cloud-one" /><div className="space-cloud cloud-two" /><div className="space-cloud cloud-three" /><canvas ref={ref} /></div>;
}
