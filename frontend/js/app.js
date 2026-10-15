/* ================================================================
   AUTH GUARD — redirect to login if not logged in
================================================================ */
let currentUserEmail = null;

(async function checkAuth() {
  try {
    const res = await fetch('/me', { credentials: 'include' });
    const data = await res.json();
    if (!data.loggedIn) {
      window.location.href = 'login.html';
      return;
    }
    currentUserEmail = data.email;
    document.getElementById('profileEmail').textContent = data.email;
    document.getElementById('drawerEmail').textContent  = data.email;
  } catch(e) {
    window.location.href = 'login.html';
  }
})();

/* ================================================================
   DRAWER
================================================================ */
function toggleDrawer() {
  const d = document.getElementById('drawer');
  const o = document.getElementById('drawerOverlay');
  d.classList.toggle('open');
  o.classList.toggle('open');
}
function closeDrawer() {
  document.getElementById('drawer').classList.remove('open');
  document.getElementById('drawerOverlay').classList.remove('open');
}
function doLogout() {
  fetch('/logout', { method:'POST', credentials:'include' })
    .finally(() => { window.location.href = 'login.html'; });
}

/* ================================================================
   PAGE SWITCHING
================================================================ */
function switchPage(name) {
  closeDrawer();
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  if (name === 'stock') {
    document.getElementById('pageStock').classList.add('active');
    document.getElementById('navStock').classList.add('active');
  } else {
    document.getElementById('pagePortfolio').classList.add('active');
    document.getElementById('navPortfolio').classList.add('active');
  }
}

/* ================================================================
   STOCK ANALYSIS — results always come from the backend agents
================================================================ */
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function showError(message, details) {
  document.getElementById('resultsContent').innerHTML = `<div class="fade-in" style="color:var(--sell)">
    ⚠ ${esc(message)}
    ${(details||[]).length ? '<ul>' + details.map(d => `<li>${esc(d.field)}: ${esc(d.message)}</li>`).join('') + '</ul>' : ''}
  </div>`;
  document.getElementById('resultsContent').style.display = 'block';
}

async function runAnalysis() {
  const body = {
    ticker:         document.getElementById('ticker').value.trim().toUpperCase(),
    portfolioValue: parseFloat(document.getElementById('portfolio').value) || 50000,
    timeHorizon:    document.getElementById('horizon').value,
    riskAppetite:   document.getElementById('risk').value,
    experience:     document.getElementById('experience').value,
    age:            parseInt(document.getElementById('age').value) || 30,
  };
  if (!body.ticker) { showError('Please enter an NSE ticker, e.g. RELIANCE.'); return; }

  setLoading(true, 'Agents are analysing… this can take up to a minute');
  document.getElementById('emptyState').style.display = 'none';
  document.getElementById('resultsContent').style.display = 'none';
  document.getElementById('runBtn').disabled = true;
  try {
    const r = await fetch('/api/analyze', {
      method: 'POST', credentials: 'include',
      headers: {'Content-Type': 'application/json'},
      signal: AbortSignal.timeout(180000),
      body: JSON.stringify(body),
    });
    if (r.status === 401) { window.location.href = 'login.html'; return; }
    const data = await r.json();
    if (data.error) { showError(data.error, data.details); return; }
    renderResults(data);
  } catch (e) {
    showError('Could not reach the analysis service: ' + e.message);
  } finally {
    setLoading(false);
    document.getElementById('runBtn').disabled = false;
  }
}

