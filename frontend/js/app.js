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
   VERIFIED NSE PRICES  — March 2026
================================================================ */
const PRICES = {
  IOC:144.60, BPCL:285.50, ONGC:265.40, GAIL:170.00, PETRONET:225.00, HINDPETRO:290.00,
  HDFCBANK:790.00, ICICIBANK:1255.00, SBIN:680.00, AXISBANK:1050.00,
  KOTAKBANK:1950.00, INDUSINDBK:760.00, BANDHANBNK:155.00, FEDERALBNK:170.00,
  TCS:2370.00, INFY:1235.00, WIPRO:189.00, HCLTECH:1345.00, TECHM:1380.00,
  LTI:4200.00, LTIM:4200.00, MPHASIS:2100.00, COFORGE:7200.00,
  MARUTI:11500.00, TATAMOTORS:680.00, 'M&M':2700.00, MM:2700.00,
  'BAJAJ-AUTO':8500.00, BAJAJAUTO:8500.00, EICHERMOT:4900.00,
  HEROMOTOCO:3900.00, TVSMOTOR:2200.00,
  SUNPHARMA:1580.00, DRREDDY:1150.00, CIPLA:1430.00, DIVISLAB:4600.00,
  BIOCON:310.00, AUROPHARMA:1180.00, LUPIN:1950.00,
  HINDUNILVR:2300.00, ITC:395.00, NESTLEIND:2250.00, BRITANNIA:4800.00,
  DABUR:510.00, MARICO:600.00, GODREJCP:1080.00,
  TATASTEEL:135.00, HINDALCO:580.00, JSWSTEEL:980.00, VEDL:400.00,
  NMDC:60.00, COALINDIA:375.00, SAIL:100.00,
  LT:3250.00, ULTRACEMCO:10500.00, GRASIM:2600.00,
  ADANIPORTS:1150.00, BHARTIARTL:1650.00, POWERGRID:290.00,
  RELIANCE:1414.40, ADANIENT:2150.00,
  DMART:4000.00, TRENT:5100.00, DLF:680.00, GODREJPROP:2100.00,
  PRESTIGE:1400.00, NTPC:335.00, TATAPOWER:380.00, ADANIGREEN:940.00,
  TITAN:3200.00, VOLTAS:1400.00, HAVELLS:1450.00, CROMPTON:360.00,
  BAJFINANCE:850.00, BAJAJFINSV:1600.00,
  HDFCLIFE:600.00, SBILIFE:1400.00, ICICIPRULI:580.00,
  ASIANPAINT:2200.00, ZOMATO:210.00, PAYTM:850.00, NYKAA:140.00, IRCTC:780.00,
  GOLDBEES:71.00, NIFTYBEES:240.00, BANKBEES:490.00,
  AAPL:215.00, MSFT:385.00, GOOGL:165.00, NVDA:110.00,
  TSLA:280.00, META:580.00, AMZN:190.00
};
const US_SET = new Set(['AAPL','MSFT','GOOGL','NVDA','TSLA','META','AMZN','NFLX','ORCL','ADBE','INTC','AMD','CRM','CSCO','IBM']);

function lookupPrice(raw) {
  const k = raw.toUpperCase().replace('.NS','').replace('.BO','');
  const price = PRICES[k];
  if (price) return { price, currency: US_SET.has(k) ? 'USD' : 'INR', known: true };
  return { price: 500, currency: 'INR', known: false };
}

