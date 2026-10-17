/* The agent flow: one map of the committee used everywhere on the site (home page, the
   live analysis, the run trace). Agents are cards joined by right-angled connectors; a
   message lights the route it travels and a pulse runs along it. A row of checks above
   the map ticks off as the run moves forward.

   AgentFlow reads the same events the server streams and logs, so a live run, a saved
   trace and a replay all draw the same way. No dependencies. */
(function (global) {
  const NS = 'http://www.w3.org/2000/svg';

  /* ---------- the cast ---------- */
  const NODES = {
    you:       {label: 'You',          icon: 'you',       idle: 'Waiting',            you: true},
    profile:   {label: 'Profile',      icon: 'profile',   idle: 'Turns you into limits'},
    planner:   {label: 'Planner',      icon: 'planner',   idle: 'Plans the work',      hub: true},
    market:    {label: 'Market',       icon: 'market',    idle: 'Prices and trend'},
    fund:      {label: 'Fundamentals', icon: 'fund',      idle: 'Profit, debt, value'},
    news:      {label: 'News',         icon: 'news',      idle: 'Headlines and tone'},
    docs:      {label: 'Document',     icon: 'docs',      idle: 'Your PDF, if attached'},
    check:     {label: 'Planner',      icon: 'check',     idle: 'Checks every report', hub: true},
    strategy:  {label: 'Strategist',   icon: 'strategy',  idle: 'Proposes the call'},
    risk:      {label: 'Risk manager', icon: 'risk',      idle: 'Challenges the call'},
    portfolio: {label: 'Portfolio',    icon: 'portfolio', idle: 'Sizes it for you'},
    report:    {label: 'Reporter',     icon: 'report',    idle: 'Writes it up'},
  };
  const AGENT = {User: 'you', ProfileAgent: 'profile', MarketAnalyst: 'market', FundamentalsAnalyst: 'fund',
    NewsAnalyst: 'news', DocumentAnalyst: 'docs', StrategyAgent: 'strategy', RiskManager: 'risk',
    PortfolioAgent: 'portfolio', ReportAgent: 'report'};
  const ANALYSTS = ['market', 'fund', 'news', 'docs'];

  const ICONS = {
    you: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4.5 20.5c.6-3.6 3.6-5.5 7.5-5.5s6.9 1.9 7.5 5.5',
    profile: 'M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zM9 12.5a2.2 2.2 0 1 0 0-4.4 2.2 2.2 0 0 0 0 4.4zM5.8 16.5c.6-1.5 1.7-2.2 3.2-2.2s2.6.7 3.2 2.2M14.5 9.5h4M14.5 13h4',
    planner: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM12 2.5v4M12 17.5v4M2.5 12h4M17.5 12h4M5.3 5.3l2.4 2.4M16.3 16.3l2.4 2.4M5.3 18.7l2.4-2.4M16.3 7.7l2.4-2.4',
    market: 'M3 17.5l5.5-6 4 3.5L20 7M15.5 7H20v4.5',
    fund: 'M5 20v-6M10 20V9M15 20v-8M20 20V5M3 20.5h18',
    news: 'M4 4.5h13v15H6a2 2 0 0 1-2-2zM17 8.5h3v9a2 2 0 0 1-2 2M7.5 8.5h6M7.5 12h6M7.5 15.5h4',
    docs: 'M6 3h8l4.5 4.5V21H6zM14 3v4.5h4.5M9 12.5h6M9 16h6',
    check: 'M12 3l7.5 3v5.5c0 4.6-3.2 8.2-7.5 9.5-4.3-1.3-7.5-4.9-7.5-9.5V6zM8.6 12l2.4 2.4 4.4-4.6',
    strategy: 'M12 20.5a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 12.6a.6.6 0 1 0 0-1.2.6.6 0 0 0 0 1.2z',
    risk: 'M12 3.5l9 15.5H3zM12 10v4.2M12 16.6v.4',
    portfolio: 'M11 3.6A8.5 8.5 0 1 0 20.4 13H11zM14 3.4V10h6.6A7 7 0 0 0 14 3.4z',
    report: 'M6 3.5h12v17H6zM9 8h6M9 11.5h6M9 15h3.5',
  };

  /* ---------- the checks above the map ---------- */
  const CHECKS = [
    ['profile', 'Your limits'], ['plan', 'Plan'], ['research', 'Research'], ['review', 'Review'],
    ['debate', 'Debate'], ['evidence', 'Evidence', true], ['decision', 'Decision'], ['sizing', 'Sizing'], ['report', 'Report'],
  ];

  /* ---------- layouts ---------- */
  // Wide: left to right in the order a run usually goes.
  const WIDE = (() => {
    const W = 176, H = 66, HH = 80;
    const n = (x, cy, h = H, w = W) => ({x, y: cy - h / 2, w, h});
    return {
      w: 1310, h: 550,
      nodes: {
        you: n(16, 284, 56, 120),
        profile: n(188, 148), planner: n(188, 284, HH),
        market: n(420, 116), fund: n(420, 228), news: n(420, 340), docs: n(420, 452),
        check: n(652, 284, HH),
        strategy: n(884, 182), risk: n(884, 386),
        portfolio: n(1116, 182), report: n(1116, 386),
      },
      edges: [
        ['you', 'planner', 'right', 'left'],
        ['planner', 'profile', 'top', 'bottom'],
        ['planner', 'market', 'right', 'left', {x: 392}], ['planner', 'fund', 'right', 'left', {x: 392}],
        ['planner', 'news', 'right', 'left', {x: 392}], ['planner', 'docs', 'right', 'left', {x: 392}],
        ['market', 'check', 'right', 'left', {x: 624}], ['fund', 'check', 'right', 'left', {x: 624}],
        ['news', 'check', 'right', 'left', {x: 624}], ['docs', 'check', 'right', 'left', {x: 624}],
        ['check', 'strategy', 'right', 'left', {x: 856}], ['check', 'risk', 'right', 'left', {x: 856}],
        ['strategy', 'risk', 'bottom', 'top'],
        ['risk', 'portfolio', 'right', 'left', {x: 1088}],
        ['portfolio', 'report', 'bottom', 'top'],
        ['report', 'you', 'bottom', 'bottom', {y: 524}],
      ],
      loop: 'market',
      captions: [[76, 'You ask'], [276, 'Plan'], [508, 'Research, in parallel'], [740, 'Review'], [972, 'Debate'], [1204, 'Decide']],
    };
  })();

  // Narrow (phones): top to bottom, analysts in one column fed by a bus on the left.
  const TALL = (() => {
    const n = (x, y, w, h) => ({x, y, w, h});
    const A = {market: 206, fund: 272, news: 338, docs: 404};
    const L = {
      w: 380, h: 830,
      nodes: {
        you: n(130, 14, 120, 48),
        profile: n(14, 98, 158, 62), planner: n(200, 92, 166, 74),
        market: n(80, A.market, 220, 58), fund: n(80, A.fund, 220, 58),
        news: n(80, A.news, 220, 58), docs: n(80, A.docs, 220, 58),
        check: n(98, 520, 184, 74),
        strategy: n(14, 636, 160, 58), risk: n(206, 636, 160, 58),
        portfolio: n(14, 742, 160, 58), report: n(206, 742, 160, 58),
      },
      edges: [
        ['you', 'planner', 'bottom', 'top', {y: 78}],
        ['planner', 'profile', 'left', 'right'],
        ['strategy', 'risk', 'right', 'left'],
        ['check', 'strategy', 'bottom', 'top', {y: 615}], ['check', 'risk', 'bottom', 'top', {y: 615}],
        ['risk', 'portfolio', 'bottom', 'top', {y: 718}],
        ['portfolio', 'report', 'right', 'left'],
      ],
      loop: 'market',
    };
    for (const a of ANALYSTS) {
      const cy = A[a] + 29;
      L.edges.push(['planner', a, 'bottom', 'left', null,
        [{x: 283, y: 166}, {x: 283, y: 188}, {x: 44, y: 188}, {x: 44, y: cy}, {x: 80, y: cy}]]);
      L.edges.push([a, 'check', 'right', 'top', null,
        [{x: 300, y: cy}, {x: 336, y: cy}, {x: 336, y: 496}, {x: 190, y: 496}, {x: 190, y: 520}]]);
    }
    L.edges.push(['report', 'you', 'bottom', 'right', null,
      [{x: 286, y: 800}, {x: 286, y: 816}, {x: 372, y: 816}, {x: 372, y: 38}, {x: 250, y: 38}]]);
    return L;
  })();

  /* ---------- geometry ---------- */
  function port(b, side) {
    if (side === 'left') return {x: b.x, y: b.y + b.h / 2};
    if (side === 'right') return {x: b.x + b.w, y: b.y + b.h / 2};
    if (side === 'top') return {x: b.x + b.w / 2, y: b.y};
    return {x: b.x + b.w / 2, y: b.y + b.h};
  }
  function points(L, [a, b, from, to, via, pts]) {
    if (pts) return pts;
    const p = port(L.nodes[a], from), q = port(L.nodes[b], to);
    const hz = s => s === 'left' || s === 'right';
    if (hz(from) && hz(to)) {
      if (Math.abs(p.y - q.y) < 0.5) return [p, q];
      const x = via && via.x != null ? via.x : (p.x + q.x) / 2;
      return [p, {x, y: p.y}, {x, y: q.y}, q];
    }
    if (!hz(from) && !hz(to)) {
      if (Math.abs(p.x - q.x) < 0.5 && !(via && via.y != null)) return [p, q];
      const y = via && via.y != null ? via.y : (p.y + q.y) / 2;
      return [p, {x: p.x, y}, {x: q.x, y}, q];
    }
    return hz(from) ? [p, {x: q.x, y: p.y}, q] : [p, {x: p.x, y: q.y}, q];
  }
  function rounded(pts, r = 12) {
    let d = `M${pts[0].x} ${pts[0].y}`;
    for (let i = 1; i < pts.length - 1; i++) {
      const a = pts[i - 1], c = pts[i], b = pts[i + 1];
      const d1 = Math.hypot(c.x - a.x, c.y - a.y), d2 = Math.hypot(b.x - c.x, b.y - c.y);
      const k = Math.min(r, d1 / 2, d2 / 2);
      const p1 = {x: c.x + (a.x - c.x) * k / d1, y: c.y + (a.y - c.y) * k / d1};
      const p2 = {x: c.x + (b.x - c.x) * k / d2, y: c.y + (b.y - c.y) * k / d2};
      d += ` L${p1.x} ${p1.y} Q${c.x} ${c.y} ${p2.x} ${p2.y}`;
    }
    const z = pts[pts.length - 1];
    return d + ` L${z.x} ${z.y}`;
  }

  function el(name, attrs, parent) {
    const n = document.createElementNS(NS, name);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function fit(t, max) {
    const full = t.textContent;
    if (t.getComputedTextLength() <= max) return;
    let lo = 0, hi = full.length;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      t.textContent = full.slice(0, mid).trimEnd() + '…';
      if (t.getComputedTextLength() <= max) lo = mid; else hi = mid - 1;
    }
    t.textContent = full.slice(0, lo).trimEnd() + '…';
    const title = el('title', {}); title.textContent = full; t.appendChild(title);
  }
  const human = tool => String(tool || '').replace(/^tool:/, '').replace(/^get_/, '').replace(/_/g, ' ');

  /* ---------- the component ---------- */
  function AgentFlow(host, opts = {}) {
    this.host = host; this.opts = opts;
    this.reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.speed = opts.speed || 1;
    this.root = document.createElement('div');
    this.root.className = 'af' + (opts.theme === 'dark' ? ' af-dark' : '');
    if (opts.checks !== false) {
      this.checksEl = document.createElement('ol');
      this.checksEl.className = 'af-checks';
      this.checksEl.setAttribute('aria-label', 'Progress of the run');
      this.checksEl.innerHTML = CHECKS.map(([id, label, hidden]) =>
        `<li data-check="${id}"${hidden ? ' hidden' : ''}><i aria-hidden="true"></i><span>${label}</span></li>`).join('');
      this.root.appendChild(this.checksEl);
    }
    this.stage = document.createElement('div');
    this.stage.className = 'af-stage';
    this.root.appendChild(this.stage);
    if (opts.legend !== false) {
      const lg = document.createElement('ul');
      lg.className = 'af-legend';
      lg.innerHTML = '<li class="lg-now">Message moving now</li><li class="lg-seen">Route used</li>' +
        '<li class="lg-obj">Objection or failure</li><li class="lg-ok">Approved</li><li class="lg-ask">Asking for evidence</li>' +
        '<li class="lg-skip">Not needed this run</li>';
      this.root.appendChild(lg);
    }
    host.appendChild(this.root);
    this.state = {}; this.seen = {}; this.checkState = {};
    this._resetRun();
    this.build();
    if (global.ResizeObserver) {
      let last = this.layout;
      new ResizeObserver(() => {
        const next = this.pickLayout();
        if (next !== last) { last = next; this.build(); }
      }).observe(host);
    }
  }

  AgentFlow.prototype.pickLayout = function () {
    if (this.opts.layout === 'wide') return WIDE;
    if (this.opts.layout === 'tall') return TALL;
    return (this.host.clientWidth || 1000) < 700 ? TALL : WIDE;
  };

  AgentFlow.prototype.build = function () {
    const L = this.layout = this.pickLayout();
    this.stage.textContent = '';
    this.root.classList.toggle('af-tall', L === TALL);
    const svg = this.svg = el('svg', {viewBox: `0 0 ${L.w} ${L.h}`, class: 'af-svg', role: 'img',
      'aria-label': this.opts.label || 'The committee: each agent, and the messages between them'});
    const defs = el('defs', {}, svg);
    const pat = el('pattern', {id: 'afgrid' + (this.uid = this.uid || Math.random().toString(36).slice(2, 7)),
      width: 26, height: 26, patternUnits: 'userSpaceOnUse'}, defs);
    el('path', {d: 'M26 0H0V26', class: 'af-gridline'}, pat);
    el('rect', {x: 0, y: 0, width: L.w, height: L.h, fill: `url(#afgrid${this.uid})`, class: 'af-grid'}, svg);
    for (const [x, text] of L.captions || []) {
      const c = el('text', {x, y: 26, class: 'af-caption'}, svg);
      c.textContent = text;
    }
    const gE = el('g', {class: 'af-edges'}, svg);
    const gP = el('g', {class: 'af-ports'}, svg);
    this.gPulse = el('g', {class: 'af-pulses'}, svg);
    const gN = el('g', {class: 'af-nodes'}, svg);
    this.edges = {}; this.adj = {}; this.ports = {};
    for (const spec of L.edges) {
      const [a, b] = spec;
      const pts = points(L, spec);
      const id = a + '>' + b;
      const path = el('path', {d: rounded(pts), class: 'af-edge', 'data-edge': id}, gE);
      this.edges[id] = {path, a, b};
      (this.adj[a] = this.adj[a] || []).push(b);
      (this.adj[b] = this.adj[b] || []).push(a);
      for (const [p, who] of [[pts[0], a], [pts[pts.length - 1], b]]) {
        const key = `${p.x},${p.y}`;
        if (!this.ports[key]) this.ports[key] = {c: el('circle', {cx: p.x, cy: p.y, r: 3.6, class: 'af-port'}, gP), ids: []};
        this.ports[key].ids.push(id);
      }
    }
    if (L.loop) {
      const b = L.nodes[L.loop];
      const x1 = b.x + b.w - 54, x2 = b.x + b.w - 18, y = b.y, top = y - 18;
      const path = el('path', {d: rounded([{x: x1, y}, {x: x1, y: top}, {x: x2, y: top}, {x: x2, y}], 7), class: 'af-edge af-loop'}, gE);
      this.edges.loop = {path, a: L.loop, b: L.loop};
    }
    this.nodes = {};
    for (const [id, spec] of Object.entries(NODES)) {
      const b = L.nodes[id];
      const g = el('g', {class: 'af-node' + (spec.hub ? ' hub' : '') + (spec.you ? ' you' : ''), 'data-node': id,
        transform: `translate(${b.x} ${b.y})`}, gN);
      el('rect', {class: 'af-card', width: b.w, height: b.h, rx: spec.you ? b.h / 2 : 14}, g);
      const big = spec.hub;
      const ix = spec.you ? 16 : 14, iy = spec.you ? (b.h - 20) / 2 : (big ? 15 : 12);
      const ico = el('g', {class: 'af-ico', transform: `translate(${ix} ${iy}) scale(${big ? 0.92 : 0.84})`}, g);
      el('path', {d: ICONS[spec.icon]}, ico);
      const title = el('text', {class: 'af-title', x: ix + (big ? 30 : 27), y: spec.you ? b.h / 2 + 5.5 : iy + (big ? 16 : 14.5)}, g);
      title.textContent = spec.label;
      let status = null;
      if (!spec.you) {
        status = el('text', {class: 'af-status', x: 14, y: b.h - (big ? 18 : 14)}, g);
      }
      const badge = el('g', {class: 'af-badge', transform: `translate(${b.w - 17} ${spec.you ? b.h / 2 : 17})`}, g);
      el('circle', {r: 7.5}, badge);
      el('path', {class: 'af-mark', d: ''}, badge);
      this.nodes[id] = {g, status, badge, w: b.w, title};
    }
    this.stage.appendChild(svg);
    // long names shrink a little rather than run into the status badge
    for (const id in this.nodes) {
      const n = this.nodes[id], room = n.w - 30 - Number(n.title.getAttribute('x'));
      let size = parseFloat(getComputedStyle(n.title).fontSize) || 15;
      while (n.title.getComputedTextLength() > room && size > 12) { size -= 0.5; n.title.style.fontSize = size + 'px'; }
    }
    // restore what has happened so far without animating it again
    for (const id in this.nodes) this._paint(id);
    for (const id in this.seen) if (this.edges[id]) this.edges[id].path.setAttribute('class', 'af-edge seen ' + this.seen[id] + (id === 'loop' ? ' af-loop' : ''));
    this._ports();
  };

  AgentFlow.prototype._ports = function () {
    for (const k in this.ports) {
      const p = this.ports[k];
      p.c.classList.toggle('on', p.ids.some(id => this.seen[id] !== undefined));
    }
  };

  const MARKS = {
    done: 'M-3.4 0.2l2.2 2.2 4.4-4.6',
    failed: 'M0 -3.6v4M0 2.9v.3',
    warn: 'M0 -3.6v4M0 2.9v.3',
    fallback: 'M-2.8 -3h3.1a1.8 1.8 0 0 1 0 3.6h-3.1zM-2.8 0.6V3.6M0.4 0.6l2.4 3',
    skipped: 'M-3 0h6',
  };
  AgentFlow.prototype._paint = function (id) {
    const n = this.nodes[id], s = this.state[id] || {};
    if (!n) return;
    const spec = NODES[id];
    const cls = ['af-node'];
    if (spec.hub) cls.push('hub'); if (spec.you) cls.push('you');
    if (s.st) cls.push(s.st);
    if (s.fallback) cls.push('fallback');
    if (this.active === id) cls.push('active');
    n.g.setAttribute('class', cls.join(' '));
    const mark = s.fallback && s.st === 'done' ? 'fallback' : s.st;
    n.badge.querySelector('.af-mark').setAttribute('d', MARKS[mark] || '');
    if (n.status) {
      n.status.textContent = s.text || spec.idle;
      fit(n.status, n.w - 26);
    }
  };

  /* ---------- low-level API (used by scripted walkthroughs) ---------- */
  AgentFlow.prototype.node = function (id, st, text, extra = {}) {
    const s = this.state[id] = Object.assign(this.state[id] || {}, extra);
    if (st !== undefined) s.st = st;
    if (text !== undefined) s.text = text;
    this._paint(id);
  };
  AgentFlow.prototype.focus = function (id) {
    const prev = this.active;
    this.active = id;
    if (prev && prev !== id) this._paint(prev);
    if (id) this._paint(id);
  };
  AgentFlow.prototype.check = function (id, st, label, note) {
    if (!this.checksEl) return;
    const li = this.checksEl.querySelector(`[data-check="${id}"]`);
    if (!li) return;
    this.checkState[id] = st;
    li.hidden = false;
    li.className = st || '';
    if (label) li.querySelector('span').textContent = label;
    if (note) li.title = note;
  };
  AgentFlow.prototype._path = function (a, b) {
    if (a === b) return null;
    const prev = {[a]: null}, q = [a];
    while (q.length) {
      const x = q.shift();
      if (x === b) break;
      for (const y of this.adj[x] || []) if (!(y in prev)) { prev[y] = x; q.push(y); }
    }
    if (!(b in prev)) return null;
    const hops = [];
    for (let x = b; prev[x] !== null; x = prev[x]) hops.unshift([prev[x], x]);
    return hops;
  };
  /* Light the route from a to b (node ids) and run a pulse along it. kind: '', objection, approve, follow */
  AgentFlow.prototype.send = function (a, b, kind = '', dur, instant) {
    const hops = a === b && a === this.layout.loop ? [['loop', 'loop']] : this._path(a, b);
    if (!hops) return Promise.resolve();
    dur = (dur || 520) / this.speed;
    const legs = hops.map(([x, y]) => {
      if (x === 'loop') return {e: this.edges.loop, fwd: true, id: 'loop'};
      const id = this.edges[x + '>' + y] ? x + '>' + y : y + '>' + x;
      return {e: this.edges[id], fwd: this.edges[id].a === x, id};
    });
    for (const g of legs) {
      this.seen[g.id] = kind;
      g.e.path.setAttribute('class', `af-edge hot ${kind}` + (g.id === 'loop' ? ' af-loop' : ''));
    }
    this._ports();
    const settle = () => legs.forEach(g => {
      if (this.edges[g.id]) this.edges[g.id].path.setAttribute('class', `af-edge seen ${kind}` + (g.id === 'loop' ? ' af-loop' : ''));
    });
    if (instant) { settle(); return Promise.resolve(); }
    if (this.reduce || !this.svg.isConnected) { setTimeout(settle, 700); return Promise.resolve(); }
    return new Promise(done => {
      const dot = el('circle', {r: 6, class: 'af-pulse ' + kind}, this.gPulse);
      const halo = el('circle', {r: 13, class: 'af-halo ' + kind}, this.gPulse);
      let k = 0, t0 = performance.now();
      const step = now => {
        const g = legs[k];
        if (!g || !g.e.path.isConnected) { dot.remove(); halo.remove(); settle(); done(); return; }
        const len = g.e.path.getTotalLength();
        const t = Math.min(1, (now - t0) / Math.max(260, dur * Math.min(1.6, len / 220)));
        const e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
        const pt = g.e.path.getPointAtLength((g.fwd ? e : 1 - e) * len);
        dot.setAttribute('cx', pt.x); dot.setAttribute('cy', pt.y);
        halo.setAttribute('cx', pt.x); halo.setAttribute('cy', pt.y);
        if (t >= 1) { k += 1; t0 = now; }
        if (k < legs.length) requestAnimationFrame(step);
        else { dot.remove(); halo.remove(); setTimeout(settle, 900); done(); }
      };
      requestAnimationFrame(step);
    });
  };

  AgentFlow.prototype._resetRun = function () {
    this.run = {checked: false, asking: false, planned: 0, reported: 0, round: 0, failed: new Set()};
  };
  AgentFlow.prototype.reset = function () {
    this.state = {}; this.seen = {}; this.active = null; this.checkState = {};
    this._resetRun();
    if (this.gPulse) this.gPulse.textContent = '';
    for (const id in this.edges) this.edges[id].path.setAttribute('class', 'af-edge' + (id === 'loop' ? ' af-loop' : ''));
    for (const id in this.nodes) this._paint(id);
    this._ports();
    if (this.checksEl) this.checksEl.querySelectorAll('li').forEach((li, i) => {
      li.className = ''; li.removeAttribute('title');
      li.querySelector('span').textContent = CHECKS[i][1];
      li.hidden = !!CHECKS[i][2];
    });
  };

  /* ---------- events: the same shape the server streams and logs ---------- */
  AgentFlow.prototype.who = function (name, other, out) {
    if (!name) return null;
    if (AGENT[name]) return AGENT[name];
    if (name === 'Planner' || name === 'team' || name === 'committee') {
      const o = AGENT[other];
      if (o === 'you' || o === 'profile') return 'planner';
      if (ANALYSTS.includes(o)) return out && !this.run.checked ? 'planner' : 'check';
      if (!o) return this.run.checked ? 'check' : 'planner';
      return 'check';
    }
    return null;
  };

  AgentFlow.prototype.apply = function (e, opts = {}) {
    const p = e.payload || {}, R = this.run, t = e.type;
    if (t === 'assessment' || t === 'arbitration' || t === 'reconciliation' || t === 'challenge') R.checked = true;
    const toolFrom = String(e.from || '').startsWith('tool:'), toolTo = String(e.to || '').startsWith('tool:');
    const a = toolFrom ? null : this.who(e.from, e.to, true);
    const b = toolTo ? null : this.who(e.to, e.from, false);
    const fallback = e.llm && e.llm.ok === false;
    if (a && fallback) this.node(a, undefined, undefined, {fallback: true});
    let kind = '';

    switch (t) {
      case 'request':
        this.node('you', 'done', `Asked about ${p.ticker || 'a stock'}`);
        this.node('planner', 'working', 'Reading your request');
        break;
      case 'memory':
        this.node('planner', 'working', 'Read your last analysis');
        break;
      case 'task':
        if (b === 'profile') this.check('profile', 'active');
        if (R.asking) kind = 'follow';
        if (ANALYSTS.includes(b) && R.failed.has(b)) kind = 'objection';
        this.node(b, 'working', p.instruction ? cap(p.instruction) : 'Working');
        if (b === 'risk' && !R.round) this.check('debate', 'active', 'Risk scoring');
        if (b === 'portfolio') this.check('sizing', 'active');
        if (b === 'report') this.check('report', 'active');
        break;
      case 'tool_call':
        this.node(a, 'working', `Using ${human(e.to)}`);
        this.focus(a);
        return {from: a, to: null, kind};
      case 'tool_result': {
        const who = this.who(e.to, null, false);
        if (p.ok === false) {
          this.node(who, 'warn', 'A source failed, trying another');
          if (who === this.layout.loop && opts.animate !== false) this.send(who, who, 'objection');
        }
        return {from: null, to: who, kind: p.ok === false ? 'objection' : ''};
      }
      case 'result': {
        this.node(a, 'done', summary(a, p));
        if (a === 'profile') this.check('profile', 'done', 'Your limits', p.profileSummary);
        if (ANALYSTS.includes(a)) {
          R.reported += 1; R.failed.delete(a);
          this.check('research', 'active', `Research ${R.reported}/${R.planned || R.reported}`);
          this.node('check', 'working', `Collecting reports ${R.reported}/${R.planned || R.reported}`);
        }
        if (a === 'risk') this.node('check', 'working', 'Risk scored');
        if (a === 'portfolio') this.check('sizing', 'done', 'Sizing');
        break;
      }
      case 'error':
        this.node(a, 'failed', cap('Failed: ' + (p.error || 'no answer')));
        if (ANALYSTS.includes(a)) { R.failed.add(a); this.check('research', 'warn', 'Research: a failure'); }
        kind = 'objection';
        break;
      case 'plan': {
        const chosen = (p.tasks || []).map(x => AGENT[x.agent]).filter(Boolean);
        R.planned = chosen.filter(x => ANALYSTS.includes(x)).length;
        ANALYSTS.filter(x => !chosen.includes(x)).forEach(x =>
          this.node(x, 'skipped', x === 'docs' ? 'No PDF attached' : 'Not needed this time'));
        this.node('planner', 'done', `Chose ${R.planned} analysts`);
        this.check('plan', 'done', 'Plan', p.focus || '');
        this.check('research', 'active', `Research 0/${R.planned}`);
        this.focus('planner');
        return {from: 'planner', to: null, kind};
      }
      case 'assessment':
        if (p.action === 'retry') {
          this.node('check', 'warn', 'Re-planning failed work');
          this.check('review', 'warn', 'Review: re-plan');
        } else {
          this.node('check', 'done', 'Reports checked');
          this.check('review', 'done', 'Review');
          this.check('research', 'done', `Research ${R.reported}/${R.planned || R.reported}`);
        }
        this.focus('check');
        return {from: 'check', to: null, kind};
      case 'replan':
        kind = 'objection';
        this.node(b, 'working', cap('Retry: ' + (p.instruction || '')));
        break;
      case 'draft':
        R.round = e.round || R.round + 1;
        this.node('strategy', 'done', `Round ${R.round}: ${p.recommendation || 'draft'}`);
        this.node('risk', 'working', 'Reviewing the draft');
        this.check('debate', 'active', `Debate, round ${R.round}`);
        break;
      case 'critique':
        if (p.verdict === 'approve') {
          kind = 'approve';
          this.node('risk', 'done', `Approved in round ${e.round || R.round}`);
          this.check('debate', 'done', `Approved, round ${e.round || R.round}`);
        } else {
          kind = 'objection';
          this.node('risk', 'warn', `Round ${e.round || R.round}: objection`);
          this.node('strategy', 'working', 'Answering the objections');
          this.check('debate', 'warn', `Objection, round ${e.round || R.round}`);
        }
        break;
      case 'followup':
        kind = 'follow'; R.asking = true;
        this.node('risk', 'working', 'Asked for evidence');
        this.check('evidence', 'active', 'Evidence');
        break;
      case 'answer':
        kind = 'follow'; R.asking = false;
        this.node(a, 'done', 'Answered the question');
        this.check('evidence', 'done', 'Evidence');
        break;
      case 'challenge':
        kind = 'objection';
        this.node(a, 'warn', 'Challenging the figures');
        break;
      case 'reply':
        this.node(a, 'done', 'Explained its figures');
        break;
      case 'reconciliation':
        this.node('check', 'working', cap(`Settled: trust ${p.trust || ''}`));
        this.focus('check');
        return {from: 'check', to: null, kind};
      case 'arbitration':
        this.node('check', 'done', `Ruled ${p.recommendation || ''}`);
        this.check('debate', 'warn', 'Planner ruled');
        this.focus('check');
        return {from: 'check', to: null, kind};
      case 'decision':
        if (p.followup || (b && b !== 'check' && !p.recommendation)) {
          kind = 'follow';
          this.node('check', 'working', 'Sending an analyst back');
          break;
        }
        if (p.recommendation) {
          this.node('check', 'done', `Decided ${p.recommendation}`);
          this.check('decision', 'done', `Decision: ${p.recommendation}`);
          this.focus('check');
          return {from: 'check', to: null, kind, verdict: p.recommendation};
        }
        break;
      case 'final':
        this.node('report', 'done', 'Report written');
        this.node('you', 'done', 'Got the verdict');
        this.check('report', 'done', 'Report');
        break;
    }
    if (a) this.focus(a);
    if (a && b && a !== b) this.send(a, b, kind, undefined, opts.animate === false);
    return {from: a, to: b, kind};
  };

  function cap(s, n = 60) { s = String(s || ''); return s.charAt(0).toUpperCase() + s.slice(1, n); }
  function summary(id, p) {
    if (id === 'profile' && p.riskCapacityScore != null) return `Risk capacity ${p.riskCapacityScore}/100`;
    if (id === 'market' && p.trend) return `${cap(p.trend)}${p.rsi != null ? ', RSI ' + Math.round(p.rsi) : ''}`;
    if (id === 'fund' && p.financialHealth) return `${cap(p.financialHealth)} health`;
    if (id === 'news' && p.newsSentiment) return `${cap(p.newsSentiment)} news`;
    if (id === 'docs' && p.documentPagesUsed) return `Read pages ${p.documentPagesUsed.slice(0, 4).join(', ')}`;
    if (id === 'risk' && p.riskLevel) return `${cap(p.riskLevel)} risk${p.riskScore != null ? ', ' + p.riskScore + '/100' : ''}`;
    if (id === 'portfolio' && p.positionPct != null) return Number(p.positionPct) > 0 ? `${p.positionPct}% of your money` : 'No new money';
    return 'Reported';
  }

  AgentFlow.NODES = NODES;
  AgentFlow.AGENT = AGENT;
  global.AgentFlow = AgentFlow;
})(window);