/* ================================================================
   GAUGE SVG
================================================================ */
function buildGauge(score, color) {
  const pct = Math.max(score / 100, 0.04);
  const W=200, H=115, cx=100, cy=105, r=82;
  const bgPath = `M ${cx-r} ${cy} A ${r} ${r} 0 1 1 ${cx+r} ${cy}`;
  const ea = Math.PI + pct * Math.PI;
  const fx = cx + r * Math.cos(ea);
  const fy = cy + r * Math.sin(ea);
  const fgPath = `M ${cx-r} ${cy} A ${r} ${r} 0 ${pct>0.5?1:0} 1 ${fx} ${fy}`;
  return `<svg viewBox="0 0 ${W} ${H}" width="180" height="104" xmlns="http://www.w3.org/2000/svg">
    <path d="${bgPath}" fill="none" stroke="#1e2330" stroke-width="13" stroke-linecap="round"/>
    <path d="${fgPath}" fill="none" stroke="${color}" stroke-width="13" stroke-linecap="round"
          style="filter:drop-shadow(0 0 6px ${color}99)"/>
    <text x="${cx}" y="${cy-8}" text-anchor="middle"
          font-family="JetBrains Mono,monospace" font-size="30" font-weight="700" fill="${color}">${score}</text>
    <text x="${cx}" y="${cy+10}" text-anchor="middle"
          font-family="JetBrains Mono,monospace" font-size="12" fill="#6b7280">out of 100</text>
  </svg>`;
}

/* ================================================================
   RENDER STOCK RESULTS
================================================================ */
function renderResults(d) {
  const rs        = typeof d.riskScore === 'number' ? d.riskScore : 13;
  const color     = riskColor(rs);
  const recClass  = d.recommendationClass || d.recClass || 'hold';
  const priceDisp = d.priceDisplay || `₹${fmt(d.currentPrice)}`;
  const hasT      = d.targetPrice1 && !isNaN(d.targetPrice1);
  const dateStr   = new Date().toLocaleDateString('en-IN',{day:'numeric',month:'short',year:'numeric'});

  document.getElementById('resultsContent').innerHTML = `
  <div class="fade-in">
    <div id="pdf-cover">
      <h1>QuantumAdvisor — Investment Analysis</h1>
      <p>${d.ticker} · ${dateStr} · multi-agent analysis</p>
    </div>
    <div class="results-header">
      <div class="rh-left">
        <span class="results-title">Analysis</span>
        <span class="ticker-badge">${d.ticker}</span>
      </div>
      <button class="download-btn" onclick="downloadPDF()">⬇ Download PDF</button>
    </div>
    <div class="price-hero">
      <div>
        <div class="price-label">Current Market Price</div>
        <div class="price-amount">${priceDisp}</div>
        <div class="price-ticker">${d.ticker} · NSE India</div>
        <div class="price-source">Source: ${esc(d.priceSource || '—')} · ${dateStr}</div>
      </div>
      <div class="rec-badge ${recClass}">
        <div class="rec-label">Recommendation</div>
        <div class="rec-text">${d.recommendation || 'HOLD'}</div>
        <div class="rec-conf">Confidence: ${d.confidence || 'Moderate'}</div>
      </div>
    </div>
    <div class="risk-card">
      <div class="card-label" style="margin-bottom:14px">Risk Assessment</div>
      <div class="risk-inner">
        <div class="gauge-wrap">${buildGauge(rs, color)}</div>
        <div class="risk-right">
          <div class="risk-level-txt" style="color:${color}">${d.riskLevel || 'Medium'} Risk</div>
          <div class="bar-row">
            <div class="bar-lbl"><span>Risk Score</span><span>${rs} / 100</span></div>
            <div class="bar-bg"><div class="bar-fill" id="riskBar" style="width:0%;background:${color}"></div></div>
          </div>
          <ul class="rf-list">${(d.riskFactors||[]).map(f=>`<li>${f}</li>`).join('')}</ul>
        </div>
      </div>
    </div>
    <div class="cards-grid">
      <div class="card"><div class="card-icon">👤</div><div class="card-label">Investor Type</div><div class="card-value">${d.userType||'—'}</div></div>
      <div class="card"><div class="card-icon">📈</div><div class="card-label">Market Trend</div><div class="card-value">${d.trend||'—'}</div></div>
      <div class="card"><div class="card-icon">🏥</div><div class="card-label">Financial Health</div><div class="card-value">${d.financialHealth||'—'}</div></div>
      <div class="card"><div class="card-icon">🎯</div><div class="card-label">Buy Score</div><div class="card-value" style="color:var(--accent);font-family:var(--mono)">${d.buyScore ?? '—'} pts</div></div>
    </div>
    ${hasT ? `
    <div class="sec-label">Price Targets & Stop Loss</div>
    <div class="targets-row">
      <div class="target-card t1"><div class="t-label">Target 1</div><div class="t-price">₹${fmt(d.targetPrice1)}</div></div>
      <div class="target-card t2"><div class="t-label">Target 2</div><div class="t-price">₹${fmt(d.targetPrice2)}</div></div>
      <div class="target-card tsl"><div class="t-label">Stop Loss</div><div class="t-price">₹${fmt(d.stopLoss)}</div></div>
    </div>` : ''}
    <div class="range-card">📊 ${d.expectedRange}</div>
    <div class="insights-card">
      <div class="sec-title">Key Insights</div>
      ${(d.reasoning||[]).map(r=>`<div class="insight-item">${r}</div>`).join('')}
    </div>
    ${d.portfolioAdvice?.length ? `
    <div class="insights-card">
      <div class="sec-title">Portfolio Advice</div>
      ${d.portfolioAdvice.map(r=>`<div class="insight-item">${r}</div>`).join('')}
    </div>` : ''}
    <div class="disclaimer">⚠ Educational analysis only. Consult a SEBI-registered financial advisor before investing.</div>
  </div>`;

  document.getElementById('resultsContent').style.display = 'block';
  requestAnimationFrame(() => setTimeout(() => {
    const bar = document.getElementById('riskBar');
    if (bar) { bar.style.transition = 'width 1.2s ease'; bar.style.width = rs + '%'; }
  }, 60));
}