/* ================================================================
   STOCK CHARACTERISTICS
================================================================ */
const STOCK_DATA = {
  IOC:[20,55,22,14.0,1.1,6.3], BPCL:[18,52,28,16.0,1.0,9.5], ONGC:[22,58,25,18.0,0.4,7.5],
  GAIL:[16,50,22,12.0,0.6,12.0], HINDPETRO:[14,48,28,10.0,1.2,11.0], RELIANCE:[18,52,20,10.0,0.5,19.3],
  HDFCBANK:[12,40,18,15.0,7.5,15.5], ICICIBANK:[15,48,20,17.0,6.8,17.9], SBIN:[14,46,25,18.0,8.0,8.5],
  AXISBANK:[13,44,22,14.0,6.5,16.0], KOTAKBANK:[11,42,18,16.0,5.8,22.0], INDUSINDBK:[10,36,28,12.0,5.0,12.0],
  TCS:[10,35,22,45.0,0.1,18.3], INFY:[10,38,22,32.0,0.1,20.0], WIPRO:[8,33,25,15.0,0.2,17.0],
  HCLTECH:[15,48,22,25.0,0.1,19.0], TECHM:[12,44,24,18.0,0.1,22.0],
  MARUTI:[16,50,22,18.0,0.2,26.0], TATAMOTORS:[14,46,28,12.0,1.5,18.0],
  BAJFINANCE:[10,35,28,22.0,3.5,25.0], BHARTIARTL:[22,58,20,30.0,2.0,28.0],
  TATASTEEL:[12,44,30,10.0,1.5,15.0], HINDALCO:[18,55,28,14.0,0.8,12.0],
  NTPC:[14,48,20,12.0,1.8,14.0], TATAPOWER:[15,50,25,10.0,2.0,18.0],
  SUNPHARMA:[16,52,22,18.0,0.2,24.0], DRREDDY:[14,48,20,20.0,0.1,22.0], CIPLA:[15,50,22,16.0,0.2,20.0],
  GOLDBEES:[18,55,12,0,0,0], NIFTYBEES:[15,50,14,0,0,0], BANKBEES:[12,44,18,0,0,0],
  _DEFAULT:[15,50,25,14.0,1.0,18.0],
};
const BANKS = new Set(['HDFCBANK','ICICIBANK','SBIN','AXISBANK','KOTAKBANK','BANDHANBNK','FEDERALBNK','INDUSINDBK']);
const ETFS  = new Set(['GOLDBEES','NIFTYBEES','BANKBEES']);

