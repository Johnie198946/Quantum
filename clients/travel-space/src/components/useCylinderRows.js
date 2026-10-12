import { useLayoutEffect } from 'react';

const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
const smoothstep = value => value * value * (3 - 2 * value);

// Read untransformed layout slots; deform only their inner visual surfaces.
// Motion keeps owning the outer slots so pinch reflow and scroll never fight.
export function useCylinderRows(scrollRef, gridRef, mode, count) {
  useLayoutEffect(() => {
    const viewport = scrollRef.current, grid = gridRef.current;
    if (!viewport || !grid) return;
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    let frame = 0, rows = [], dirty = true, previousScroll = viewport.scrollTop;
    let previousTime = performance.now(), velocity = 0, flow = 0;

    function measure() {
      rows = [];
      for (const slot of grid.children) {
        let row = rows.find(item => Math.abs(item.top - slot.offsetTop) < 3);
        if (!row) { row = { top: slot.offsetTop, height: 0, surfaces: [] }; rows.push(row); }
        row.height = Math.max(row.height, slot.offsetHeight);
        row.surfaces.push(slot.querySelector('.cylinder-surface'));
      }
      dirty = false;
    }

    function render(time) {
      frame = 0;
      if (dirty) measure();
      const elapsed = clamp(time - previousTime, 8, 64);
      const currentScroll = viewport.scrollTop;
      velocity = (currentScroll - previousScroll) / elapsed;
      const targetFlow = media.matches ? 0 : clamp(velocity / 1.8, -1, 1);
      flow += (targetFlow - flow) * (1 - Math.exp(-elapsed / 95));
      if (Math.abs(flow) < .001) flow = 0;
      previousScroll = currentScroll; previousTime = time;
      const halfHeight = Math.max(1, viewport.clientHeight / 2);

      rows.forEach((row, index) => {
        const delta = grid.offsetTop + row.top + row.height / 2 - currentScroll - halfHeight;
        const distance = clamp(delta / halfHeight, -1.4, 1.4);
        const edge = Math.min(1, Math.abs(distance));
        const angle = distance * .72;
        const rotation = media.matches ? 0 : -distance * 39;
        const scale = media.matches ? 1 : 1 - .10 * edge * edge;
        const compression = media.matches ? 1 : 1 - .07 * edge * edge;
        const shift = media.matches ? 0 : halfHeight * .66 * (Math.sin(angle) - angle);
        const depth = media.matches ? 0 : -52 * edge * edge;
        const opacity = media.matches ? 1 : 1 - .80 * smoothstep(clamp((Math.abs(distance) - .54) / .61, 0, 1));
        const brightness = media.matches ? 1 : 1 - .14 * edge * edge;
        const bend = flow * (7 + edge * 8);
        for (const surface of row.surfaces) {
          surface.dataset.cylinderRow = index;
          surface.dataset.cylinderDistance = distance.toFixed(4);
          surface.dataset.cylinderFlow = flow.toFixed(4);
          const values = {
            '--cylinder-rotation': rotation.toFixed(3) + 'deg',
            '--cylinder-scale-x': (scale + Math.abs(flow) * .018).toFixed(4),
            '--cylinder-scale-y': (compression - Math.abs(flow) * .034).toFixed(4),
            '--cylinder-shift': shift.toFixed(3) + 'px',
            '--cylinder-depth': depth.toFixed(3) + 'px',
            '--cylinder-opacity': opacity.toFixed(4),
            '--cylinder-brightness': brightness.toFixed(4),
            '--cylinder-radius-top': (18 + Math.max(0, bend)).toFixed(2) + 'px',
            '--cylinder-radius-bottom': (18 + Math.max(0, -bend)).toFixed(2) + 'px'
          };
          Object.entries(values).forEach(([key, value]) => surface.style.setProperty(key, value));
        }
      });
      // Keep a short settling tail, then stop rendering until the next input.
      if (Math.abs(flow) > .001 || Math.abs(velocity) > .01) frame = requestAnimationFrame(render);
    }

    function schedule() { if (!frame) frame = requestAnimationFrame(render); }
    function resize() { dirty = true; schedule(); }
    const observer = new ResizeObserver(resize);
    observer.observe(viewport); observer.observe(grid);
    for (const slot of grid.children) observer.observe(slot);
    viewport.addEventListener('scroll', schedule, { passive: true });
    media.addEventListener('change', resize);
    resize();
    return () => {
      cancelAnimationFrame(frame); observer.disconnect();
      viewport.removeEventListener('scroll', schedule);
      media.removeEventListener('change', resize);
    };
  }, [scrollRef, gridRef, mode, count]);
}