/* ================================================================
   PDF DOWNLOAD
================================================================ */
function downloadPDF() {
  const btn = document.querySelector('.download-btn');
  btn.textContent = 'Preparing…'; btn.disabled = true;
  const s = document.createElement('style');
  s.id = 'qa-pdf';
  s.textContent = `@media print{*{-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important;}
    body{background:#0a0c10!important;color:#e8eaf0!important;}
    .form-panel,.app-header,.download-btn,.run-btn{display:none!important;}
    .layout{display:block!important;}
    .results-panel{padding:20px!important;background:#0a0c10!important;}
    #pdf-cover{display:flex!important;flex-direction:column;gap:4px;}
    .price-hero{background:#111827!important;}}`;
  document.head.appendChild(s);
  setTimeout(() => {
    window.print();
    setTimeout(() => {
      document.getElementById('qa-pdf')?.remove();
      btn.textContent = '⬇ Download PDF';
      btn.disabled = false;
    }, 1200);
  }, 200);
}

/* ================================================================
   PORTFOLIO UPLOAD
================================================================ */
let selectedFile = null;

function onDragOver(e) {
  e.preventDefault();
  document.getElementById('uploadZone').classList.add('drag');
}
function onDragLeave(e) {
  document.getElementById('uploadZone').classList.remove('drag');
}
function onDrop(e) {
  e.preventDefault();
  document.getElementById('uploadZone').classList.remove('drag');
  const f = e.dataTransfer?.files?.[0];
  if (f) setFile(f);
}
function onFileSelect(e) {
  const f = e.target.files?.[0];
  if (f) setFile(f);
}
function setFile(f) {
  const ok = f.name.toLowerCase().endsWith('.csv') || f.name.toLowerCase().endsWith('.xlsx');
  if (!ok) { alert('Please upload a CSV or XLSX file.'); return; }
  selectedFile = f;
  document.getElementById('fileName').textContent = f.name;
  document.getElementById('fileSelected').style.display = 'flex';
  document.getElementById('analyzeBtn').disabled = false;
}
function removeFile() {
  selectedFile = null;
  document.getElementById('fileSelected').style.display = 'none';
  document.getElementById('analyzeBtn').disabled = true;
  document.getElementById('fileInput').value = '';
  document.getElementById('portResults').style.display = 'none';
}

