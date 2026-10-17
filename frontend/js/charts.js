/* Quantum Advisor charts: small, dependency-free SVG charts with a shared tooltip.
   Every chart has a hover/focus tooltip and its numbers are also visible as text
   (labels, tiles or a table), so nothing is only reachable by hovering. */

const SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#6250d6']; // validated categorical order
const GAIN = '#2a78d6', LOSS = '#d03b3b', INK = '#1B2433', MUTED = '#6B7480', GRID = '#E3E7E2';
const NS = 'http://www.w3.org/2000/svg';

function svgEl(tag, attrs = {}, parent) {
  const el = document.createElementNS(NS, tag);
  Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
  if (parent) parent.appendChild(el);
  return el;
}
function svgText(parent, x, y, text, attrs = {}) {
  const t = svgEl('text', {x, y, 'font-size': 11.5, fill: MUTED, ...attrs}, parent);
  t.textContent = text;
  return t;
}
function niceTicks(lo, hi, count = 4) {
  const span = hi - lo || 1, raw = span / count, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => span / s <= count) || mag * 10;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}
function compact(n) {
  const a = Math.abs(n);
  if (a >= 1e7) return (n / 1e7).toFixed(1).replace(/\.0$/, '') + ' cr';
  if (a >= 1e5) return (n / 1e5).toFixed(1).replace(/\.0$/, '') + ' L';
  if (a >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, '') + 'K';
  return String(Math.round(n));
}
function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString('en-IN', {day: 'numeric', month: 'short'});
}
function movingAverage(ys, n) {
  return ys.map((_, i) => i + 1 < n ? null : ys.slice(i + 1 - n, i + 1).reduce((a, b) => a + b, 0) / n);
}

/* ---------- shared tooltip (values lead, labels follow; built with textContent) ---------- */
const tip = document.createElement('div');
tip.className = 'chart-tip'; tip.hidden = true; tip.setAttribute('role', 'status');
document.body.appendChild(tip);
function showTip(clientX, clientY, title, rows) {
  tip.replaceChildren();
  const h = document.createElement('div'); h.className = 'tip-title'; h.textContent = title; tip.appendChild(h);
  rows.forEach(([key, value, color]) => {
    const r = document.createElement('div'); r.className = 'tip-row';
    if (color) { const k = document.createElement('i'); k.style.background = color; r.appendChild(k); }
    const v = document.createElement('b'); v.textContent = value; r.appendChild(v);
    const l = document.createElement('span'); l.textContent = key; r.appendChild(l);
    tip.appendChild(r);
  });
  tip.hidden = false;
  const pad = 14, w = tip.offsetWidth, hgt = tip.offsetHeight;
  let x = clientX + pad, y = clientY + pad;
  if (x + w > window.innerWidth - 8) x = clientX - w - pad;
  if (y + hgt > window.innerHeight - 8) y = clientY - hgt - pad;
  tip.style.left = Math.max(8, x) + 'px'; tip.style.top = Math.max(8, y) + 'px';
}
function hideTip() { tip.hidden = true; }
function hoverable(el, title, rows) {
  el.setAttribute('tabindex', '0');
  const show = e => {
    const r = el.getBoundingClientRect();
    showTip(e.clientX ?? r.right, e.clientY ?? r.top, title, rows);
  };
  el.addEventListener('pointermove', show);
  el.addEventListener('focus', () => { const r = el.getBoundingClientRect(); showTip(r.right, r.top, title, rows); });
  el.addEventListener('pointerleave', hideTip);
  el.addEventListener('blur', hideTip);
}

