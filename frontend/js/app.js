/* Quantum Advisor front end: live committee board, decision sheet, portfolio review, history. */

/* ---------------- sign-in, navigation, server health ---------------- */
let ME = {};
(async function boot() {
  try {
    ME = await (await fetch('/me', {credentials: 'include'})).json();
    if (!ME.loggedIn && ME.loginRequired !== false) { location.href = 'login.html'; return; }
    setUser(ME.email || 'Guest', null);
    document.getElementById('signOut').hidden = !ME.loggedIn;
    document.getElementById('accountEmail').textContent = ME.email ? `Signed in as ${ME.email}.` : '';
    if (ME.loggedIn) loadProfile();
  } catch (e) { location.href = 'login.html'; return; }
  openPage(pageFromHash(), {replace: true});
  try {
    const h = await (await fetch('/api/health')).json();
    if (!h.llmConfigured) showNotice('healthNotice',
      'This server has no Gemini API key, so every agent is using its rule-based fallback. Results still work, without LLM reasoning.');
  } catch (e) { /* health is informational only */ }
})();

function setUser(email, name) {
  const label = name || (email || 'Guest').split('@')[0];
  document.getElementById('who').textContent = label;
  document.getElementById('avatar').textContent = label.trim()[0] ? label.trim()[0].toUpperCase() : '?';
  document.getElementById('menuEmail').textContent = email || '';
}

document.getElementById('signOut').addEventListener('click', async () => {
  await fetch('/logout', {method: 'POST', credentials: 'include'}).catch(() => {});
  location.href = '/';
});

function showNotice(id, text, isError) {
  const n = document.getElementById(id);
  n.textContent = text; n.classList.toggle('error', !!isError); n.hidden = false;
}

/* pages: today, analyse, portfolio, watchlist (main nav) and history, profile (user menu) */
const PAGES = ['today', 'analyse', 'portfolio', 'watchlist', 'history', 'profile'];
const OLD_HASH = {watch: 'watchlist', account: 'profile'};
function pageFromHash() {
  const h = location.hash.slice(1);
  return PAGES.includes(h) ? h : (OLD_HASH[h] || 'today');
}
document.addEventListener('click', ev => {
  const a = ev.target.closest('[data-page]');
  if (!a) return;
  ev.preventDefault();
  closeUserMenu();
  openPage(a.dataset.page);
});
window.addEventListener('hashchange', () => openPage(pageFromHash(), {replace: true}));
function openPage(name, opts = {}) {
  document.querySelectorAll('.nav-link, .bnav-link').forEach(t => {
    if (t.dataset.page === name) t.setAttribute('aria-current', 'page'); else t.removeAttribute('aria-current');
  });
  document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === 'page-' + name));
  if (location.hash !== '#' + name) history[opts.replace ? 'replaceState' : 'pushState'](null, '', '#' + name);
  if (name === 'today' && window.loadToday) loadToday();
  if (name === 'history') loadHistory();
  if (name === 'profile') { mountAccountProfile(); if (window.loadNotifications) loadNotifications(); }
  if (name === 'watchlist' && window.loadWatch) loadWatch();
  if (name === 'portfolio' && window.loadPortfolioPage) loadPortfolioPage();
  if (name === 'analyse') requestAnimationFrame(redrawTrails);
  if (!opts.keepScroll) window.scrollTo(0, 0);
}

/* user menu */
const userBtn = document.getElementById('userBtn'), userMenu = document.getElementById('userMenu');
function closeUserMenu() { userMenu.hidden = true; userBtn.setAttribute('aria-expanded', 'false'); }
userBtn.addEventListener('click', () => {
  const open = userMenu.hidden;
  userMenu.hidden = !open; userBtn.setAttribute('aria-expanded', String(open));
  if (open) userMenu.querySelector('a, button').focus();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !userMenu.hidden) { closeUserMenu(); userBtn.focus(); } });
document.addEventListener('click', e => { if (!userMenu.hidden && !e.target.closest('.user-menu')) closeUserMenu(); });

/* jump to the analysis of a stock from anywhere (Today search, watchlist, history) */
function analyseStock(symbol, run = true) {
  openPage('analyse');
  const t = document.getElementById('ticker');
  t.value = symbol;
  if (run) runAnalysis(); else t.focus();
}

/* ---------------- committee board ---------------- */
const board = document.getElementById('board');
const linksSvg = document.getElementById('links');
const seats = {};
board.querySelectorAll('.seat').forEach(s => { seats[s.dataset.agent] = s; });
const trails = new Set();

function seatState(agent, state, text) {
  const s = seats[agent];
  if (!s) return;
  s.classList.remove('working', 'done', 'failed', 'skipped');
  if (state) s.classList.add(state);
  if (text !== undefined) s.querySelector('.state').textContent = text;
}
function resetBoard() {
  Object.keys(seats).forEach(a => { seatState(a, null, 'Idle'); seats[a].classList.remove('fallback'); });
  linksSvg.innerHTML = ''; trails.clear();
  live.reset();
}

/* ---------------- live flow: the map, the latest message, the call so far ---------------- */
const live = (() => {
  const host = document.getElementById('liveGraph');
  const flow = window.AgentFlow ? new AgentFlow(host, {label: 'Live map of the committee'}) : null;
  const $ = id => document.getElementById(id);
  const stats = {msg: 0, tools: 0, llm: 0, ask: 0};
  function stat(k, v) { stats[k] = v; $('ls' + {msg: 'Msg', tools: 'Tools', llm: 'Llm', ask: 'Ask'}[k]).textContent = v; }
  function needle(rec, note) {
    const m = $('liveNeedle');
    m.hidden = !rec; m.className = rec ? rec.toLowerCase() : '';
    $('liveNeedleNote').textContent = note;
  }
  function say(e) {
    const route = e.to && e.to !== e.from ? `${partyName(e.from)} to ${partyName(e.to)}` : partyName(e.from);
    $('liveRoute').textContent = `${route} · ${KIND_NAMES[e.type] || e.type}${e.round ? ', round ' + e.round : ''}`;
    const t = describeEvent(e);
    const el = $('liveText');
    el.textContent = t.length > 240 ? t.slice(0, 238).trimEnd() + '…' : t;
    el.classList.remove('live-in'); void el.offsetWidth; el.classList.add('live-in');
  }
  return {
    reset() {
      if (flow) flow.reset();
      Object.keys(stats).forEach(k => stat(k, 0));
      needle(null, 'No call yet.');
      $('liveRoute').textContent = 'Sending your request to the Planner…';
      $('liveText').textContent = '';
    },
    message(e) {
      const p = e.payload || {};
      stat('msg', stats.msg + 1);
      if (e.type === 'tool_call') stat('tools', stats.tools + 1);
      if (e.llm && e.llm.ok) stat('llm', stats.llm + 1);
      if (e.type === 'followup') stat('ask', stats.ask + 1);
      if (e.type !== 'tool_result') say(e);
      if (flow) flow.apply(e);
      if (e.type === 'draft') needle(p.recommendation, `Round ${e.round} draft: ${p.recommendation}`);
      if (e.type === 'critique') needle(document.getElementById('liveNeedle').className.toUpperCase() || null,
        `${$('liveNeedleNote').textContent.split(' · ')[0]} · ${p.verdict === 'approve' ? 'approved' : 'sent back'}`);
      if (e.type === 'arbitration') needle(p.recommendation, `Planner ruled: ${p.recommendation}`);
      if (e.type === 'decision' && p.recommendation) needle(p.recommendation, `Final: ${p.recommendation}, ${String(p.confidence || '').toLowerCase()} confidence`);
    },
  };
})();