async function analyzePortfolio() {
  if (!selectedFile) return;
  setLoading(true, 'Analyzing your portfolio…');
  document.getElementById('analyzeBtn').disabled = true;

  const fd = new FormData();
  fd.append('file', selectedFile);

  try {
    const res = await fetch('/upload_portfolio', {
      method:'POST', credentials:'include', body: fd
    });
    if (res.status === 401) { window.location.href = 'login.html'; return; }
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || 'Server error');
    }
    const data = await res.json();
    renderPortfolioResults(data);
  } catch(e) {
    alert('Error: ' + e.message);
  } finally {
    setLoading(false);
    document.getElementById('analyzeBtn').disabled = false;
  }
}

/* ================================================================
   RENDER PORTFOLIO RESULTS
================================================================ */
const SECTOR_COLORS = {
  'Banking':'#7c6ef5','IT':'#00e5be','Oil & Gas':'#f5a623','Pharma':'#4ade80',
  'FMCG':'#fb923c','Auto':'#60a5fa','Metals':'#a78bfa','Infra':'#34d399',
  'Finance':'#e879f9','FMCG':'#fbbf24','Utilities':'#2dd4bf','ETF':'#94a3b8',
  'Real Estate':'#f87171','Telecom':'#38bdf8','Retail':'#c084fc',
  'Consumer':'#86efac','Other':'#6b7280'
};