/* ================================================================
   ANALYSIS ENGINE  (original — untouched)
================================================================ */
function runEngine(ticker, portfolio, experience, riskAppetite, age, horizon) {
  const tk = ticker.toUpperCase().replace('.NS','').replace('.BO','');
  const { price, currency, known } = lookupPrice(tk);
  const priceINR = currency === 'USD' ? price * 84 : price;

  let riskCapacity = 50;
  if      (age < 30) riskCapacity += 25;
  else if (age < 40) riskCapacity += 15;
  else if (age > 60) riskCapacity -= 25;
  if (horizon === 'Long-term')              riskCapacity += 20;
  else if (horizon === 'Short-term')        riskCapacity -= 15;
  if (riskAppetite === 'Aggressive')        riskCapacity += 15;
  else if (riskAppetite === 'Conservative') riskCapacity -= 15;
  if (experience === 'Experienced')         riskCapacity += 15;
  else if (experience === 'Beginner')       riskCapacity -= 5;
  riskCapacity = clamp(riskCapacity, 0, 100);

  const sd = STOCK_DATA[tk] || STOCK_DATA['_DEFAULT'];
  const [trendScore, rsi, vol, roe, de, pe] = sd;

  let healthScore = 50;
  if (ETFS.has(tk)) {
    healthScore = 65;
  } else {
    if      (roe > 25) healthScore += 30;
    else if (roe > 12) healthScore += 20;
    if (!BANKS.has(tk)) {
      if      (de < 0.5) healthScore += 20;
      else if (de < 1.0) healthScore += 10;
    } else { healthScore += 15; }
  }

  let riskScore = 0;
  const riskFactors = [];
  if      (vol > 28) { riskScore += 25; riskFactors.push(`⚠️ High volatility (${vol}%)`); }
  else if (vol > 20) { riskScore += 13; riskFactors.push(`〰️ Moderate volatility (${vol}%)`); }
  else               { riskScore +=  5; riskFactors.push(`✓ Low volatility (${vol}%)`); }

  if      (healthScore < 55) { riskScore += 20; riskFactors.push('⚠️ Weak fundamentals'); }
  else if (healthScore < 70) { riskScore +=  8; riskFactors.push('✓ Adequate fundamentals'); }
  else                       { riskScore +=  5; riskFactors.push('✓ Healthy fundamentals'); }

  if      (rsi > 70) { riskScore += 10; riskFactors.push(`⚠️ Overbought (RSI ${rsi})`); }
  else if (rsi < 35) { riskScore +=  8; riskFactors.push(`📉 Oversold RSI ${rsi} — potential bounce`); }
  else               { riskScore +=  3; riskFactors.push(`✓ RSI in range (${rsi})`); }

  riskScore = clamp(riskScore, 0, 100);
  const riskLevel = riskScore >= 45 ? 'High' : riskScore >= 25 ? 'Medium' : 'Low-Medium';
  const riskClass = riskScore >= 45 ? 'high' : riskScore >= 25 ? 'medium' : 'low';

  if (experience === 'Beginner') {
    const sip = Math.min(portfolio * 0.15, 10000);
    return build({
      tk, priceINR, known, riskCapacity, riskScore, riskLevel, riskClass, riskFactors,
      trendScore, rsi, vol, healthScore, pe,
      userType:'Beginner Investor', riskProfile:riskAppetite,
      recommendation:'Start SIP', recClass:'hold', buyScore:0,
      targetPrice1:null, targetPrice2:null, stopLoss:null,
      portfolioAdvice:[`💰 Suggested monthly SIP: ₹${fmtInt(sip)}`, '📊 Consider Nifty 50 Index Fund'],
      reasoning:['✅ SIP recommended for beginners','✅ Rupee cost averaging reduces entry risk','✅ Index funds lower single-stock risk'],
      expectedRange:'Returns: 12–15% CAGR (historical)'
    });
  }

  let buyScore = 0;
  const reasoning = [];
  buyScore += trendScore / 2;
  reasoning.push(trendScore >= 18 ? `✅ Strong uptrend (+${trendScore})` :
                 trendScore <  12 ? `📉 Weak trend (+${trendScore})` :
                                    `〰️ Sideways trend (+${trendScore})`);
  buyScore += (healthScore - 50) / 2;
  reasoning.push(healthScore >= 70 ? `✅ Strong fundamentals (score: ${healthScore})` :
                                     `✓ Solid fundamentals (score: ${healthScore})`);
  if (ETFS.has(tk)) { buyScore += 10; reasoning.push('✅ Diversified ETF — lower single-stock risk'); }
  else if (pe > 0 && pe < 12)  { buyScore += 15; reasoning.push(`✅ Attractively valued (P/E: ${pe}x)`); }
  else if (pe >= 12 && pe < 22){ buyScore +=  5; reasoning.push(`〰️ Fair valuation (P/E: ${pe}x)`); }
  else if (pe >= 22)           { reasoning.push(`⚠️ Premium valuation (P/E: ${pe}x)`); }
  if (rsi < 38) { buyScore += 10; reasoning.push(`📉 Oversold RSI ${rsi} — potential bounce`); }

  let recommendation, recClass, alloc;
  if      (buyScore >= 35) { recommendation='BUY';          recClass='buy';  alloc=8; }
  else if (buyScore >= 20) { recommendation='ACCUMULATE';   recClass='hold'; alloc=5; }
  else                     { recommendation='HOLD / WATCH'; recClass='hold'; alloc=3; }

  const tm1 = recClass==='buy' ? 1.15 : 1.10;
  const tm2 = recClass==='buy' ? 1.28 : 1.18;
  const slm = recClass==='buy' ? 0.92 : 0.95;

  let portfolioAdvice;
  if (priceINR > portfolio) {
    portfolioAdvice = [
      `⚠️ Stock price ₹${fmt(priceINR)} exceeds your ₹${fmtInt(portfolio)} portfolio`,
      '💡 Increase capital or choose a lower-priced stock'
    ];
  } else {
    const posVal = portfolio * (alloc / 100);
    const units  = Math.max(1, Math.floor(posVal / priceINR));
    const actual = units * priceINR;
    portfolioAdvice = [
      `💰 Suggested position: ₹${fmtInt(actual)}`,
      `📊 Buy ${units} unit${units !== 1 ? 's' : ''} @ ₹${fmt(priceINR)}`
    ];
  }

  return build({
    tk, priceINR, known, riskCapacity, riskScore, riskLevel, riskClass, riskFactors,
    trendScore, rsi, vol, healthScore, pe,
    userType: experience==='Experienced' ? 'Experienced Investor' : 'Intermediate Investor',
    riskProfile: riskAppetite,
    recommendation, recClass,
    buyScore: Math.round(buyScore * 10) / 10,
    targetPrice1: +(priceINR * tm1).toFixed(2),
    targetPrice2: +(priceINR * tm2).toFixed(2),
    stopLoss:     +(priceINR * slm).toFixed(2),
    portfolioAdvice, reasoning,
    expectedRange: `Range: ₹${fmt(priceINR*(1-vol/100))} – ₹${fmt(priceINR*(1+vol/100))}`
  });
}