/* the seats are the old view; the map is the default */
const viewToggle = document.getElementById('viewToggle');
viewToggle.addEventListener('click', () => {
  const seatsOn = board.hidden;
  board.hidden = !seatsOn; document.getElementById('live').hidden = seatsOn;
  viewToggle.setAttribute('aria-pressed', String(seatsOn));
  viewToggle.textContent = seatsOn ? 'Show the live map instead' : 'Show the seats instead';
  if (seatsOn) redrawTrails();
});
function centre(el) {
  const b = board.getBoundingClientRect(), r = el.getBoundingClientRect();
  return [r.left - b.left + r.width / 2, r.top - b.top + r.height / 2];
}
function drawLine(from, to, cls) {
  const [x1, y1] = centre(seats[from]), [x2, y2] = centre(seats[to]);
  const l = document.createElementNS('http://www.w3.org/2000/svg', 'line');
  l.setAttribute('x1', x1); l.setAttribute('y1', y1); l.setAttribute('x2', x2); l.setAttribute('y2', y2);
  l.setAttribute('class', cls);
  linksSvg.appendChild(l);
  return l;
}
function link(from, to, kind) {
  if (!seats[from] || !seats[to] || from === to) return;
  const key = [from, to].sort().join('|');
  if (!trails.has(key)) { trails.add(key); drawLine(from, to, 'trail'); }
  const live = drawLine(from, to, 'live ' + (kind || ''));
  setTimeout(() => live.remove(), 1400);
}
function redrawTrails() {
  linksSvg.innerHTML = '';
  trails.forEach(k => { const [a, b] = k.split('|'); if (seats[a] && seats[b]) drawLine(a, b, 'trail'); });
}
window.addEventListener('resize', redrawTrails);