/* ---------- price chart: price + MA20/MA50, targets, volume panel, ranges, crosshair ---------- */
function mountPriceChart(host, d) {
  const all = d.priceHistory || [];
  if (all.length < 2) { host.innerHTML = '<p class="caption">No price history returned for a chart.</p>'; return; }
  const dates = d.priceDates && d.priceDates.length === all.length ? d.priceDates : null;
  const vols = d.volumeHistory && d.volumeHistory.length === all.length ? d.volumeHistory : null;
  const ma20All = movingAverage(all, 20), ma50All = movingAverage(all, 50);
  const bbAll = all.map((_, i) => {           // Bollinger bands: 20-day average +/- 2 standard deviations
    if (i < 19) return null;
    const w = all.slice(i - 19, i + 1), m = w.reduce((a, b) => a + b, 0) / 20;
    const sd = Math.sqrt(w.reduce((a, b) => a + (b - m) ** 2, 0) / 19);
    return [m - 2 * sd, m + 2 * sd];
  });
  const ranges = [['1M', 22], ['3M', 66], ['6M', all.length]].filter(([, n]) => n <= all.length || n === all.length);
  const state = {n: Math.min(66, all.length), ma20: true, ma50: all.length >= 60, bb: false};

  host.innerHTML = `
    <div class="chart-controls">
      <div class="seg" role="group" aria-label="Time range">${ranges.map(([l, n]) =>
        `<button type="button" data-n="${n}">${l}</button>`).join('')}</div>
      <label class="key"><input type="checkbox" data-ma="ma20" ${state.ma20 ? 'checked' : ''}><i style="background:${SERIES[0]}"></i>20-day average</label>
      ${all.length >= 60 ? `<label class="key"><input type="checkbox" data-ma="ma50" checked><i style="background:${SERIES[1]}"></i>50-day average</label>` : ''}
      ${all.length >= 25 ? `<label class="key"><input type="checkbox" data-ma="bb"><i style="background:${SERIES[2]};opacity:.5"></i>Bollinger bands</label>` : ''}
    </div>
    <div class="pchart"></div>
    ${vols ? '<div class="vchart"></div>' : ''}`;
  const plot = host.querySelector('.pchart'), vplot = host.querySelector('.vchart');

  function draw() {
    const n = Math.min(state.n, all.length), off = all.length - n;
    const ys = all.slice(off), ma20 = ma20All.slice(off), ma50 = ma50All.slice(off), bb = bbAll.slice(off);
    const ds = dates ? dates.slice(off) : null, vs = vols ? vols.slice(off) : null;
    host.querySelectorAll('.seg button').forEach(b => b.setAttribute('aria-pressed', String(+b.dataset.n === state.n)));

    const W = Math.max(320, Math.round(plot.clientWidth || 960)), narrow = W < 560;
    const H = narrow ? 220 : 280, padL = 6, padR = narrow ? 92 : 130, padT = 12, padB = 24;
    const levels = [['Target 2', d.targetPrice2], ['Target 1', d.targetPrice1], ['Stop-loss', d.stopLoss]]
      .filter(l => typeof l[1] === 'number');
    const shown = ys.concat(state.ma20 ? ma20.filter(v => v != null) : [], state.ma50 ? ma50.filter(v => v != null) : [],
                            levels.map(l => l[1]), state.bb ? bb.filter(Boolean).flat() : []);
    let lo = Math.min(...shown), hi = Math.max(...shown); const pad = (hi - lo) * 0.06 || 1; lo -= pad; hi += pad;
    const x = i => padL + i * (W - padL - padR) / Math.max(1, ys.length - 1);
    const y = v => padT + (hi - v) * (H - padT - padB) / (hi - lo);

    plot.replaceChildren();
    const svg = svgEl('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', tabindex: '0',
      'aria-label': `Closing prices for the last ${ys.length} trading days. Use the arrow keys to read values.`}, plot);
    const levelYs = levels.map(l => y(l[1]));
    niceTicks(lo, hi, 4).forEach(t => {
      svgEl('line', {x1: padL, x2: W - padR, y1: y(t), y2: y(t), stroke: GRID, 'stroke-width': 1}, svg);
      if (levelYs.every(ly => Math.abs(ly - y(t)) > 13))      // never collide with a target label
        svgText(svg, W - padR + 6, y(t) + 4, Math.round(t).toLocaleString('en-IN'));
    });
    const path = arr => arr.map((v, i) => v == null ? '' : `${i && arr[i - 1] != null ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join('');
    const area = `${path(ys)}L${x(ys.length - 1).toFixed(1)} ${H - padB}L${padL} ${H - padB}Z`;
    svgEl('path', {d: area, fill: INK, opacity: 0.06}, svg);
    if (state.bb) {
      const lowB = bb.map(b => b && b[0]), upB = bb.map(b => b && b[1]);
      const first = bb.findIndex(Boolean);
      if (first >= 0) {
        const band = upB.slice(first).map((v, k) => `${k ? 'L' : 'M'}${x(first + k).toFixed(1)} ${y(v).toFixed(1)}`).join('') +
          lowB.slice(first).map((v, k, a) => `L${x(first + a.length - 1 - k).toFixed(1)} ${y(a[a.length - 1 - k]).toFixed(1)}`).join('') + 'Z';
        svgEl('path', {d: band, fill: SERIES[2], opacity: 0.12}, svg);
        [lowB, upB].forEach(arr => svgEl('path', {d: path(arr), fill: 'none', stroke: SERIES[2], 'stroke-width': 1, 'stroke-dasharray': '4 3'}, svg));
      }
    }
    if (state.ma50) svgEl('path', {d: path(ma50), fill: 'none', stroke: SERIES[1], 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}, svg);
    if (state.ma20) svgEl('path', {d: path(ma20), fill: 'none', stroke: SERIES[0], 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}, svg);
    svgEl('path', {d: path(ys), fill: 'none', stroke: INK, 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}, svg);
    levels.forEach(([name, v]) => {
      const c = name === 'Stop-loss' ? LOSS : '#2F6B4F';
      svgEl('line', {x1: padL, x2: W - padR, y1: y(v), y2: y(v), stroke: c, 'stroke-width': 1, opacity: 0.8}, svg);
      svgText(svg, W - padR + 6, y(v) + 4, narrow ? `₹${Math.round(v).toLocaleString('en-IN')}` : `${name} ₹${Math.round(v).toLocaleString('en-IN')}`, {fill: name === 'Stop-loss' ? '#8A2C25' : INK, 'font-weight': 600, 'font-size': 11});
    });
    const last = ys.length - 1;
    svgEl('circle', {cx: x(last), cy: y(ys[last]), r: 4.5, fill: INK, stroke: '#FAFBF8', 'stroke-width': 2}, svg);
    const xl = ds ? [[0, fmtDate(ds[0])], [Math.floor(last / 2), fmtDate(ds[Math.floor(last / 2)])], [last, fmtDate(ds[last])]]
                  : [[0, `${ys.length} days ago`], [last, 'Today']];
    xl.forEach(([i, t], k) => svgText(svg, x(i), H - 6, t, {'text-anchor': k === 0 ? 'start' : k === xl.length - 1 ? 'end' : 'middle'}));

    // crosshair
    const cross = svgEl('line', {y1: padT, y2: H - padB, stroke: MUTED, 'stroke-width': 1, visibility: 'hidden'}, svg);
    const dot = svgEl('circle', {r: 4.5, fill: INK, stroke: '#FAFBF8', 'stroke-width': 2, visibility: 'hidden'}, svg);
    let idx = last;
    const point = (i, cx, cy) => {
      idx = Math.max(0, Math.min(last, i));
      cross.setAttribute('x1', x(idx)); cross.setAttribute('x2', x(idx)); cross.setAttribute('visibility', 'visible');
      dot.setAttribute('cx', x(idx)); dot.setAttribute('cy', y(ys[idx])); dot.setAttribute('visibility', 'visible');
      const rows = [[ 'close', inr(ys[idx]), INK]];
      if (state.ma20 && ma20[idx] != null) rows.push(['20-day average', inr(ma20[idx]), SERIES[0]]);
      if (state.ma50 && ma50[idx] != null) rows.push(['50-day average', inr(ma50[idx]), SERIES[1]]);
      if (state.bb && bb[idx]) rows.push(['Bollinger range', `${inr(bb[idx][0], 0)} – ${inr(bb[idx][1], 0)}`, SERIES[2]]);
      if (vs) rows.push(['shares traded', compact(vs[idx])]);
      const chg = (ys[idx] / ys[0] - 1) * 100;
      rows.push([`since ${ds ? fmtDate(ds[0]) : 'start of range'}`, `${chg >= 0 ? '+' : ''}${chg.toFixed(1)}%`]);
      const b = svg.getBoundingClientRect();
      showTip(cx ?? b.left + x(idx) / W * b.width, cy ?? b.top + 20, ds ? new Date(ds[idx] + 'T00:00:00').toLocaleDateString('en-IN', {weekday: 'short', day: 'numeric', month: 'short', year: 'numeric'}) : `${last - idx} trading days ago`, rows);
    };
    svg.addEventListener('pointermove', e => {
      const b = svg.getBoundingClientRect(), px = (e.clientX - b.left) / b.width * W;
      point(Math.round((px - padL) / (W - padL - padR) * last), e.clientX, e.clientY);
    });
    svg.addEventListener('pointerleave', () => { hideTip(); cross.setAttribute('visibility', 'hidden'); dot.setAttribute('visibility', 'hidden'); });
    svg.addEventListener('focus', () => point(idx));
    svg.addEventListener('blur', hideTip);
    svg.addEventListener('keydown', e => {
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); point(idx + (e.key === 'ArrowRight' ? 1 : -1)); }
    });

    if (vplot && vs) {
      vplot.replaceChildren();
      const VH = 70, vmax = Math.max(...vs) || 1;
      const vsvg = svgEl('svg', {viewBox: `0 0 ${W} ${VH}`, role: 'img', 'aria-label': 'Shares traded each day'}, vplot);
      const bw = Math.max(1, Math.min(24, (W - padL - padR) / vs.length - 2));
      const avg = vs.reduce((a, b) => a + b, 0) / vs.length;
      vs.forEach((v, i) => {
        const h = Math.max(1, v / vmax * (VH - 18));
        svgEl('rect', {x: x(i) - bw / 2, y: VH - 4 - h, width: bw, height: h, rx: Math.min(2, bw / 2),
                       fill: v > avg * 1.5 ? SERIES[0] : '#B9C3CF'}, vsvg);
      });
      svgText(vsvg, W - padR + 6, 14, 'Volume', {'font-weight': 600, fill: INK});
      svgText(vsvg, W - padR + 6, 28, `avg ${compact(avg)}`);
      if (!narrow) svgText(vsvg, W - padR + 6, 42, 'blue: 1.5× avg');
    }
  }
  let rt; const ro = new ResizeObserver(() => { clearTimeout(rt); rt = setTimeout(draw, 120); });
  ro.observe(plot);
  host.querySelectorAll('.seg button').forEach(b => b.addEventListener('click', () => { state.n = +b.dataset.n; draw(); }));
  host.querySelectorAll('input[data-ma]').forEach(c => c.addEventListener('change', () => { state[c.dataset.ma] = c.checked; draw(); }));
  draw();
}

/* ---------- horizontal bars (one series) with value at the tip ---------- */
function hBars(rows, {unit = '', color = SERIES[0], max} = {}) {
  // rows: [{label, value, note}]
  const top = max ?? Math.max(1, ...rows.map(r => Math.abs(r.value)));
  return `<div class="hbars">${rows.map(r => `
    <div class="hbar-row" data-label="${esc(r.label)}" data-value="${r.value}" data-note="${esc(r.note || '')}">
      <span class="hbar-label">${esc(r.label)}</span>
      <span class="hbar-track"><span class="hbar-fill ${r.value < 0 ? 'neg' : ''}" style="width:${Math.abs(r.value) / top * 100}%;background:${r.value < 0 ? '#9FB0A6' : color}"></span></span>
      <span class="hbar-value">${r.value > 0 ? '+' : r.value < 0 ? '−' : ''}${Math.abs(r.value)}${unit}</span>
    </div>`).join('')}</div>`;
}
function wireHBars(root, titleFn) {
  root.querySelectorAll('.hbar-row').forEach(row => hoverable(row, row.dataset.label,
    [[titleFn ? titleFn(row) : '', (+row.dataset.value > 0 ? '+' : '') + row.dataset.value]].concat(row.dataset.note ? [[row.dataset.note, '']] : [])));
}

/* ---------- diverging bars around zero (gains vs losses) ---------- */
function divergingBars(rows) {
  // rows: [{label, value (pct), sub}]
  const m = Math.max(1, ...rows.map(r => Math.abs(r.value)));
  return `<div class="dbars">${rows.map(r => {
    const w = Math.abs(r.value) / m * 50, neg = r.value < 0;
    return `<div class="dbar-row" data-label="${esc(r.label)}" data-value="${r.value.toFixed(1)}" data-sub="${esc(r.sub || '')}">
      <span class="dbar-label">${esc(r.label)}</span>
      <span class="dbar-track"><span class="dbar-zero"></span>
        <span class="dbar-fill" style="${neg ? `right:50%;width:${w}%;background:${LOSS}` : `left:50%;width:${w}%;background:${GAIN}`}"></span></span>
      <span class="dbar-value">${r.value >= 0 ? '+' : '−'}${Math.abs(r.value).toFixed(1)}%</span>
    </div>`;
  }).join('')}<div class="dbar-axis"><span>loss</span><span>0</span><span>gain</span></div></div>`;
}

/* ---------- scatter: holding volatility vs weight ---------- */
function mountRiskMap(host, stocks) {
  if (!host._ro) {
    let t; host._ro = new ResizeObserver(() => { clearTimeout(t); t = setTimeout(() => drawRiskMap(host, host._stocks), 120); });
    host._ro.observe(host);
  }
  host._stocks = stocks;
  drawRiskMap(host, stocks);
}
function drawRiskMap(host, stocks) {
  const pts = stocks.filter(s => s.volatility != null);
  if (pts.length < 2) { host.innerHTML = '<p class="caption">Needs live prices for at least two holdings.</p>'; return; }
  const W = Math.max(320, Math.round(host.clientWidth || 960)), narrow = W < 560;
  const H = narrow ? 300 : 340, padL = 44, padR = 16, padT = 30, padB = 46;
  const xmax = Math.max(3, ...pts.map(p => p.volatility)) * 1.1, ymax = Math.max(10, ...pts.map(p => p.weight)) * 1.15;
  const x = v => padL + v / xmax * (W - padL - padR), y = v => padT + (1 - v / ymax) * (H - padT - padB);
  host.replaceChildren();
  const svg = svgEl('svg', {viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Each holding by daily volatility and share of the portfolio'}, host);
  const vx = 1.8, wy = Math.min(20, ymax * 0.6);
  svgEl('rect', {x: x(vx), y: padT, width: W - padR - x(vx), height: Math.max(0, y(wy) - padT), fill: LOSS, opacity: 0.05}, svg);
  svgText(svg, W - padR - 6, padT + 16, 'large and volatile', {'text-anchor': 'end', fill: '#8A2C25', 'font-weight': 600, 'font-size': 12});
  svgText(svg, padL, 14, 'Share of portfolio', {fill: INK, 'font-size': 12, 'font-weight': 600});
  niceTicks(0, ymax, 4).forEach(t => {
    svgEl('line', {x1: padL, x2: W - padR, y1: y(t), y2: y(t), stroke: GRID}, svg);
    svgText(svg, padL - 8, y(t) + 4, t + '%', {'text-anchor': 'end', 'font-size': 12});
  });
  niceTicks(0, xmax, 5).forEach(t => svgText(svg, x(t), H - 26, t + '%', {'text-anchor': 'middle', 'font-size': 12}));
  svgText(svg, (padL + W - padR) / 2, H - 6, narrow ? 'Daily volatility' : 'Daily volatility: how much the price moves on a typical day',
          {'text-anchor': 'middle', fill: INK, 'font-size': 12, 'font-weight': 600});

  // dots first, then labels placed greedily so they never overlap each other or a dot
  const placed = [];
  const boxes = pts.map(p => ({x: x(p.volatility) - 7, y: y(p.weight) - 7, w: 14, h: 14}));
  const hits = (b) => placed.concat(boxes).some(o => b.x < o.x + o.w && b.x + b.w > o.x && b.y < o.y + o.h && b.y + b.h > o.y);
  pts.slice().sort((a, b) => b.weight - a.weight).forEach(p => {
    const cx = x(p.volatility), cy = y(p.weight);
    const g = svgEl('g', {class: 'pt'}, svg);
    svgEl('circle', {cx, cy, r: 14, fill: 'transparent'}, g);                    // hit area
    svgEl('circle', {cx, cy, r: 6, fill: p.pnlPct >= 0 ? GAIN : LOSS, stroke: '#FAFBF8', 'stroke-width': 2}, g);
    hoverable(g, p.ticker, [['of the portfolio', p.weight + '%'], ['daily volatility', p.volatility + '%'],
                            ['return', `${p.pnlPct >= 0 ? '+' : ''}${p.pnlPct.toFixed(1)}%`, p.pnlPct >= 0 ? GAIN : LOSS]]);
    const w = p.ticker.length * 7.4 + 4, h = 14;
    const spots = [[cx + 10, cy - 7], [cx - 10 - w, cy - 7], [cx - w / 2, cy - 22], [cx - w / 2, cy + 9],
                   [cx + 10, cy - 20], [cx + 10, cy + 6], [cx - 10 - w, cy - 20], [cx - 10 - w, cy + 6]];
    const spot = spots.map(([bx, by]) => ({x: bx, y: by, w, h}))
      .find(b => b.x >= padL && b.x + b.w <= W - padR && b.y >= padT - 4 && b.y + b.h <= H - padB && !hits(b));
    if (spot) {
      placed.push(spot);
      svgText(g, spot.x + 2, spot.y + 11, p.ticker, {fill: INK, 'font-weight': 600, 'font-size': 12});
    } // no free spot: the tooltip and the holdings table carry the name
  });
}

/* ---------- sparkline ---------- */
function sparkline(ys, w = 96, h = 26) {
  if (!ys || ys.length < 2) return '<span class="caption">–</span>';
  const lo = Math.min(...ys), hi = Math.max(...ys), r = hi - lo || 1;
  const pts = ys.map((v, i) => `${(i / (ys.length - 1) * (w - 6) + 1).toFixed(1)},${(2 + (hi - v) / r * (h - 4)).toFixed(1)}`).join(' ');
  const up = ys[ys.length - 1] >= ys[0];
  const [lx, ly] = pts.split(' ').pop().split(',');
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-label="${ys.length}-day trend, ${up ? 'up' : 'down'} ${Math.abs((ys[ys.length - 1] / ys[0] - 1) * 100).toFixed(1)}%">
    <polyline points="${pts}" fill="none" stroke="${INK}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${lx}" cy="${ly}" r="2.5" fill="${up ? GAIN : LOSS}"/></svg>`;
}

/* ---------- RSI meter with 30/70 zones ---------- */
function rsiMeter(rsi) {
  const v = Math.max(0, Math.min(100, +rsi || 0));
  return `<div class="meter" role="img" aria-label="RSI ${v.toFixed(0)} of 100; above 70 is overbought, below 30 oversold">
    <span class="zone low"></span><span class="zone high"></span><span class="pin" style="left:${v}%"></span></div>
    <div class="meter-scale"><span>0</span><span>30</span><span>70</span><span>100</span></div>`;
}