function renderPortfolioResults(d) {
  const el = document.getElementById('portResults');
  const pnlPos = d.totalPnL >= 0;
  const pnlClass = pnlPos ? 'pos' : 'neg';
  const pnlSign  = pnlPos ? '+' : '';

  // Summary cards
  let html = `<div class="fade-in">
  <div class="style-badge">🧠 ${d.investmentStyle}</div>

  <div class="summary-grid">
    <div class="summ-card">
      <div class="summ-label">Total Value</div>
      <div class="summ-value neutral">₹${fmtInt(d.totalValue)}</div>
    </div>
    <div class="summ-card">
      <div class="summ-label">Total Invested</div>
      <div class="summ-value neutral">₹${fmtInt(d.totalCost)}</div>
    </div>
    <div class="summ-card">
      <div class="summ-label">Profit / Loss</div>
      <div class="summ-value ${pnlClass}">${pnlSign}₹${fmtInt(Math.abs(d.totalPnL))} (${pnlSign}${d.totalPnLPct.toFixed(1)}%)</div>
    </div>
    <div class="summ-card">
      <div class="summ-label">Holdings</div>
      <div class="summ-value neutral">${d.stocks.length} stocks</div>
    </div>
  </div>`;

  // Score bars
  const riskColor2 = riskColor(d.riskScore);
  const divColor   = d.diversificationScore >= 60 ? '#00e5be' : d.diversificationScore >= 40 ? '#f5a623' : '#ff4f6a';
  html += `<div class="score-row">
    <div class="score-card">
      <div class="score-title">Portfolio Risk Score</div>
      <div class="score-num" style="color:${riskColor2}">${d.riskScore}</div>
      <div class="score-bar-bg">
        <div class="score-bar-fill" id="riskBarP" style="width:0%;background:${riskColor2}"></div>
      </div>
    </div>
    <div class="score-card">
      <div class="score-title">Diversification Score</div>
      <div class="score-num" style="color:${divColor}">${d.diversificationScore}</div>
      <div class="score-bar-bg">
        <div class="score-bar-fill" id="divBar" style="width:0%;background:${divColor}"></div>
      </div>
    </div>
  </div>`;

  // Sector allocation
  html += `<div class="card-label" style="margin-bottom:12px">Sector Allocation</div>
  <div class="sector-grid">`;
  for (const [sec, pct] of Object.entries(d.sectorAllocation)) {
    const col = SECTOR_COLORS[sec] || '#6b7280';
    html += `<div class="sector-pill">
      <div class="sector-dot" style="background:${col}"></div>
      ${sec} &nbsp;<strong>${pct}%</strong>
    </div>`;
  }
  html += `</div>`;

  // Stock table
  html += `<div class="card-label" style="margin-bottom:12px">Holdings Detail</div>
  <div class="stock-table-wrap">
  <table class="stock-table">
    <thead>
      <tr>
        <th>Ticker</th><th>Qty</th><th>Buy ₹</th><th>LTP ₹</th>
        <th>Cost</th><th>Value</th><th>P&L</th><th>P&L %</th>
        <th>Sector</th><th>Action</th>
      </tr>
    </thead>
    <tbody>`;

  for (const s of d.stocks) {
    const pcls = s.pnl >= 0 ? 'pnl-pos' : 'pnl-neg';
    const sign = s.pnl >= 0 ? '+' : '';
    const rPill = s.recommendation.toLowerCase();
    html += `<tr>
      <td class="tk-cell">${s.ticker}</td>
      <td>${s.quantity}</td>
      <td>₹${fmt(s.buyPrice)}</td>
      <td>₹${fmt(s.currentPrice)}</td>
      <td>₹${fmtInt(s.costBasis)}</td>
      <td>₹${fmtInt(s.currentValue)}</td>
      <td class="${pcls}">${sign}₹${fmtInt(Math.abs(s.pnl))}</td>
      <td class="${pcls}">${sign}${s.pnlPct.toFixed(1)}%</td>
      <td>${s.sector}</td>
      <td><span class="rec-pill ${rPill}">${s.recommendation}</span></td>
    </tr>`;
  }
  html += `</tbody></table></div>`;

  // Advice
  html += `<div class="insights-card">
    <div class="sec-title">Portfolio Advice & Alerts</div>
    <ul class="advice-list">
      ${d.advice.map(a=>`<li>${a}</li>`).join('')}
    </ul>
  </div>`;

  // Per-stock recommendations
  html += `<div class="insights-card">
    <div class="sec-title">Per-Stock Recommendations</div>
    ${d.recommendations.map(r=>`
      <div class="insight-item">
        <strong style="font-family:var(--mono);color:var(--accent2)">${r.ticker}</strong>
        &nbsp;·&nbsp; <span class="rec-pill ${r.action.toLowerCase()}">${r.action}</span>
        &nbsp; ${r.note}
      </div>`).join('')}
  </div>`;

  html += `<div class="disclaimer">⚠ Educational analysis only. Consult a SEBI-registered financial advisor before investing.</div>
  </div>`;

  el.innerHTML = html;
  el.style.display = 'block';

  // Animate bars
  requestAnimationFrame(() => setTimeout(() => {
    const rb = document.getElementById('riskBarP');
    const db = document.getElementById('divBar');
    if (rb) { rb.style.transition = 'width 1.2s ease'; rb.style.width = d.riskScore + '%'; }
    if (db) { db.style.transition = 'width 1.2s ease'; db.style.width = d.diversificationScore + '%'; }
  }, 80));
}

/* ================================================================
   HELPERS
================================================================ */
function setLoading(on, msg) {
  const ol = document.getElementById('loadingOverlay');
  if (msg) document.getElementById('loadingText').textContent = msg;
  ol.classList.toggle('active', on);
}
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function fmt(n) { return Number(n).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2}); }
function fmtInt(n) { return Math.round(n).toLocaleString('en-IN'); }
function riskColor(s) {
  if (s < 20) return '#00e5be';
  if (s < 38) return '#7c6ef5';
  if (s < 60) return '#f5a623';
  return '#ff4f6a';
}