const ANALYSTS = ['MarketAnalyst', 'FundamentalsAnalyst', 'NewsAnalyst', 'DocumentAnalyst'];
function short(s, n = 46) { s = String(s || ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; }

/* ---------------- progress stages and timer ---------------- */
const STAGES = ['brief', 'plan', 'research', 'check', 'debate', 'decide'];
const stageEls = Object.fromEntries([...document.querySelectorAll('#stages li')].map(li => [li.dataset.stage, li]));
let timerId = null, timerStart = 0;
function setStage(name, failed) {
  const k = STAGES.indexOf(name);
  STAGES.forEach((s, i) => {
    const li = stageEls[s]; if (!li) return;
    li.classList.toggle('done', i < k || (i === k && name === 'decide' && !failed));
    li.classList.toggle('now', i === k && !(name === 'decide' && !failed));
    li.classList.toggle('failed', i === k && !!failed);
    if (i === k) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
  });
}
function resetStages() { STAGES.forEach(s => stageEls[s] && stageEls[s].classList.remove('done', 'now', 'failed')); }
function startTimer() {
  const t = document.getElementById('timer'); t.hidden = false; timerStart = Date.now();
  const tick = () => { const s = Math.floor((Date.now() - timerStart) / 1000); t.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
  tick(); clearInterval(timerId); timerId = setInterval(tick, 1000);
}
function stopTimer() { clearInterval(timerId); }
function stageFor(e) {
  if (e.type === 'request') return 'brief';
  if (e.type === 'plan' || (e.type === 'task' && e.to === 'ProfileAgent')) return 'plan';
  if (e.type === 'task' && ANALYSTS.includes(e.to)) return 'research';
  if (e.type === 'assessment' || e.type === 'challenge' || e.type === 'reconciliation' || e.to === 'RiskManager' && e.type === 'task') return 'check';
  if (e.type === 'draft' || e.type === 'critique' || e.type === 'arbitration') return 'debate';
  if (e.type === 'decision' && e.from === 'Planner' && e.payload && e.payload.recommendation) return 'decide';
  if (e.type === 'task' && (e.to === 'PortfolioAgent' || e.to === 'ReportAgent')) return 'decide';
  return null;
}
let currentStage = -1;

function onAgentMessage(e) {
  const p = e.payload || {};
  live.message(e);
  const st = stageFor(e);
  if (st && STAGES.indexOf(st) > currentStage) { currentStage = STAGES.indexOf(st); setStage(st); }
  if (e.llm && e.llm.ok === false && seats[e.from]) seats[e.from].classList.add('fallback');
  switch (e.type) {
    case 'task': seatState(e.to, 'working', short(p.instruction)); link(e.from, e.to, 'task'); break;
    case 'tool_call': seatState(e.from, 'working', `Using ${partyName(e.to)} (${short(p.argument, 18)})`); break;
    case 'tool_result': if (!p.ok) seatState(e.to, 'working', 'A source failed, deciding what next'); break;
    case 'result': seatState(e.from, 'done', short(p.trend ? `${p.trend}, RSI ${p.rsi}` : p.newsSentiment ? `${p.newsSentiment} news` :
                               p.documentPagesUsed ? `Read pages ${p.documentPagesUsed.join(', ')}` :
                               p.financialHealth ? `${p.financialHealth} fundamentals` : p.riskLevel ? `${p.riskLevel} risk` : 'Done'));
                   link(e.from, e.to, 'result'); break;
    case 'error': seatState(e.from, 'failed', short('Failed: ' + p.error)); link(e.from, e.to, 'critique'); break;
    case 'plan': {
      const chosen = (p.tasks || []).map(t => t.agent);
      ANALYSTS.filter(a => !chosen.includes(a)).forEach(a => seatState(a, 'skipped',
        a === 'DocumentAnalyst' ? 'No document attached' : 'Not needed for this request'));
      seatState('Planner', 'working', `Planned ${chosen.length} analysts`); break;
    }
    case 'memory': seatState('Planner', 'working', 'Read your last analysis'); break;
    case 'assessment': seatState('Planner', 'working', p.action === 'retry' ? 'Re-planning failed work' : 'Results checked'); break;
    case 'replan': seatState(e.to, 'working', short('Retry: ' + p.instruction)); link(e.from, e.to, 'replan'); break;
    case 'draft': seatState('StrategyAgent', 'done', `Round ${e.round}: ${p.recommendation}`);
                  seatState('RiskManager', 'working', 'Reviewing the draft'); link(e.from, e.to, 'draft'); break;
    case 'critique': seatState('RiskManager', p.verdict === 'approve' ? 'done' : 'working', `Round ${e.round}: ${p.verdict}`);
                     if (p.verdict !== 'approve') seatState('StrategyAgent', 'working', 'Answering the objections');
                     link(e.from, e.to, 'critique'); break;
    case 'arbitration': seatState('Planner', 'done', `Ruled ${p.recommendation}`); break;
    case 'challenge': seatState(e.from, 'working', 'Challenging the live figures'); link(e.from, e.to, 'critique'); break;
    case 'reply': seatState(e.from, 'done', 'Explained its figures'); link(e.from, e.to, 'draft'); break;
    case 'reconciliation': seatState('Planner', 'working', `Settled: trust ${p.trust}`);
                           seatState('DocumentAnalyst', 'done', 'Conflict settled'); break;
    case 'decision': if (e.from === 'Planner') seatState('Planner', 'done', `Decided ${p.recommendation}`); break;
    case 'final': if (seats[e.from]) seatState(e.from, 'done', 'Report written'); break;
  }
}

/* ---------------- minutes ---------------- */
const minutesEl = document.getElementById('minutes');
let minuteCount = 0;
function resetMinutes() {
  minutesEl.innerHTML = ''; minuteCount = 0;
  document.getElementById('minutesEmpty').hidden = true;
  document.getElementById('minutesCount').textContent = '';
}
function addMinute(e) {
  minutesEl.insertAdjacentHTML('beforeend', minuteItem(e));
  minuteCount += 1;
  document.getElementById('minutesCount').textContent = `${minuteCount} messages`;
  minutesEl.scrollTop = minutesEl.scrollHeight;
}

/* ---------------- company document (optional) ---------------- */
const docInput = document.getElementById('docFile');
const docName = document.getElementById('docName'), docClear = document.getElementById('docClear');
document.getElementById('docChoose').addEventListener('click', () => docInput.click());
function showDoc() {
  const f = docInput.files[0];
  docName.textContent = f ? `${f.name} (${f.size < 1048576 ? Math.max(1, Math.round(f.size / 1024)) + ' KB' : (f.size / 1048576).toFixed(1) + ' MB'})` : 'None attached';
  docName.classList.toggle('set', !!f); docClear.hidden = !f;
}
docInput.addEventListener('change', () => {
  const f = docInput.files[0];
  if (f && f.size > 15 * 1048576) { docInput.value = ''; showDecisionError('That PDF is larger than 15 MB. Attach a smaller file, such as the quarterly results.'); }
  showDoc();
});
docClear.addEventListener('click', () => { docInput.value = ''; showDoc(); });

/* ---------------- run an analysis (streamed) ---------------- */
document.querySelectorAll('.chip[data-t]').forEach(c => c.addEventListener('click', () => {
  document.getElementById('ticker').value = c.dataset.t; document.getElementById('ticker').focus();
}));
document.getElementById('brief').addEventListener('submit', ev => { ev.preventDefault(); runAnalysis(); });

function collectInput() {
  const v = id => document.getElementById(id).value;
  return {
    ticker: v('ticker').trim().toUpperCase(),
    portfolioValue: parseFloat(v('portfolioValue')) || 0,
    age: parseInt(v('age'), 10) || 0,
    experience: v('experience'), timeHorizon: v('timeHorizon'), riskAppetite: v('riskAppetite'),
    goal: v('goal').trim() || null,
    // saved extras that are edited on the Account page, not on this form
    goals: (savedProfile && savedProfile.goals) || [],
    monthlyInvest: savedProfile ? savedProfile.monthlyInvest ?? null : null,
    avoidSectors: (savedProfile && savedProfile.avoidSectors) || [],
    name: savedProfile ? savedProfile.name ?? null : null,
  };
}

async function runAnalysis() {
  const input = collectInput();
  if (document.getElementById('remember').checked) {
    saveProfile(input).then(() => { editingProfile = false; loadProfile(); }).catch(() => {});
  }
  const btn = document.getElementById('runBtn'), status = document.getElementById('roomStatus');
  const decision = document.getElementById('decision');
  if (!input.ticker) { showDecisionError('Enter an NSE symbol, for example RELIANCE.'); return; }

  btn.disabled = true; btn.textContent = `Analysing ${input.ticker}…`;
  decision.hidden = true; resetBoard(); resetMinutes(); resetStages(); currentStage = -1; startTimer();
  foldRoom(false); document.getElementById('roomToggle').hidden = true;
  document.getElementById('room').scrollIntoView({block: 'nearest'});
  status.textContent = 'Sending your request to the Planner…';
  const slow = setTimeout(() => { status.textContent = 'Waking the server. Free hosting sleeps when idle, so the first run can take up to a minute.'; }, 5000);

  try {
    const file = docInput.files[0];
    let body, headers = {};
    if (file) {
      body = new FormData();
      Object.entries(input).forEach(([k, v]) => { if (v !== null && v !== '') body.append(k, v); });
      body.append('document', file);
    } else {
      body = JSON.stringify(input); headers = {'Content-Type': 'application/json'};
    }
    const res = await fetch('/api/analyze/stream', {
      method: 'POST', credentials: 'include', headers, body, signal: AbortSignal.timeout(300000),
    });
    if (res.status === 401) { location.href = 'login.html'; return; }
    if (res.status === 400 || res.status === 413) {
      const b = await res.json();
      status.textContent = 'Check the highlighted details.';
      if ((b.details || []).some(x => x.field !== 'ticker')) showProfileForm('editing');
      showDecisionError(b.error, b.details); return;
    }
    if (!res.ok || !res.body) throw new Error('the server answered ' + res.status);

    const reader = res.body.getReader(), decoder = new TextDecoder();
    let buffer = '', result = null;
    for (;;) {
      const {value, done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
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
        if (kind === 'start') { clearTimeout(slow); status.textContent = 'The committee is working…'; }
        else if (kind === 'trace') { addMinute(payload); onAgentMessage(payload); }
        else if (kind === 'result') result = payload;
      }
    }
    if (!result) throw new Error('the connection closed before the committee finished');
    if (result.error) { status.textContent = 'The analysis stopped.'; setStage(STAGES[Math.max(0, currentStage)], true); showDecisionError(result.error); return; }
    status.textContent = `Decided: ${result.recommendation}. ${result.decidedBy}.`;
    currentStage = 5; setStage('decide');
    result._input = input; result._at = new Date();
    renderDecision(result);
  } catch (err) {
    status.textContent = 'Could not reach the analysis service.';
    showDecisionError(`Could not reach the analysis service (${err.message}). Check your connection and run it again.`);
  } finally {
    clearTimeout(slow); stopTimer();
    btn.disabled = false; btn.textContent = 'Run the analysis';
  }
}

function showDecisionError(message, details) {
  const d = document.getElementById('decision');
  d.innerHTML = `<div class="sheet"><div class="error-sheet"><h3>The analysis could not finish</h3>
    <p>${esc(message)}</p>${(details || []).length ? '<ul class="factor-list">' + details.map(x =>
      `<li><b>${esc(x.field)}</b>: ${esc(x.message)}</li>`).join('') + '</ul>' : ''}</div></div>`;
  d.hidden = false;
  (details || []).forEach(x => { const f = document.getElementById(x.field); if (f) f.setAttribute('aria-invalid', 'true'); });
}

/* ---------------- decision sheet ---------------- */
function riskScale(d) {
  const max = 50, tol = Math.max(0, d.riskScore - (d.suitabilityGap ?? 0));
  const pct = v => Math.max(0, Math.min(100, v / max * 100));
  return `<div class="scale" aria-hidden="true"><div class="track"></div><div class="ok" style="width:${pct(tol)}%"></div>
    <div class="mark" style="left:${pct(d.riskScore)}%"></div></div>
    <div class="scale-legend"><span>Calmer</span><span>Green area: risk you can carry (up to ${Math.round(tol)})</span><span>Riskier</span></div>`;
}

function docSection(d) {
  if (!d.documentAvailable) return '';
  if (d.documentAboutCompany === false) {
    return `<section><h3>From your document</h3>
      <p class="conflict flag"><b>Not used:</b> ${esc((d.documentConflicts || [])[0] || 'the document seems to be about another company')}. Attach ${esc(d.ticker)}'s own annual report or results.</p></section>`;
  }
  const u = d.documentUnit ? String(d.documentUnit) : '';
  const unit = u ? ` (${/₹|rs|inr/i.test(u) ? esc(u) : '₹ ' + esc(u)})` : '';
  const figs = Object.entries(d.documentFigures || {}).map(([k, v]) =>
    `<div><span>${esc(k)}${k.startsWith('EPS') ? ' (₹)' : unit}</span><b>${Number(v).toLocaleString('en-IN')}</b></div>`).join('');
  const r = d.documentRatios || {};
  const ratios = [r.profitMargin != null ? `profit margin ${r.profitMargin}%` : '', r.de != null ? `debt/equity ${r.de}` : '']
    .filter(Boolean).join(', ');
  const flags = (d.documentRedFlags || []).map(f => `<p class="conflict flag"><b>Red flag:</b> ${esc(f)}</p>`).join('');
  const check = d.documentCheck || {};
  const conflicts = (d.documentConflicts || []).map(c => `<p class="conflict"><b>Disagrees with live data:</b> ${esc(c)}</p>`).join('')
    + (check.reasoning ? `<p class="doc-note"><b>Planner's ruling</b> (rely on ${esc(check.trust)}): ${esc(check.reasoning)}</p>` : '');
  return `<section><h3>From your document</h3>
    <p class="doc-note">${esc(d.documentName)}${d.documentPeriod ? ', ' + esc(d.documentPeriod) : ''}. Read pages ${esc((d.documentPagesUsed || []).join(', '))} of ${esc(d.documentPages)}.</p>
    ${figs ? `<div class="doc-figs">${figs}</div>` : '<p class="doc-note">No figures could be read from the statements.</p>'}
    ${ratios ? `<p class="doc-note">Worked out from these: ${esc(ratios)}.</p>` : ''}
    ${flags}${conflicts}
    ${(d.documentPoints || []).length ? `<ul>${d.documentPoints.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
  </section>`;
}

function grade(v, good, bad, higherIsBetter = true) {
  if (v == null || isNaN(v)) return {word: 'No data', cls: 'na', icon: '–'};
  const isGood = higherIsBetter ? v >= good : v <= good, isBad = higherIsBetter ? v < bad : v > bad;
  return isGood ? {word: 'Strong', cls: 'good', icon: '▲'} : isBad ? {word: 'Weak', cls: 'bad', icon: '▼'} : {word: 'Fair', cls: 'mid', icon: '●'};
}
function tile(label, value, sub, extra = '') {
  return `<div class="tile"><dt>${esc(label)}</dt><dd>${value}</dd>${sub ? `<p class="tile-sub">${sub}</p>` : ''}${extra}</div>`;
}
function scorecardView(d) {
  const c = d.scorecard;
  if (!c || !c.scores) return '';
  const cls = n => n >= 7 ? 'good' : n >= 4 ? 'mid' : 'bad';
  const rows = c.scores.map(x => `<li><span class="sc-name">${esc(x.name)}</span>
    <span class="sc-bar ${cls(x.score)}" role="img" aria-label="${x.score} out of 10">${Array.from({length: 10}, (_, i) => `<i${i < x.score ? ' class="f"' : ''}></i>`).join('')}</span>
    <b class="sc-num">${x.score}<small>/10</small></b><span class="sc-why">${esc(x.why)}</span></li>`).join('');
  const entryCls = {Good: 'good', Fair: 'mid', Stretched: 'bad'}[c.entry.verdict] || 'mid';
  return `<section><h3>Scorecard</h3>
    <p class="section-note">The analysts' numbers on one scale. Missing data is left out, not guessed.</p>
    <div class="scorecard"><ul class="sc-rows">${rows}</ul>
      <div class="sc-side"><p class="sc-entry"><span>Entry point</span><b class="grade ${entryCls}">${esc(c.entry.verdict)}</b></p>
        <p class="sc-entry-why">${esc(c.entry.why)}</p>
        <p class="sc-flags-h">${c.redFlags.length ? `Red flags (${c.redFlags.length})` : 'No red flags'}</p>
        ${c.redFlags.length ? `<ul class="sc-flags">${c.redFlags.map(f => `<li>${esc(f)}</li>`).join('')}</ul>` : ''}</div></div></section>`;
}
function signalTiles(d) {
  const t = [];
  const m1 = d.change1mPct;
  t.push(tile('Trend', esc(d.trend), m1 != null ? `${m1 >= 0 ? '+' : '−'}${Math.abs(m1).toFixed(1)}% in a month` : ''));
  t.push(tile('RSI (momentum)', esc(Number(d.rsi).toFixed(0)), d.rsi > 70 ? 'Overbought: a pullback is common' : d.rsi < 30 ? 'Oversold: selling may be overdone' : 'Neutral range', rsiMeter(d.rsi)));
  t.push(tile('Daily volatility', `${esc(d.volatility)}%`, d.volatility > 1.8 ? 'Moves more than most large caps' : 'Typical for a large cap'));
  if (d.belowHighPct != null) t.push(tile('Off 6-month high', `${Math.abs(d.belowHighPct).toFixed(1)}%`, d.maxDrawdownPct != null ? `Worst fall in 6 months: ${Math.abs(d.maxDrawdownPct).toFixed(0)}%` : ''));
  if (d.volumeRatio != null) t.push(tile('Trading volume', `${d.volumeRatio}×`, `${esc(d.volumeLevel)} vs its 50-day average`));
  if (d.newsSentiment && d.newsSentiment !== 'Not analysed') t.push(tile('News', esc(d.newsSentiment), `${d.headlineCount || 0} headlines read`));
  if (d.macdState) t.push(tile('MACD (12, 26, 9)', esc(d.macdState), `Histogram ${d.macdHist > 0 ? '+' : ''}${esc(d.macdHist)}: ${d.macdHist > 0 ? 'momentum building' : 'momentum fading'}`));
  if (d.bbState) t.push(tile('Bollinger bands', esc(d.bbState), `%B ${esc(d.bbPercentB)}; band width ${esc(d.bbWidthPct)}% of price`));
  if (d.support != null) t.push(tile('Support / resistance', `${inr(d.support, 0)} – ${inr(d.resistance, 0)}`, `60-day low ${Math.abs(d.toSupportPct).toFixed(1)}% below, high ${Math.abs(d.toResistancePct).toFixed(1)}% above`));
  if (d.change3mPct != null) t.push(tile('3-month change', `${d.change3mPct >= 0 ? '+' : '−'}${Math.abs(d.change3mPct).toFixed(1)}%`, 'Momentum over a quarter'));
  return `<dl class="tiles">${t.join('')}</dl>`;
}
function fundamentalsSection(d) {
  if (!d.fundamentalsAvailable) return '';
  const rows = [
    ['P/E', d.pe != null ? Number(d.pe).toFixed(1) : '–', grade(d.pe, 20, 35, false), 'Price per ₹1 of yearly profit'],
    ['EPS', d.eps != null ? inr(d.eps) : '–', d.eps != null ? (d.eps > 0 ? {word: 'Profitable', cls: 'good', icon: '▲'} : {word: 'Loss', cls: 'bad', icon: '▼'}) : grade(null), 'Profit per share, last 12 months'],
    ['ROE', d.roe != null ? d.roe + '%' : '–', grade(d.roe, 15, 8), 'Profit on shareholders’ money'],
    ['Debt / equity', d.de != null ? d.de : '–', grade(d.de, 0.5, 1.5, false), 'Borrowing compared with equity'],
    ['Profit margin', d.profitMargin != null ? d.profitMargin + '%' : '–', grade(d.profitMargin, 15, 5), 'Profit kept from each ₹100 of sales'],
  ];
  return `<section><h3>Company health</h3>
    <dl class="tiles">${rows.map(([l, v, g, help]) => tile(l, esc(String(v)), `<span class="grade ${g.cls}"><span aria-hidden="true">${g.icon}</span> ${g.word}</span> · ${esc(help)}`)).join('')}</dl>
    <p class="section-note">${esc(d.fundamentalsSummary || '')}</p></section>`;
}
function newsSection(d) {
  const items = d.headlineLabels || [];
  if (!items.length) return '';
  const count = k => items.filter(h => h.sentiment === k).length;
  const [pos, neu, neg] = [count('Positive'), count('Neutral'), count('Negative')];
  const seg = (n, cls, label) => n ? `<span class="split-seg ${cls}" style="flex:${n}" title="${label}: ${n}"></span>` : '';
  return `<section><h3>What the news says</h3>
    <div class="split" role="img" aria-label="${pos} positive, ${neu} neutral, ${neg} negative headlines">${seg(pos, 'pos', 'Positive')}${seg(neu, 'neu', 'Neutral')}${seg(neg, 'neg', 'Negative')}</div>
    <div class="split-legend"><span><i class="pos"></i>${pos} positive</span><span><i class="neu"></i>${neu} neutral</span><span><i class="neg"></i>${neg} negative</span></div>
    <ul class="headlines">${items.slice(0, 8).map(h => `<li><span class="htag ${esc(h.sentiment).toLowerCase()}">${esc(h.sentiment)}</span>${h.material ? '<span class="htag material">Could move the price</span>' : ''} ${esc(h.title)}</li>`).join('')}</ul>
    <p class="section-note">${esc(d.newsSummary || '')}</p></section>`;
}
function lastRunNote(d) {
  const l = d.lastRun;
  if (!l || !l.recommendation) return '';
  const when = new Date(l.created_at).toLocaleDateString('en-IN', {day: 'numeric', month: 'short'});
  const move = l.price && d.currentPrice ? (d.currentPrice / l.price - 1) * 100 : null;
  const changed = l.recommendation !== d.recommendation;
  return `<p class="last-run"><b>Last time (${esc(when)}):</b> ${esc(l.recommendation)} at ${l.price ? inr(l.price) : '–'}, risk ${esc(l.riskScore)}.
    ${move != null ? `Price since then: ${move >= 0 ? '+' : '−'}${Math.abs(move).toFixed(1)}%.` : ''} ${changed ? `<b>The call changed to ${esc(d.recommendation)}.</b>` : 'Same call as before.'}</p>`;
}
function sizingTiles(d) {
  const p = d.positionSizing || {};
  if (p.amount == null) return '';
  return `<dl class="tiles compact">${tile('Suggested amount', p.amount ? inr(p.amount, 0) : '₹0', p.amount ? `${p.positionPct}% of your money` : 'No new money for now')}
    ${tile('Shares', esc(String(p.units ?? 0)), `at ${inr(d.currentPrice)}`)}
    ${tile('Target 1', inr(d.targetPrice1, 0), `${((d.targetPrice1 / d.currentPrice - 1) * 100).toFixed(1)}% away`)}
    ${tile('Stop-loss', inr(d.stopLoss, 0), `${((d.stopLoss / d.currentPrice - 1) * 100).toFixed(1)}% away`)}</dl>`;
}

/* ---------- the PDF (browser print): a report header and the terms, shown only on paper ---------- */
const HORIZON = {'Short-term': 'needs the money within a year', 'Medium-term': 'needs it in 1 to 3 years', 'Long-term': 'needs it in 5 years or more'};
function stamp(t) {
  return t.toLocaleString('en-IN', {day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'Asia/Kolkata'}) + ' IST';
}
function printHeader(d) {
  const m = d.meta || {}, i = d._input || {}, at = d._at || new Date();
  const who = document.getElementById('menuEmail').textContent;
  const prof = i.age ? [`age ${i.age}`, String(i.experience || '').toLowerCase(), `${String(i.riskAppetite || '').toLowerCase()} risk`,
    HORIZON[i.timeHorizon] || '', i.portfolioValue ? `${inr(i.portfolioValue, 0)} to invest` : ''].filter(Boolean).join(', ') : (d.profileSummary || '');
  const models = Object.keys(m.models || {}).join(', ');
  const row = (k, v) => v ? `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>` : '';
  return `<header class="print-only print-head">
    <div class="ph-top"><span class="ph-brand"><img src="img/mark.svg" alt="" width="26" height="26">Quantum Advisor</span>
      <span class="ph-kind">Stock analysis report</span></div>
    <h2 class="ph-title">${esc(d.ticker)}${d.companyName ? ' · ' + esc(d.companyName) : ''}</h2>
    <dl class="ph-meta">
      ${row('Generated', stamp(at))}
      ${row('Prepared for', who)}
      ${row('Investor', prof)}
      ${row('Price used', d.currentPrice ? `${inr(d.currentPrice)} from ${d.priceSource || 'market data'}` : '')}
      ${row('Run', `${m.runId || ''}, ${m.llmCalls ? (m.llmCalls - m.llmFailures) + ' of ' + m.llmCalls + ' decisions by the model' : 'rule-based'}${m.durationMs ? ', ' + Math.round(m.durationMs / 1000) + ' s' : ''}`)}
      ${row('Model', models)}
    </dl>
  </header>`;
}
function printTerms(d) {
  const url = location.origin + '/terms.html';
  return `<section class="print-only print-terms">
    <h3>Terms and important information</h3>
    <ol>
      <li><b>Not investment advice.</b> This report is an educational analysis produced by Quantum Advisor, a student project. It is not a recommendation to buy, sell or hold any security. Quantum Advisor is not registered with SEBI as an investment adviser or research analyst.</li>
      <li><b>Data can be wrong or late.</b> Prices, company figures and news come from free public sources, can be delayed by up to 15 minutes and may be incomplete. Check them before acting.</li>
      <li><b>AI judgement can be wrong.</b> The agents' reasoning is produced by a large language model, limited by rule checks and a risk review. The full trace of this run (run ${esc((d.meta || {}).runId || '')}) shows which agent said what and from which data.</li>
      <li><b>Your decision, your risk.</b> Investing can lose money and past prices do not predict future ones. Speak to a SEBI-registered adviser before investing.</li>
      <li><b>Your data.</b> Your profile, holdings and analyses are stored only to run the service for you and are not sold or shared for advertising.</li>
    </ol>
    <p>Full terms of use: ${esc(url)}</p>
    <p class="pt-foot">Quantum Advisor · generated ${esc(stamp(d._at || new Date()))} · ${esc(location.host)}</p>
  </section>`;
}
/* a sensible file name when the browser saves the PDF */
let titleBeforePrint = document.title;
addEventListener('beforeprint', () => {
  const h = document.querySelector('#decision:not([hidden]) .ph-title');
  if (!h) return;
  titleBeforePrint = document.title;
  const day = new Date().toISOString().slice(0, 10);
  document.title = `Quantum Advisor - ${h.textContent.split(' · ')[0]} analysis - ${day}`;
});
addEventListener('afterprint', () => { document.title = titleBeforePrint; });

function renderDecision(d) {
  const rec = (d.recommendation || 'HOLD').toLowerCase();
  const gap = d.suitabilityGap ?? 0;
  const fit = gap > 0 ? `riskier than suits you by ${gap} points` : `within what suits you (${-gap} points to spare)`;
  const m = d.meta || {};
  const degraded = [...new Set([...(m.degradedAgents || []), ...(m.failedAgents || [])])];
  const findings = [['Market', d.marketSummary], ['Fundamentals', d.fundamentalsSummary], ['News', d.newsSummary],
                    ['Your document', d.documentAvailable ? d.documentSummary : null],
                    ['Risk', d.riskSummary], ['Your profile', d.profileSummary]].filter(f => f[1]);
  const rounds = (d.debate || []).map(r => `<li><span class="round-no">${r.round}</span><div>
      <p class="turn"><b>Strategist:</b> ${esc(r.draft.recommendation)}, ${esc(String(r.draft.confidence).toLowerCase())} confidence. ${esc((r.draft.rationale || []).join('; '))}</p>
      ${(r.draft.responses || []).map(x => `<p class="objection"><b>${esc(x.objection_id)}</b> answered: ${esc(x.response)}</p>`).join('')}
      <p class="turn"><b>Risk manager:</b> <span class="verdict-tag ${esc(r.critique.verdict)}">${esc(r.critique.verdict)}</span> ${esc(r.critique.reasoning)}</p>
      ${(r.critique.objections || []).map(o => `<p class="objection"><b>${esc(o.id)}</b> (${esc(o.severity)}): ${esc(o.text)}</p>`).join('')}
    </div></li>`).join('');
  const breakdown = (d.riskBreakdown || []).slice().sort((a, b) => b.points - a.points)
    .map(p => ({label: p.label, value: p.points}));
  const llmShare = m.llmCalls ? Math.round((m.llmCalls - m.llmFailures) / m.llmCalls * 100) : 0;

  const el = document.getElementById('decision');
  el.innerHTML = `<article class="sheet" aria-labelledby="verdictWord">
    ${printHeader(d)}
    <div class="sheet-top">
      <div>
        <p class="verdict-line">${esc(d.ticker)}${d.companyName ? ' · ' + esc(d.companyName) : ''}${d.requestedTicker && d.requestedTicker !== d.ticker ? ` <span class="doc-note">(you entered ${esc(d.requestedTicker)}, which now trades as ${esc(d.ticker)})</span>` : ''}</p>
        <p class="verdict ${rec}" id="verdictWord">${esc(d.action ? d.action.label : d.recommendation)}</p>
        ${d.action ? `<p class="verdict-action">${esc(d.action.text)}</p>
        <p class="verdict-call">Committee call <b>${esc(d.recommendation)}</b> · ${d.action.holding ? 'in your saved holdings' : 'not in your saved holdings'}</p>` : ''}
        <p class="verdict-meta"><strong>${esc(d.confidence)} confidence.</strong> ${esc(d.decidedBy)}.</p>
        <p class="price-big">${esc(d.priceDisplay || inr(d.currentPrice))}</p>
        <p class="caption">${esc(d.sector || '')}${d.sector ? ' · ' : ''}price from ${esc(d.priceSource || 'market data')}</p>
      </div>
      <div class="headline-box">
        <p class="headline">${esc(d.reportHeadline || '')}</p>
        ${(d.portfolioAdvice || [])[0] ? `<p class="first-advice">${esc(d.portfolioAdvice[0])}</p>` : ''}
        ${lastRunNote(d)}
        ${(d.preferenceNotes || []).map(n => `<p class="conflict flag"><b>Your preference:</b> ${esc(n)} The recommendation is unchanged; the choice is yours.</p>`).join('')}
      </div>
    </div>
    <div class="chart price-panel" id="priceChartHost"></div>
    <p class="caption chart-caption">${esc(d.expectedRange || '')} Hover or use the arrow keys on the chart to read any day.</p>
    ${degraded.length ? `<p class="notice" style="margin:14px 0 0">Partly rule-based: ${esc(degraded.map(partyName).join(', '))} used fallbacks or had no data.</p>` : ''}

    ${scorecardView(d)}
    <section><h3>Signals at a glance</h3>${signalTiles(d)}</section>

    <section><h3>Is it right for you?</h3>
      <p class="risk-text">Stock risk <b>${esc(d.riskScore)}</b> (${esc(d.riskLevel)}), ${esc(fit)}.</p>
      ${riskScale(d)}
      ${breakdown.length ? `<div class="two-col"><div><h4>Where the risk points come from</h4>${hBars(breakdown, {unit: ''})}</div>
        <div><h4>What the risk manager flagged</h4>${(d.keyRisks || d.riskFactors || []).length ? `<ul class="factor-list">${(d.keyRisks || d.riskFactors).map(f => `<li>${esc(f)}</li>`).join('')}</ul>` : '<p class="section-note">No major risk factor.</p>'}</div></div>` : ''}
    </section>

    <section><h3>What to do</h3>
      <ul class="advice-list">${(d.portfolioAdvice || []).map(a => `<li>${esc(a)}</li>`).join('')}</ul>
      ${sizingTiles(d)}
    </section>

    <section><h3>How the committee argued</h3><ol class="rounds">${rounds}</ol>
      ${(d.followups || []).length ? `<div class="followups"><h4>Evidence asked for during the debate</h4><ul>${d.followups.map(f => `<li>
        <p><b>${esc(partyName(f.from))}</b> asked the Planner for <b>${esc(partyName(f.agent))}</b> (round ${f.round}): ${esc(f.question)}</p>
        <p class="fu-answer">${f.granted ? `<b>${esc(partyName(f.agent))}:</b> ${esc(f.answer)}${f.changesView ? ' <span class="verdict-tag revise">changes the view</span>' : ''}` : `<b>Planner declined:</b> ${esc(f.reasoning)}`}</p></li>`).join('')}</ul></div>` : ''}
      <p class="outcome">Outcome: ${esc(d.recommendation)}. ${esc(d.decidedBy)}.</p></section>

    ${fundamentalsSection(d)}
    ${newsSection(d)}
    ${docSection(d)}
    <section><h3>What each analyst found</h3>
      <dl class="findings">${findings.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl></section>

    <section><h3>Report</h3><p class="report">${esc(d.aiReport)}</p></section>

    <footer class="run-foot">
      <span>Run ${esc(m.runId)}</span>
      <span>${m.llmCalls - m.llmFailures} of ${m.llmCalls} decisions by the LLM (${llmShare}%)</span>
      <span>${m.replans} re-plan${m.replans === 1 ? '' : 's'}, ${m.debateRounds} debate round${m.debateRounds === 1 ? '' : 's'}</span>
      <span>${(m.durationMs / 1000).toFixed(0)} s</span>
      <span class="spacer"></span>
      <a href="trace.html?run=${encodeURIComponent(m.runId)}" target="_blank" rel="noopener" class="no-print">Open the full trace</a>
      <button class="secondary no-print" type="button" onclick="window.print()">Save as PDF</button>
    </footer>
    <p class="disclaimer">Educational analysis, not investment advice. Speak to a SEBI-registered adviser before investing.</p>
    ${printTerms(d)}
  </article>`;
  el.hidden = false;
  mountPriceChart(document.getElementById('priceChartHost'), d);
  wireHBars(el, () => 'risk points');
  addSectionNav(el, d);
  foldRoom(true, d);
  el.scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start'});
}

/* Section links along the top of the decision, highlighting the one in view. */
const SECTION_LABELS = {'Signals at a glance': 'Signals', 'Is it right for you?': 'Fit for you', 'What to do': 'What to do',
  'How the committee argued': 'Debate', 'Company health': 'Company', 'What the news says': 'News',
  'Your document': 'Document', 'What each analyst found': 'Findings', 'Report': 'Report'};
let sectionObserver = null;
function addSectionNav(el, d) {
  const sections = [...el.querySelectorAll('.sheet > section')].filter(sec => sec.querySelector('h3'));
  const links = [['sec-overview', 'Overview']];
  el.querySelector('.sheet-top').id = 'sec-overview';
  sections.forEach((sec, i) => {
    const title = sec.querySelector('h3').textContent.trim();
    const label = SECTION_LABELS[title] || (title.startsWith('What the document') || title.startsWith('Your') ? 'Document' : title.split(' ').slice(0, 2).join(' '));
    sec.id = 'sec-' + i;
    links.push([sec.id, label]);
  });
  const nav = document.createElement('nav');
  nav.className = 'sec-nav no-print';
  nav.setAttribute('aria-label', 'Sections of this decision');
  nav.innerHTML = `<span class="sec-nav-verdict ${esc((d.recommendation || '').toLowerCase())}">${esc(d.ticker)} ${esc(d.recommendation)}</span>` +
    links.map(([id, label]) => `<a href="#${id}" data-sec="${id}">${esc(label)}</a>`).join('');
  el.querySelector('.sheet').prepend(nav);
  nav.addEventListener('click', ev => {
    const a = ev.target.closest('a[data-sec]');
    if (!a) return;
    ev.preventDefault();
    document.getElementById(a.dataset.sec).scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start'});
  });
  if (sectionObserver) sectionObserver.disconnect();
  sectionObserver = new IntersectionObserver(entries => {
    entries.forEach(en => {
      if (!en.isIntersecting) return;
      nav.querySelectorAll('a').forEach(a => a.classList.toggle('on', a.dataset.sec === en.target.id));
    });
  }, {rootMargin: '-35% 0px -60% 0px'});
  links.forEach(([id]) => sectionObserver.observe(document.getElementById(id)));
}

/* After a decision the committee board folds into one line; it opens again on demand. */
function foldRoom(folded, d) {
  const room = document.getElementById('room'), toggle = document.getElementById('roomToggle');
  room.classList.toggle('folded', folded);
  toggle.hidden = false;
  toggle.textContent = folded ? 'Show how the committee decided' : 'Hide';
  toggle.setAttribute('aria-expanded', String(!folded));
  if (!folded) requestAnimationFrame(redrawTrails);
}
document.getElementById('roomToggle').addEventListener('click', () => {
  foldRoom(!document.getElementById('room').classList.contains('folded'));
});

/* ---------------- portfolio review ---------------- */
const fileInput = document.getElementById('fileInput'), drop = document.getElementById('drop');
let chosenFile = null;
document.getElementById('chooseFile').addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => pickFile(fileInput.files[0]));
drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('drag'); });
drop.addEventListener('dragleave', () => drop.classList.remove('drag'));
drop.addEventListener('drop', e => { e.preventDefault(); drop.classList.remove('drag'); pickFile(e.dataTransfer.files[0]); });
function pickFile(f) {
  if (!f) return;
  if (!/\.(csv|xlsx)$/i.test(f.name)) { renderPortfolioError('Choose a .csv or .xlsx file.'); return; }
  chosenFile = f;
  document.getElementById('fileName').textContent = f.name;
  document.getElementById('reviewBtn').disabled = false;
}
document.getElementById('reviewBtn').addEventListener('click', reviewPortfolio);
document.getElementById('sampleBtn').addEventListener('click', async () => {
  try {
    const text = await (await fetch('samples/sample_portfolio.csv')).text();
    pickFile(new File([text], 'sample_portfolio.csv', {type: 'text/csv'}));
    reviewPortfolio();
  } catch (e) { renderPortfolioError('Could not load the sample portfolio.'); }
});

// Validated categorical order (charts.js SERIES); a 7th+ sector folds into "Other".
const SECTOR_TONES = SERIES;

async function reviewPortfolio() {
  if (!chosenFile) return;
  const btn = document.getElementById('reviewBtn');
  btn.disabled = true; btn.textContent = 'Pricing holdings live…';
  document.getElementById('portfolioResult').innerHTML = '<div class="sheet loading-sheet"><p>Pricing each holding live and asking the review agent… this takes about 20–40 seconds.</p><div class="bar-loader"><span></span></div></div>';
  const fd = new FormData(); fd.append('file', chosenFile);
  const keep = document.getElementById('keepHoldings').checked;
  if (keep) fd.append('save', '1');
  try {
    const res = await fetch('/upload_portfolio', {method: 'POST', credentials: 'include', body: fd, signal: AbortSignal.timeout(180000)});
    if (res.status === 401) { location.href = 'login.html'; return; }
    const d = await res.json();
    if (!res.ok || d.error) { renderPortfolioError(d.error || 'The review failed.'); return; }
    renderPortfolio(d);
    if (d.saved && window.afterHoldingsSaved) window.afterHoldingsSaved();
  } catch (err) {
    renderPortfolioError(`Could not reach the server (${err.message}). Try again.`);
  } finally {
    btn.disabled = false; btn.textContent = 'Upload and review';
  }
}
function renderPortfolioError(msg) {
  document.getElementById('portfolioResult').innerHTML =
    `<div class="sheet"><div class="error-sheet"><h3>The review could not finish</h3><p>${esc(msg)}</p></div></div>`;
}
function renderPortfolio(d) {
  const calls = Object.fromEntries(((d.review || {}).holdings || []).map(h => [h.ticker, h]));
  let sectors = Object.entries(d.sectorAllocation || {}).sort((a, b) => b[1] - a[1]);
  if (sectors.length > SECTOR_TONES.length) {
    const keep = sectors.slice(0, SECTOR_TONES.length - 1);
    sectors = keep.concat([['Other', +sectors.slice(SECTOR_TONES.length - 1).reduce((a, [, p]) => a + p, 0).toFixed(1)]]);
  }
  const pnlCls = d.totalPnL >= 0 ? 'pos' : 'neg', sign = d.totalPnL >= 0 ? '+' : '−';
  const priced = d.stocks.filter(s => String(s.priceSource).startsWith('live'));
  const best = priced.slice().sort((a, b) => b.pnlPct - a.pnlPct)[0], worst = priced.slice().sort((a, b) => a.pnlPct - b.pnlPct)[0];
  const rows = d.stocks.slice().sort((a, b) => b.currentValue - a.currentValue).map(s => {
    const c = calls[s.ticker] || {};
    const live = String(s.priceSource).startsWith('live');
    return `<tr><td class="tk">${esc(s.ticker)}<div class="src">${esc(s.sector)}</div></td>
      <td>${sparkline(s.history)}</td>
      <td>${s.quantity}</td><td>${inr(s.buyPrice)}</td>
      <td>${inr(s.currentPrice)}<div class="src ${live ? '' : 'bad'}">${esc(s.priceSource)}</div></td>
      <td class="${s.pnl >= 0 ? 'pos' : 'neg'}">${s.pnlPct >= 0 ? '+' : '−'}${Math.abs(s.pnlPct).toFixed(1)}%</td>
      <td>${s.weight != null ? s.weight + '%' : '–'}</td>
      <td>${s.volatility == null ? '–' : s.volatility + '%'}</td><td>${s.pe != null ? Number(s.pe).toFixed(1) : '–'}</td>
      <td class="left">${c.action ? `<span class="call ${esc(c.action)}">${esc(c.action)}</span>` : ''}</td>
      <td class="left why">${esc(c.reason || '')}</td></tr>`;
  }).join('');
  const review = d.review || {};
  const minutes = (d.trace || []).map(minuteItem).join('');
  const returns = d.stocks.filter(s => String(s.priceSource).startsWith('live'))
    .map(s => ({label: s.ticker, value: s.pnlPct})).sort((a, b) => b.value - a.value);
  const actionCount = a => Object.values(calls).filter(c => c.action === a).length;
  document.getElementById('portfolioResult').innerHTML = `<article class="sheet">
    <dl class="tiles port">
      ${tile('Value today', inr(d.totalValue, 0), `${d.stocks.length} holdings`)}
      ${tile('Invested', inr(d.totalCost, 0), '')}
      ${tile('Gain or loss', `<span class="${pnlCls}">${sign}${inr(Math.abs(d.totalPnL), 0)}</span>`, `${sign}${Math.abs(d.totalPnLPct).toFixed(1)}% overall`)}
      ${best ? tile('Best', esc(best.ticker), `<span class="pos">${best.pnlPct >= 0 ? '+' : '−'}${Math.abs(best.pnlPct).toFixed(1)}%</span>`) : ''}
      ${worst ? tile('Worst', esc(worst.ticker), `<span class="neg">${worst.pnlPct >= 0 ? '+' : '−'}${Math.abs(worst.pnlPct).toFixed(1)}%</span>`) : ''}
      ${tile('Priced live', `${d.livePriced} of ${d.stocks.length}`, d.livePriced < d.stocks.length ? 'Others use your buy price' : 'All holdings')}
    </dl>

    ${(d.skippedRows || []).length ? `<p class="notice" style="margin:16px 0 0">Skipped ${d.skippedRows.length} row${d.skippedRows.length > 1 ? 's' : ''} from your file: ${esc(d.skippedRows.join('; '))}.</p>` : ''}
    <section><h3>The review</h3>
      ${review.degraded ? '<p class="notice" style="margin:0 0 10px">Written by the rule-based fallback; the LLM was not available.</p>' : ''}
      <p>${esc(review.summary || '')}</p>
      <ul class="advice-list" style="margin-top:10px">${(review.actions || d.advice || []).map(a => `<li>${esc(a)}</li>`).join('')}</ul>
      <div class="call-counts">${['ADD', 'HOLD', 'TRIM', 'REVIEW'].map(a => `<span class="call ${a}">${a}</span> ${actionCount(a)}`).join('<span class="sep"></span>')}</div>
      <dl class="tiles compact">${tile('Portfolio risk', `${d.riskScore}/100`, d.riskScore > 60 ? 'High' : d.riskScore > 40 ? 'Moderate' : 'Low')}
        ${tile('Diversification', `${d.diversificationScore}/100`, d.diversificationScore >= 60 ? 'Well spread' : d.diversificationScore >= 35 ? 'Could be wider' : 'Concentrated')}
        ${tile('Style', esc(d.investmentStyle || '–'), '')}</dl>
    </section>

    <div class="two-col charts">
      <section><h3>Return by holding</h3>${returns.length ? divergingBars(returns) : '<p class="section-note">No live prices.</p>'}</section>
      <section><h3>Where the money sits</h3>
        <div class="alloc">${sectors.map(([s, p], i) => `<span style="width:${p}%;background:${SECTOR_TONES[i]}" data-label="${esc(s)}" data-value="${p}"></span>`).join('')}</div>
        <ul class="alloc-list">${sectors.map(([s, p], i) => `<li><i style="background:${SECTOR_TONES[i]}"></i><span>${esc(s)}</span><b>${p}%</b></li>`).join('')}</ul>
      </section>
    </div>

    <section><h3>Risk map</h3>
      <p class="section-note">Each holding by how much it moves and how much of your money it holds. Blue dots are in profit, red at a loss. Holdings in the shaded corner deserve a second look.</p>
      <div class="chart" id="riskMapHost"></div></section>

    <section><h3>Holdings</h3><div class="table-wrap"><table class="holdings">
      <thead><tr><th>Stock</th><th>3 months</th><th>Qty</th><th>Bought at</th><th>Price now</th><th>Return</th><th>Weight</th><th>Daily vol.</th><th>P/E</th><th class="left">Call</th><th class="left">Why</th></tr></thead>
      <tbody>${rows}</tbody></table></div></section>
    <section class="no-print"><details><summary>Agent minutes for this review (${(d.trace || []).length} messages)</summary>
      <div class="minutes" style="border:none"><ol>${minutes}</ol></div></details>
      ${d.meta ? `<p class="run-foot" style="border:none">Run ${esc(d.meta.runId)}. <a href="trace.html?run=${encodeURIComponent(d.meta.runId)}" target="_blank" rel="noopener">Open the full trace</a></p>` : ''}
    </section>
    <p class="disclaimer">Educational analysis, not investment advice.</p>
  </article>`;
  const root = document.getElementById('portfolioResult');
  mountRiskMap(document.getElementById('riskMapHost'), d.stocks);
  root.querySelectorAll('.dbar-row').forEach(r => hoverable(r, r.dataset.label, [['return', (+r.dataset.value >= 0 ? '+' : '') + r.dataset.value + '%', +r.dataset.value >= 0 ? GAIN : LOSS]]));
  root.querySelectorAll('.alloc span').forEach(sp => hoverable(sp, sp.dataset.label, [['of the portfolio', sp.dataset.value + '%']]));
}

/* ---------------- history (memory) ---------------- */
async function loadHistory() {
  const el = document.getElementById('historyList'), sum = document.getElementById('trackSummary');
  el.innerHTML = '<p class="empty-note">Loading your analyses and how the prices moved since…</p>';
  sum.innerHTML = '';
  try {
    const res = await fetch('/api/track-record', {credentials: 'include'});
    if (res.status === 401) { location.href = 'login.html'; return; }
    const {calls, summary} = await res.json();
    if (!calls.length) {
      el.innerHTML = `<div class="brief-empty"><h3>No analyses yet</h3><p>Run one from Analyse. Each call is kept here with its price, so you can see how it turned out after one and four weeks.</p>
        <button class="secondary" type="button" data-page="analyse">Analyse a stock</button></div>`;
      return;
    }
    const pctCell = v => v == null ? '<td class="muted">–</td>' : `<td class="${v > 0 ? 'pos' : v < 0 ? 'neg' : ''}">${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)}%</td>`;
    const groups = Object.entries(summary.byRecommendation || {}).map(([rec, g]) =>
      `<div class="tile"><dt>${esc(rec)} calls</dt><dd>${g.right} of ${g.calls} borne out</dd><p class="tile-sub">average ${g.avg4w > 0 ? '+' : ''}${g.avg4w.toFixed(1)}% after 4 weeks</p></div>`).join('');
    sum.innerHTML = `<section class="track">
      <dl class="tiles compact">
        <div class="tile"><dt>Analyses</dt><dd>${summary.calls}</dd><p class="tile-sub">${summary.tooEarly} too recent to judge</p></div>
        <div class="tile"><dt>Judged after 4 weeks</dt><dd>${summary.judged ? `${summary.right} of ${summary.judged}` : '–'}</dd><p class="tile-sub">${summary.judged ? 'borne out' : 'none old enough yet'}</p></div>
        ${groups}
      </dl>
      <p class="hint">${esc(summary.rule)} A handful of calls is not proof of skill either way.</p></section>`;
    const verdict = v => ({right: '<span class="verdict-tag approve">borne out</span>', wrong: '<span class="verdict-tag revise">not borne out</span>',
                           'too early': '<span class="muted">too early</span>', 'no data': '<span class="muted">no price data</span>'}[v] || '');
    el.innerHTML = `<div class="table-wrap"><table class="history"><thead><tr><th>When</th><th>Stock</th><th>Call</th><th>Price then</th>
      <th>After 1 week</th><th>After 4 weeks</th><th>Since then</th><th>Result</th><th></th></tr></thead><tbody>
      ${calls.map(r => `<tr><td>${esc(new Date(r.date + 'T00:00:00').toLocaleDateString('en-IN', {day: 'numeric', month: 'short', year: 'numeric'}))}</td>
        <td><button type="button" class="link-btn tk-btn" data-analyse="${esc(r.ticker)}" title="Analyse ${esc(r.ticker)} again">${esc(r.ticker)}</button></td>
        <td class="rec ${esc(r.recommendation)}">${esc(r.recommendation)}</td><td>${r.price ? inr(r.price) : '–'}</td>
        ${pctCell(r.after1w)}${pctCell(r.after4w)}${pctCell(r.nowPct)}<td>${verdict(r.verdict)}</td>
        <td><a href="trace.html?run=${encodeURIComponent(r.runId)}" target="_blank" rel="noopener">Trace</a></td></tr>`).join('')}
    </tbody></table></div>`;
  } catch (e) {
    el.innerHTML = '<p class="empty-note">Could not load your history. Refresh to try again.</p>';
  }
}
document.addEventListener('click', ev => {
  const b = ev.target.closest('[data-analyse]');
  if (b) analyseStock(b.dataset.analyse);
});

/* ---------------- account: saved profile and password ---------------- */
const PROFILE_FIELDS = ['age', 'experience', 'portfolioValue', 'timeHorizon', 'riskAppetite', 'goal'];
const cap = f => 'p' + f[0].toUpperCase() + f.slice(1);

/* A saved profile collapses into one line on the analysis form; "Change" opens the fields. */
let savedProfile = null, editingProfile = false;
const EXPERIENCE_TEXT = {Beginner: 'new to investing', Intermediate: 'some years of investing', Experienced: '5+ years of investing'};
const HORIZON_TEXT = {'Short-term': 'needs the money within a year', 'Medium-term': 'needs it in 1 to 3 years', 'Long-term': 'needs it in 5 years or more'};
const FALL_TEXT = {Conservative: 'would sell after a 20% fall', Moderate: 'would hold through a 20% fall', Aggressive: 'would buy more after a 20% fall'};

function showProfileForm(mode) {      // mode: 'collapsed' | 'editing' | 'first'
  const collapsed = mode === 'collapsed';
  document.getElementById('youCard').hidden = !collapsed;
  document.getElementById('profileFields').hidden = collapsed;
  document.getElementById('youIntro').hidden = mode !== 'first';
  document.getElementById('youEditing').hidden = mode !== 'editing';
  document.getElementById('youEdit').setAttribute('aria-expanded', String(!collapsed));
  document.getElementById('remember').checked = mode === 'first';
  document.getElementById('rememberText').textContent = mode === 'first' ? 'Save to my profile' : 'Also save these as my profile';
  editingProfile = mode === 'editing';
}
function fillProfileFields(profile) {
  PROFILE_FIELDS.forEach(f => { const a = document.getElementById(f); if (a) a.value = profile[f] ?? ''; });
}
function renderYouCard(p) {
  const monthly = p.monthlyInvest ? `, adds ${inr(p.monthlyInvest, 0)} a month` : '';
  document.getElementById('youLine').textContent =
    `${p.age} years old, ${EXPERIENCE_TEXT[p.experience] || p.experience}, ${inr(p.portfolioValue, 0)} to invest${monthly}, ` +
    `${HORIZON_TEXT[p.timeHorizon] || p.timeHorizon}, ${FALL_TEXT[p.riskAppetite] || p.riskAppetite}.`;
  const goals = (p.goals || []).map(g => g.title + (g.year ? ` by ${g.year}` : ''));
  const g = document.getElementById('youGoal');
  const goalText = goals.length ? `${goals.length > 1 ? 'Goals' : 'Goal'}: ${goals.join(', ')}` : (p.goal ? `Goal: ${p.goal}` : '');
  g.textContent = goalText; g.hidden = !goalText;
  const av = document.getElementById('youAvoid');
  av.textContent = (p.avoidSectors || []).length ? `Avoiding: ${p.avoidSectors.join(', ').toLowerCase()}` : '';
  av.hidden = !(p.avoidSectors || []).length;
}
document.getElementById('youProfile').addEventListener('click', () => openPage('profile'));
document.getElementById('youEdit').addEventListener('click', () => {
  showProfileForm('editing'); document.getElementById('portfolioValue').focus();
});
document.getElementById('youReset').addEventListener('click', () => {
  if (savedProfile) { fillProfileFields(savedProfile); showProfileForm('collapsed'); }
});

async function loadProfile() {
  try {
    const res = await fetch('/api/profile', {credentials: 'include'});
    if (!res.ok) { showProfileForm('first'); return; }
    const {saved, profile} = await res.json();
    PROFILE_FIELDS.forEach(f => {
      const a = document.getElementById(f), b = document.getElementById(cap(f));
      // nothing saved yet: the account form starts from what is in the analysis form
      const v = saved ? (profile[f] ?? '') : (a ? a.value : (profile[f] ?? ''));
      if (b) b.value = v;
    });
    if (saved) {
      savedProfile = profile;
      renderYouCard(profile);
      if (!editingProfile) { fillProfileFields(profile); showProfileForm('collapsed'); }
    } else if (!editingProfile) {
      showProfileForm('first');
    }
  } catch (e) { showProfileForm('first'); }
}

async function saveProfile(values) {
  const body = {};
  PROFILE_FIELDS.concat(['goals', 'monthlyInvest', 'avoidSectors', 'name']).forEach(f => { if (f in values) body[f] = values[f]; });
  const res = await fetch('/api/profile', {method: 'PUT', credentials: 'include',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const data = await res.json();
  if (!res.ok) throw data;
  return data;
}

let accountFormMounted = false;
function mountAccountProfile() {
  ProfileForm.mount(document.getElementById('accountProfile'), {
    submitLabel: 'Save profile', onSaved: p => { editingProfile = false; loadProfile(); setUser(ME.email, p.name); },
  });
  accountFormMounted = true;
}
document.getElementById('passwordForm').addEventListener('submit', async ev => {
  ev.preventDefault();
  const ok = document.getElementById('pwOk'), err = document.getElementById('pwErr');
  ok.hidden = err.hidden = true;
  const res = await fetch('/api/account/password', {method: 'POST', credentials: 'include',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({current: document.getElementById('pwCurrent').value, new: document.getElementById('pwNew').value})});
  const data = await res.json().catch(() => ({}));
  if (res.ok) { ok.hidden = false; ev.target.reset(); }
  else { err.textContent = data.error || 'Could not change the password.'; err.hidden = false; }
});
