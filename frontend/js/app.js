/* ================================================================
   AUTH GUARD — redirect to login if not logged in
================================================================ */
let currentUserEmail = null;

(async function checkAuth() {
  try {
    const res = await fetch('/me', { credentials: 'include' });
    const data = await res.json();
    if (!data.loggedIn && data.loginRequired !== false) {
      window.location.href = 'login.html';
      return;
    }
    currentUserEmail = data.email || 'Guest';
    document.getElementById('profileEmail').textContent = currentUserEmail;
    document.getElementById('drawerEmail').textContent  = currentUserEmail;
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
   STOCK ANALYSIS — streamed live from the agents
   POST /api/analyze/stream returns Server-Sent Events:
     start  {runId}            once
     trace  {from,to,type,...} one per agent message
     result {...}              once, the final analysis
================================================================ */
const AGENT_ICONS = {
  User:'🧑', Planner:'🧭', ProfileAgent:'👤', MarketAnalyst:'📈', FundamentalsAnalyst:'🏢',
  NewsAnalyst:'📰', RiskManager:'🛡️', StrategyAgent:'🎯', PortfolioAgent:'💼',
  ReportAgent:'📄', memory:'🧠', team:'👥'
};
const TYPE_LABEL = {
  request:'request', plan:'plan', task:'task', tool_call:'tool call', tool_result:'tool result',
  result:'result', error:'error', replan:'re-plan', assessment:'assessment', draft:'draft',
  critique:'critique', arbitration:'arbitration', decision:'decision', final:'final', memory:'memory'
};

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function describeEvent(e) {
  const p = e.payload || {};
  switch (e.type) {
    case 'request':     return `Analyse ${p.ticker} for a ${p.experience} investor (${p.riskAppetite}, ${p.timeHorizon})`;
    case 'plan':        return `${p.reasoning} → ${(p.tasks||[]).map(t => t.agent).join(', ')}`;
    case 'task':        return p.instruction;
    case 'tool_call':   return `${e.to.replace('tool:','')}(${p.argument ?? ''})${p.thought && p.thought !== 'default order' ? ' — ' + p.thought : ''}`;
    case 'tool_result': return p.ok ? (p.summary || Object.entries(p).filter(([k,v]) => k !== 'ok' && v !== null && typeof v !== 'object').slice(0,6).map(([k,v]) => `${k}: ${v}`).join(' · ')) : `FAILED: ${p.error}`;
    case 'result':      return Object.entries(p).filter(([k,v]) => v !== null && typeof v !== 'object').slice(0,5).map(([k,v]) => `${k}: ${v}`).join(' · ');
    case 'error':       return p.error;
    case 'replan':      return p.instruction;
    case 'assessment':  return `${p.action.toUpperCase()} — ${p.reasoning} (max confidence ${p.confidence_cap})`;
    case 'draft':       return `${p.recommendation} (${p.confidence}) — ${(p.rationale||[]).join('; ')}${(p.responses||[]).length ? ' | answers: ' + p.responses.map(r => r.objection_id + ': ' + r.response).join('; ') : ''}`;
    case 'critique':    return `${p.verdict.toUpperCase()} — ${p.reasoning}${(p.objections||[]).length ? ' | ' + p.objections.map(o => `${o.id} (${o.severity}): ${o.text}`).join('; ') : ''}`;
    case 'arbitration': return `${p.recommendation} (${p.confidence}) — ${p.reasoning}`;
    case 'decision':    return p.note || `${p.recommendation} (${p.confidence}) — ${p.decidedBy || ''}`;
    case 'memory':      return `Last analysis ${p.created_at}: ${p.recommendation}, risk ${p.riskScore}, ${p.trend}`;
    case 'final':       return p.headline || p.reason || p.status || '';
    default:            return JSON.stringify(p).slice(0, 160);
  }
}

function feedRow(e) {
  const from = e.from.startsWith('tool:') ? '🔧 ' + e.from.slice(5) : (AGENT_ICONS[e.from]||'•') + ' ' + e.from;
  const to   = e.to.startsWith('tool:')   ? '🔧 ' + e.to.slice(5)   : (AGENT_ICONS[e.to]||'•') + ' ' + e.to;
  const fail = (e.type === 'tool_result' && e.payload && e.payload.ok === false) || e.type === 'error';
  const llm  = e.llm ? (e.llm.ok ? `<span class="feed-llm">LLM ${e.llm.latency_ms ?? ''}ms</span>`
                                 : `<span class="feed-llm off">rules fallback</span>`) : '';
  return `<div class="feed-row t-${e.type}${fail ? ' fail' : ''}">
    <span class="feed-seq">${e.seq}</span>
    <span class="feed-route">${esc(from)} <span class="feed-arrow">→</span> ${esc(to)}</span>
    <span class="feed-type">${TYPE_LABEL[e.type] || e.type}${e.round ? ' · round ' + e.round : ''}</span>${llm}
    <div class="feed-msg">${esc(describeEvent(e))}</div>
  </div>`;
}

function resetFeed(runId) {
  const box = document.getElementById('agentFeed');
  box.style.display = 'block';
  box.innerHTML = `<div class="feed-head"><span>🤖 Agent conversation</span>
    <span class="feed-run">${runId ? 'run ' + esc(runId) : ''}</span>
    <button class="feed-toggle" onclick="toggleFeed()">hide</button></div>
    <div class="feed-body" id="feedBody"></div>`;
}
function toggleFeed() {
  const b = document.getElementById('feedBody'), t = document.querySelector('.feed-toggle');
  const hidden = b.style.display === 'none';
  b.style.display = hidden ? 'block' : 'none'; t.textContent = hidden ? 'hide' : 'show';
}
function appendFeed(e) {
  const body = document.getElementById('feedBody');
  if (!body) return;
  body.insertAdjacentHTML('beforeend', feedRow(e));
  body.scrollTop = body.scrollHeight;
}

function collectInput() {
  return {
    ticker:         document.getElementById('ticker').value.trim().toUpperCase(),
    portfolioValue: parseFloat(document.getElementById('portfolio').value) || 50000,
    timeHorizon:    document.getElementById('horizon').value,
    riskAppetite:   document.getElementById('risk').value,
    experience:     document.getElementById('experience').value,
    age:            parseInt(document.getElementById('age').value) || 30,
    goal:           (document.getElementById('goal')?.value || '').trim() || null,
  };
}

function showError(message, details) {
  document.getElementById('resultsContent').innerHTML = `<div class="error-card fade-in">
    <div class="error-title">⚠ Analysis could not complete</div>
    <div>${esc(message)}</div>
    ${(details||[]).length ? '<ul>' + details.map(d => `<li><b>${esc(d.field)}</b>: ${esc(d.message)}</li>`).join('') + '</ul>' : ''}
  </div>`;
  document.getElementById('resultsContent').style.display = 'block';
}

async function runAnalysis() {
  const input = collectInput();
  if (!input.ticker) { showError('Please enter an NSE ticker, e.g. RELIANCE.'); return; }

  document.getElementById('emptyState').style.display = 'none';
  document.getElementById('resultsContent').style.display = 'none';
  const btn = document.getElementById('runBtn');
  btn.disabled = true; btn.innerHTML = '<span>⏳</span> Agents working…';
  resetFeed('');

  try {
    const res = await fetch('/api/analyze/stream', {
      method: 'POST', credentials: 'include',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(input),
      signal: AbortSignal.timeout(180000),
    });
    if (res.status === 401) { window.location.href = 'login.html'; return; }
    if (res.status === 400) {
      const b = await res.json();
      document.getElementById('agentFeed').style.display = 'none';
      showError(b.error, b.details); return;
    }
    if (!res.ok || !res.body) throw new Error('Server returned HTTP ' + res.status);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '', result = null;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let cut;
      while ((cut = buffer.indexOf('\n\n')) >= 0) {
        const chunk = buffer.slice(0, cut); buffer = buffer.slice(cut + 2);
        let kind = 'message', data = '';
        for (const line of chunk.split('\n')) {
          if (line.startsWith('event: ')) kind = line.slice(7);
          else if (line.startsWith('data: ')) data += line.slice(6);
        }
        if (!data) continue;
        const payload = JSON.parse(data);
        if (kind === 'start') document.querySelector('.feed-run').textContent = 'run ' + payload.runId;
        else if (kind === 'trace') appendFeed(payload);
        else if (kind === 'result') result = payload;
      }
    }
    if (!result) throw new Error('The connection closed before the agents finished.');
    if (result.error) { showError(result.error); return; }
    renderResults(result);
  } catch (e) {
    showError('Could not reach the analysis service: ' + e.message + '. Please try again.');
  } finally {
    btn.disabled = false; btn.innerHTML = '<span>⚡</span> Run AI Analysis';
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
    ${renderDegraded(d)}
    <div id="pdf-cover">
      <h1>QuantumAdvisor — Investment Analysis</h1>
      <p>${d.ticker} · ${dateStr} · multi-agent analysis</p>
    </div>
    <div class="results-header">
      <div class="rh-left">
        <span class="results-title">Analysis</span>
        <span class="ticker-badge">${d.ticker}</span>
        <span class="verified-badge">${esc(d.decidedBy || '')}</span>
      </div>
      <button class="download-btn" onclick="downloadPDF()">⬇ Download PDF</button>
    </div>
    <div class="price-hero">
      <div>
        <div class="price-label">Current Market Price</div>
        <div class="price-amount">${priceDisp}</div>
        <div class="price-ticker">${d.ticker} · NSE India</div>
        <div class="price-source">Source: ${esc(d.priceSource || '—')} · ${d.observations || '?'} daily closes · ${dateStr}</div>
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
          <ul class="rf-list">${(d.riskFactors||[]).map(f=>`<li>${esc(f)}</li>`).join('')}</ul>
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
    <div class="range-card">📊 ${esc(d.expectedRange || '')}</div>
    <div class="insights-card">
      <div class="sec-title">Key Insights</div>
      ${(d.reasoning||[]).map(r=>`<div class="insight-item">${esc(r)}</div>`).join('')}
    </div>
    ${d.portfolioAdvice?.length ? `
    <div class="insights-card">
      <div class="sec-title">Portfolio Advice</div>
      ${d.portfolioAdvice.map(r=>`<div class="insight-item">${esc(r)}</div>`).join('')}
    </div>` : ''}
    ${renderAnalystNotes(d)}
    ${renderDebate(d)}
    ${d.aiReport ? `<div class="insights-card"><div class="sec-title">Report Agent</div><div class="report-text">${esc(d.aiReport)}</div></div>` : ''}
    ${renderMeta(d)}
    <div class="disclaimer">⚠ Educational analysis only. Consult a SEBI-registered financial advisor before investing.</div>
  </div>`;

  document.getElementById('resultsContent').style.display = 'block';
  requestAnimationFrame(() => setTimeout(() => {
    const bar = document.getElementById('riskBar');
    if (bar) { bar.style.transition = 'width 1.2s ease'; bar.style.width = rs + '%'; }
  }, 60));
}

/* ================================================================
   AGENT EVIDENCE PANELS
================================================================ */
function renderDegraded(d) {
  const m = d.meta || {};
  const names = [...new Set([...(m.degradedAgents||[]), ...(m.failedAgents||[])])];
  if (!names.length) return '';
  return `<div class="degraded-banner">⚠ Partial result: ${esc(names.join(', '))} ran on rule-based fallbacks or had no data.
    ${m.llmAvailable === false ? 'The LLM is not configured on this server.' : ''}</div>`;
}
function renderAnalystNotes(d) {
  const rows = [
    ['📈 Market', d.marketSummary],
    ['🏢 Fundamentals', d.fundamentalsSummary],
    ['📰 News', d.newsSummary],
    ['🛡️ Risk', d.riskSummary],
    ['👤 Profile', d.profileSummary],
  ].filter(r => r[1]);
  if (!rows.length) return '';
  return `<div class="insights-card"><div class="sec-title">What each analyst found</div>
    ${rows.map(([k,v]) => `<div class="insight-item"><b>${k}:</b> ${esc(v)}</div>`).join('')}</div>`;
}
function renderDebate(d) {
  if (!(d.debate||[]).length) return '';
  const verdictClass = {approve:'v-ok', revise:'v-warn', veto:'v-bad'};
  return `<div class="insights-card"><div class="sec-title">Strategy ↔ Risk debate</div>
    ${d.debate.map(r => `<div class="debate-round">
      <div class="debate-line">🎯 <b>Round ${r.round} — Strategy:</b> ${esc(r.draft.recommendation)} (${esc(r.draft.confidence)})
        ${(r.draft.responses||[]).map(x => `<div class="debate-sub">↳ ${esc(x.objection_id)}: ${esc(x.response)}</div>`).join('')}</div>
      <div class="debate-line">🛡️ <b>Risk:</b> <span class="${verdictClass[r.critique.verdict]||''}">${esc(r.critique.verdict.toUpperCase())}</span> — ${esc(r.critique.reasoning)}
        ${(r.critique.objections||[]).map(o => `<div class="debate-sub">${esc(o.id)} (${esc(o.severity)}): ${esc(o.text)}</div>`).join('')}</div>
    </div>`).join('')}
    <div class="debate-final">Final: <b>${esc(d.recommendation)}</b> · ${esc(d.decidedBy||'')}</div></div>`;
}
function renderMeta(d) {
  const m = d.meta || {};
  if (!m.runId) return '';
  return `<div class="meta-line">Run ${esc(m.runId)} · LLM ${m.llmCalls - m.llmFailures}/${m.llmCalls} calls answered · ${m.replans} re-plan(s) ·
    ${m.debateRounds} debate round(s) · ${(m.durationMs/1000).toFixed(1)} s ·
    <a href="/api/runs/${encodeURIComponent(m.runId)}/trace" target="_blank" rel="noopener">raw trace JSON</a></div>`;
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