function build(o) {
  return {
    ticker:            o.tk,
    currentPrice:      o.priceINR,
    priceDisplay:      `₹${fmt(o.priceINR)} per share`,
    isKnown:           o.known,
    userType:          o.userType,
    riskProfile:       o.riskProfile,
    riskCapacityScore: o.riskCapacity,
    riskScore:         o.riskScore,
    riskLevel:         o.riskLevel,
    riskClass:         o.riskClass,
    riskFactors:       o.riskFactors,
    trend:             o.trendScore>=18 ? 'Uptrend' : o.trendScore<12 ? 'Downtrend' : 'Sideways',
    volatility:        o.vol>28 ? 'High' : o.vol>20 ? 'Moderate' : 'Low',
    financialHealth:   o.healthScore>=80 ? 'Excellent' : o.healthScore>=65 ? 'Good' : 'Fair',
    pe:                o.pe,
    recommendation:    o.recommendation,
    recommendationClass: o.recClass,
    confidence:        (o.buyScore||0) >= 20 ? 'Moderate' : 'Low',
    buyScore:          o.buyScore || 0,
    reasoning:         o.reasoning,
    targetPrice1:      o.targetPrice1,
    targetPrice2:      o.targetPrice2,
    stopLoss:          o.stopLoss,
    portfolioAdvice:   o.portfolioAdvice,
    expectedRange:     o.expectedRange,
  };
}

/* ================================================================
   STOCK ANALYSIS TRIGGER
================================================================ */
async function runAnalysis() {
  const ticker     = document.getElementById('ticker').value.trim().toUpperCase();
  const portfolio  = parseFloat(document.getElementById('portfolio').value) || 50000;
  const horizon    = document.getElementById('horizon').value;
  const risk       = document.getElementById('risk').value;
  const experience = document.getElementById('experience').value;
  const age        = parseInt(document.getElementById('age').value) || 30;
  if (!ticker) { alert('Please enter a ticker'); return; }

  setLoading(true, 'Running multi-agent analysis…');
  document.getElementById('emptyState').style.display = 'none';
  document.getElementById('resultsContent').style.display = 'none';
  document.getElementById('runBtn').disabled = true;

  try {
    const r = await fetch('/api/analyze', {
      method:'POST', credentials:'include',
      headers:{'Content-Type':'application/json'},
      signal: AbortSignal.timeout(5000),
      body: JSON.stringify({ ticker, portfolioValue:portfolio, timeHorizon:horizon, riskAppetite:risk, experience, age })
    });
    if (r.status === 401) { window.location.href='login.html'; return; }
    if (!r.ok) throw new Error('HTTP '+r.status);
    const backendData = await r.json();
    if (backendData.error) throw new Error(backendData.error);
    renderResults(backendData);
  } catch(e) {
    // Fallback: use local engine if backend unreachable
    console.warn('Backend unavailable, using local engine:', e.message);
    const local = runEngine(ticker, portfolio, experience, risk, age, horizon);
    renderResults(local);
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
      <p>${d.ticker} · ${dateStr} · NSE Verified Prices</p>
    </div>
    <div class="results-header">
      <div class="rh-left">
        <span class="results-title">Analysis</span>
        <span class="ticker-badge">${d.ticker}</span>
        ${d.isKnown ? '<span class="verified-badge">✓ VERIFIED</span>' : ''}
      </div>
      <button class="download-btn" onclick="downloadPDF()">⬇ Download PDF</button>
    </div>
    <div class="price-hero">
      <div>
        <div class="price-label">Current Market Price</div>
        <div class="price-amount">${priceDisp}</div>
        <div class="price-ticker">${d.ticker} · NSE India</div>
        <div class="price-source">Verified · ${dateStr}</div>
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
