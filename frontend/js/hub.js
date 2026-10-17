/* A small picture of the committee: the Planner in the middle, the agents around it on
   right-angled connectors, and messages travelling along them. Drawn into any element with
   a data-hub attribute (sign-in pages, welcome, 404). Decorative: hidden from screen readers. */
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const LEFT = ['Profile', 'Market', 'Fundamentals', 'News'];
  const RIGHT = ['Strategist', 'Risk manager', 'Portfolio', 'Reporter'];
  const W = 132, H = 40, ys = [60, 130, 200, 270];
  function el(n, a, p) { const e = document.createElementNS(NS, n); for (const k in a) e.setAttribute(k, a[k]); if (p) p.appendChild(e); return e; }
  function path(pts) {
    let d = `M${pts[0][0]} ${pts[0][1]}`;
    for (let i = 1; i < pts.length - 1; i++) {
      const [ax, ay] = pts[i - 1], [cx, cy] = pts[i], [bx, by] = pts[i + 1];
      const r = Math.min(10, Math.abs(cy - ay) / 2 || 10, Math.abs(by - cy) / 2 || 10, Math.abs(cx - ax) / 2 || 10, Math.abs(bx - cx) / 2 || 10);
      const p1 = [cx + Math.sign(ax - cx) * r, cy + Math.sign(ay - cy) * r], p2 = [cx + Math.sign(bx - cx) * r, cy + Math.sign(by - cy) * r];
      d += ` L${p1[0]} ${p1[1]} Q${cx} ${cy} ${p2[0]} ${p2[1]}`;
    }
    const z = pts[pts.length - 1];
    return d + ` L${z[0]} ${z[1]}`;
  }
  function draw(host) {
    const svg = el('svg', {viewBox: '0 0 560 330', class: 'hub', 'aria-hidden': 'true', focusable: 'false'});
    const defs = el('defs', {}, svg);
    const pat = el('pattern', {id: 'hubgrid', width: 22, height: 22, patternUnits: 'userSpaceOnUse'}, defs);
    el('path', {d: 'M22 0H0V22', class: 'hub-grid'}, pat);
    const rg = el('radialGradient', {id: 'hubfade'}, defs);
    el('stop', {offset: '0.55', 'stop-color': '#fff'}, rg); el('stop', {offset: '1', 'stop-color': '#000'}, rg);
    const mask = el('mask', {id: 'hubmask'}, defs);
    el('rect', {width: 560, height: 330, fill: 'url(#hubfade)'}, mask);
    el('rect', {width: 560, height: 330, fill: 'url(#hubgrid)', mask: 'url(#hubmask)'}, svg);
    const lines = el('g', {class: 'hub-lines'}, svg), dots = el('g', {class: 'hub-dots'}, svg), nodes = el('g', {}, svg);
    const hub = {x: 214, y: 135, w: 132, h: 60};
    const ids = [];
    LEFT.forEach((name, i) => {
      const cy = ys[i] + 5;
      const id = 'hl' + i;
      el('path', {id, d: path([[16 + W, cy], [182, cy], [182, 165], [hub.x, 165]])}, lines);
      ids.push(id);
      const g = el('g', {class: 'hub-node', transform: `translate(16 ${cy - H / 2})`}, nodes);
      el('rect', {width: W, height: H, rx: 11}, g);
      el('circle', {cx: 16, cy: H / 2, r: 3.5}, g);
      const t = el('text', {x: 28, y: H / 2 + 4.5}, g); t.textContent = name;
    });
    RIGHT.forEach((name, i) => {
      const cy = ys[i] + 5;
      const id = 'hr' + i;
      el('path', {id, d: path([[hub.x + hub.w, 165], [378, 165], [378, cy], [412, cy]])}, lines);
      ids.push(id);
      const g = el('g', {class: 'hub-node', transform: `translate(412 ${cy - H / 2})`}, nodes);
      el('rect', {width: W, height: H, rx: 11}, g);
      el('circle', {cx: 16, cy: H / 2, r: 3.5}, g);
      const t = el('text', {x: 28, y: H / 2 + 4.5}, g); t.textContent = name;
    });
    const g = el('g', {class: 'hub-node hub-centre', transform: `translate(${hub.x} ${hub.y})`}, nodes);
    el('rect', {width: hub.w, height: hub.h, rx: 14}, g);
    const t = el('text', {x: hub.w / 2, y: 28, 'text-anchor': 'middle'}, g); t.textContent = 'Planner';
    const s = el('text', {x: hub.w / 2, y: 45, 'text-anchor': 'middle', class: 'hub-sub'}, g); s.textContent = 'coordinates';
    // messages: one dot per connector, staggered, in and out of the Planner
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
      ids.forEach((id, k) => {
        const c = el('circle', {r: 4, class: 'hub-dot'}, dots);
        const m = el('animateMotion', {dur: '3.2s', repeatCount: 'indefinite', begin: `-${(k * 0.41).toFixed(2)}s`}, c);
        el('mpath', {href: '#' + id}, m);
      });
    }
    host.appendChild(svg);
  }
  document.querySelectorAll('[data-hub]').forEach(draw);
})();
