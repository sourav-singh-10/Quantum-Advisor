/* Watchlist, portfolio and profile pages (briefs, alerts, holdings, notifications), plus company
   suggestions for every ticker box. */

/* ---------------- suggestions as you type ---------------- */
function attachSuggest(input, list, onPick) {
  let items = [], active = -1, timer = null, seq = 0;
  const close = () => { list.hidden = true; input.setAttribute('aria-expanded', 'false'); active = -1; };
  const render = () => {
    if (!items.length) { close(); return; }
    list.innerHTML = items.map((c, i) => `<li role="option" id="${list.id}-${i}" aria-selected="${i === active}" data-i="${i}">
      <b>${esc(c.symbol)}</b><span>${esc(c.name)}</span></li>`).join('');
    list.hidden = false; input.setAttribute('aria-expanded', 'true');
    input.setAttribute('aria-activedescendant', active >= 0 ? `${list.id}-${active}` : '');
  };
  const pick = i => { const c = items[i]; if (!c) return; close(); onPick(c); };
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) { items = []; close(); return; }
    timer = setTimeout(async () => {
      const mine = ++seq;
      try {
        const r = await fetch('/api/symbols?q=' + encodeURIComponent(q), {credentials: 'include'});
        const d = await r.json();
        if (mine !== seq) return;                // an older request answered late
        items = d.results || []; active = items.length ? 0 : -1; render();
      } catch (e) { close(); }
    }, 140);
  });
  input.addEventListener('keydown', e => {
    if (list.hidden) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); active = (active + 1) % items.length; render(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); active = (active - 1 + items.length) % items.length; render(); }
    else if (e.key === 'Enter' && active >= 0) { e.preventDefault(); pick(active); }
    else if (e.key === 'Escape') close();
  });
  list.addEventListener('mousedown', e => {           // mousedown fires before the input loses focus
    const li = e.target.closest('li[data-i]');
    if (li) { e.preventDefault(); pick(+li.dataset.i); }
  });
  input.addEventListener('blur', () => setTimeout(close, 120));
}

document.getElementById('ticker').addEventListener('focus', e => e.target.select());   // typing replaces
attachSuggest(document.getElementById('ticker'), document.getElementById('tickerList'), c => {
  const t = document.getElementById('ticker'); t.value = c.symbol; t.focus();
});

/* ---------------- shared helpers ---------------- */
let watchData = null, briefsLoading = null;
const $ = id => document.getElementById(id);

function showErr(id, msg) { const el = $(id); el.textContent = msg || ''; el.hidden = !msg; }
function pct(v, digits = 2) {
  if (v == null) return '–';
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(digits)}%`;
}
function money(v) {
  if (v == null) return '–';
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}₹${Math.abs(v).toLocaleString('en-IN', {maximumFractionDigits: 0})}`;
}
function cls(v) { return v > 0 ? 'pos' : v < 0 ? 'neg' : ''; }
function ago(iso) {
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (m < 1) return 'just now';
  if (m < 60) return `${m} min ago`;
  if (m < 1440) return `${Math.round(m / 60)} h ago`;
  return new Date(iso).toLocaleDateString('en-IN', {day: 'numeric', month: 'short'});
}
async function api(path, opts = {}) {
  const res = await fetch(path, {credentials: 'include', ...opts});
  if (res.status === 401) { location.href = 'login.html'; throw new Error('signed out'); }
  const d = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(d.error || `Request failed (${res.status})`);
  return d;
}
function loadingBrief(text) {
  return `<div class="brief-card"><p class="brief-loading">${esc(text)}</p><div class="bar-loader"><span></span></div></div>`;
}
function setBadge(n) {
  document.querySelectorAll('[data-badge]').forEach(b => { b.hidden = !n; b.textContent = n; });
}

/* Briefs, alerts, watchlist and holdings come from one call, shared by both pages. */
async function loadBriefs(force) {
  if (briefsLoading && !force) return briefsLoading;
  briefsLoading = api('/api/briefs').then(d => { watchData = d; setBadge(d.unseen); return d; })
                                   .finally(() => { briefsLoading = null; });
  return briefsLoading;
}

/* ---------------- Watchlist page ---------------- */
async function loadWatch() {
  if (!watchData) $('mBody').innerHTML = loadingBrief('Loading your morning brief…');
  try {
    await loadBriefs();
    renderWatchlist(watchData.watchlist);
    renderAlerts(watchData.alerts, watchData.unseen);
    renderBrief('morning');
    loadPriceAlerts();
  } catch (e) {
    $('mBody').innerHTML = `<div class="brief-empty"><p>${esc(e.message)}</p></div>`;
  }
}
window.loadWatch = loadWatch;

function renderWatchlist(items) {
  $('wlCount').textContent = items.length ? `${items.length} of 25 companies.` : 'Up to 25 companies.';
  $('wlList').innerHTML = items.length ? items.map(w => `<li>
      <div><button type="button" class="link-btn tk-btn" data-analyse="${esc(w.ticker)}" title="Analyse ${esc(w.ticker)}">${esc(w.ticker)}</button><span>${esc(w.name || '')}</span></div>
      <div class="wl-acts">
        <button type="button" class="wl-alert" data-t="${esc(w.ticker)}" aria-label="Set a price alert for ${esc(w.ticker)}">Alert</button>
        <button type="button" class="wl-remove" data-t="${esc(w.ticker)}" aria-label="Remove ${esc(w.ticker)}">Remove</button>
      </div></li>`).join('')
    : '<li class="wl-empty">Nothing here yet. Type a company name above.</li>';
}
attachSuggest($('wlInput'), $('wlSuggest'), c => addWatch(c.symbol, c.name));
$('wlInput').addEventListener('keydown', e => {
  if (e.key === 'Enter' && $('wlSuggest').hidden && e.target.value.trim()) { e.preventDefault(); addWatch(e.target.value.trim()); }
});
async function addWatch(ticker, name) {
  showErr('wlErr', '');
  $('wlInput').value = ''; $('wlInput').disabled = true;
  $('wlInput').placeholder = `Checking ${ticker}…`;
  try {
    const d = await api('/api/watchlist', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                          body: JSON.stringify({ticker, name})});
    watchData.watchlist = d.items; renderWatchlist(d.items); renderBrief('morning');
  } catch (e) { showErr('wlErr', e.message); }
  finally { $('wlInput').disabled = false; $('wlInput').placeholder = 'Add a company, e.g. Infosys'; $('wlInput').focus(); }
}
$('wlList').addEventListener('click', async e => {
  const al = e.target.closest('.wl-alert');
  if (al) { $('paTicker').value = al.dataset.t; $('paPrice').focus(); $('paForm').scrollIntoView({block: 'nearest'}); return; }
  const b = e.target.closest('.wl-remove');
  if (!b) return;
  try {
    const d = await api('/api/watchlist/' + encodeURIComponent(b.dataset.t), {method: 'DELETE'});
    watchData.watchlist = d.items; renderWatchlist(d.items);
  } catch (err) { showErr('wlErr', err.message); }
});

/* alerts feed */
function renderAlerts(alerts, unseen) {
  setBadge(unseen);
  $('alSeen').hidden = !unseen;
  $('alList').innerHTML = alerts.length ? alerts.slice(0, 25).map(alertItem).join('')
    : '<li class="wl-empty">No alerts yet. A headline that can move a price, a move of 3% or more, or one of your price levels shows up here.</li>';
}
function alertItem(a) {
  const kind = a.kind === 'price' ? 'Big move' : a.kind === 'target' ? 'Your price alert' : (a.detail || 'News');
  return `<li class="${a.seen ? '' : 'unseen'}">
    <span class="tone ${esc(a.tone)}" aria-hidden="true"></span>
    <div><p><b>${esc(a.ticker)}</b> ${a.link ? `<a href="${esc(a.link)}" target="_blank" rel="noopener">${esc(a.title)}</a>` : esc(a.title)}</p>
    <span class="al-meta">${esc(kind)}, ${ago(a.created_at)}</span></div></li>`;
}
$('alSeen').addEventListener('click', async () => {
  await api('/api/alerts/seen', {method: 'POST'}).catch(() => {});
  watchData.alerts.forEach(a => { a.seen = 1; }); watchData.unseen = 0;
  renderAlerts(watchData.alerts, 0);
});
async function pollBadge() {
  try { setBadge((await api('/api/alerts/unseen')).unseen); } catch (e) { /* offline */ }
}

/* your price alerts */
attachSuggest($('paTicker'), $('paSuggest'), c => { $('paTicker').value = c.symbol; $('paPrice').focus(); });
async function loadPriceAlerts() {
  try { renderPriceAlerts((await api('/api/price-alerts')).items); } catch (e) { /* shown on next try */ }
}
function renderPriceAlerts(items) {
  $('paList').innerHTML = items.length ? items.map(a => `<li class="${a.triggered_at ? 'done' : ''}">
      <span><b>${esc(a.ticker)}</b> ${a.direction === 'below' ? 'falls below' : 'rises above'} ${inr(a.price)}</span>
      <span class="al-meta">${a.triggered_at ? `reached ${inr(a.triggered_price)}, ${ago(a.triggered_at)}` : 'waiting'}</span>
      <button type="button" class="wl-remove" data-pa="${a.id}" aria-label="Delete this price alert">${a.triggered_at ? 'Clear' : 'Delete'}</button></li>`).join('')
    : '<li class="wl-empty">No price alerts. Pick a stock, a direction and a price.</li>';
}
$('paForm').addEventListener('submit', async e => {
  e.preventDefault();
  showErr('paErr', '');
  const btn = e.target.querySelector('button[type="submit"]');
  btn.disabled = true;
  try {
    const d = await api('/api/price-alerts', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ticker: $('paTicker').value.trim().toUpperCase(), direction: $('paDir').value, price: parseFloat($('paPrice').value)})});
    renderPriceAlerts(d.items); $('paTicker').value = ''; $('paPrice').value = '';
  } catch (err) { showErr('paErr', err.message); }
  finally { btn.disabled = false; }
});
$('paList').addEventListener('click', async e => {
  const b = e.target.closest('[data-pa]');
  if (!b) return;
  try { renderPriceAlerts((await api('/api/price-alerts/' + b.dataset.pa, {method: 'DELETE'})).items); } catch (err) { showErr('paErr', err.message); }
});

/* ---------------- Portfolio page ---------------- */
async function loadPortfolioPage() {
  if (!watchData) $('cBody').innerHTML = loadingBrief('Loading your holdings…');
  try {
    await loadBriefs();
    renderHoldings(watchData.holdings);
    renderBrief('closing');
  } catch (e) { $('cBody').innerHTML = `<div class="brief-empty"><p>${esc(e.message)}</p></div>`; }
}
window.loadPortfolioPage = loadPortfolioPage;

function renderHoldings(items) {
  const has = items.length > 0;
  $('portActions').hidden = !has;
  $('portUpload').hidden = has && !$('portUpload').dataset.open;
  $('hdSummary').innerHTML = has
    ? `<b>${items.length} holding${items.length > 1 ? 's' : ''} saved:</b> ${items.map(h => `${esc(h.ticker)} ×${Number(h.quantity).toLocaleString('en-IN')}`).join(', ')}`
    : '';
}
$('replaceHoldings').addEventListener('click', () => {
  $('portUpload').dataset.open = '1'; $('portUpload').hidden = false; $('chooseFile').focus();
});
$('hdClear').addEventListener('click', async () => {
  const d = await api('/api/holdings', {method: 'DELETE'}).catch(() => null);
  if (d) { watchData.holdings = []; delete $('portUpload').dataset.open; renderHoldings([]); renderBrief('closing');
           $('portfolioResult').innerHTML = ''; }
});
$('reviewSaved').addEventListener('click', async () => {
  const btn = $('reviewSaved');
  btn.disabled = true; btn.textContent = 'Pricing holdings live…';
  $('portfolioResult').innerHTML = '<div class="sheet loading-sheet"><p>Pricing each holding live and asking the review agent… this takes about 20–40 seconds.</p><div class="bar-loader"><span></span></div></div>';
  try { renderPortfolio(await api('/api/holdings/review', {method: 'POST'})); }
  catch (e) { renderPortfolioError(e.message); }
  finally { btn.disabled = false; btn.textContent = 'Review my holdings now'; }
});
/* called by app.js after an upload that kept the holdings */
window.afterHoldingsSaved = async () => {
  delete $('portUpload').dataset.open;
  await loadBriefs(true);
  renderHoldings(watchData.holdings); renderBrief('closing');
};

/* ---------------- briefs (morning on Watchlist, closing on Portfolio) ---------------- */
const BRIEF_SLOTS = {morning: {body: 'mBody', when: 'mWhen', btn: 'mRefresh'}, closing: {body: 'cBody', when: 'cWhen', btn: 'cRefresh'}};
document.querySelectorAll('[data-refresh]').forEach(btn => btn.addEventListener('click', async () => {
  const kind = btn.dataset.refresh, slot = BRIEF_SLOTS[kind];
  btn.disabled = true;
  $(slot.body).innerHTML = loadingBrief(kind === 'morning'
    ? 'Fetching prices and news for each watchlist company…' : 'Pricing your holdings and reading today’s news…');
  try {
    watchData = await api(`/api/briefs/${kind}/refresh`, {method: 'POST'});
    renderBrief(kind);
  } catch (e) {
    renderBrief(kind);
    $(slot.body).insertAdjacentHTML('afterbegin', `<p class="form-error">${esc(e.message)}</p>`);
  } finally { btn.disabled = false; }
}));

function flagChips(flags) {
  return (flags || []).map(f => `<span class="flag ${esc(f.tone)}">${esc(f.text)}</span>`).join('');
}
function newsList(news) {
  if (!news || !news.length) return '';
  return `<ul class="b-news">${news.slice(0, 3).map(n => `<li>
    <span class="htag ${esc(n.tone.toLowerCase())}">${esc(n.tone)}</span>
    ${n.link ? `<a href="${esc(n.link)}" target="_blank" rel="noopener">${esc(n.title)}</a>` : esc(n.title)}
    ${n.material ? '<span class="mat">may move the price</span>' : ''}</li>`).join('')}</ul>`;
}
function stockRow(i, closing) {
  if (i.error) return `<li class="b-row err"><div class="b-id"><b>${esc(i.ticker)}</b><span>${esc(i.name || '')}</span></div>
    <p class="b-miss">No price data right now.</p></li>`;
  const held = closing ? `<div class="b-held"><span>Today <b class="${cls(i.dayPnL)}">${money(i.dayPnL)}</b></span>
      <span>Overall <b class="${cls(i.pnlPct)}">${pct(i.pnlPct, 1)}</b></span><span>${i.weight != null ? i.weight + '% of holdings' : ''}</span></div>` : '';
  return `<li class="b-row">
    <div class="b-id"><button type="button" class="link-btn tk-btn" data-analyse="${esc(i.ticker)}" title="Analyse ${esc(i.ticker)}">${esc(i.ticker)}</button><span>${esc(i.name || '')}</span></div>
    <div class="b-price"><b>${inr(i.price)}</b><span class="${cls(i.changePct)}">${pct(i.changePct)}</span></div>
    <div class="b-spark">${sparkline(i.history, 110, 30)}</div>
    <div class="b-range" title="${esc(i.rangeLabel)} range">${rangeBar(i)}</div>
    <div class="b-more">${held}<div class="flags">${flagChips(i.flags)}</div>${newsList(i.news)}</div>
  </li>`;
}
function rangeBar(i) {
  const span = i.high52 - i.low52 || 1, at = Math.min(100, Math.max(0, (i.price - i.low52) / span * 100));
  return `<span class="rb-label">${esc(i.rangeLabel)} range</span>
    <span class="rb"><i style="left:${at.toFixed(1)}%"></i></span>
    <span class="rb-ends"><span>${inr(i.low52, 0)}</span><span>${inr(i.high52, 0)}</span></span>`;
}
function summaryBlock(s) {
  if (!s) return '';
  return `<div class="b-summary">
    <p class="b-headline">${esc(s.headline)}</p>
    ${s.points && s.points.length ? `<ul>${s.points.map(p => `<li>${esc(p)}</li>`).join('')}</ul>` : ''}
    ${s.actions && s.actions.length ? `<div class="b-actions"><b>To check</b><ul>${s.actions.map(a => `<li>${esc(a)}</li>`).join('')}</ul></div>` : ''}
    <p class="b-by">${s.byLLM ? 'Written by the market watch agent from the numbers below.' : 'Written from rules because the LLM was unavailable.'}</p>
  </div>`;
}

function renderBrief(kind) {
  const d = watchData, slot = BRIEF_SLOTS[kind];
  if (!d) return;
  const b = d[kind];
  const need = kind === 'morning' ? !d.watchlist.length : !d.holdings.length;
  const isToday = b && b.day === d.today;
  const asOf = b ? b.items.map(i => i.asOf).filter(Boolean).sort().pop() : null;
  const asOfText = asOf ? `, prices as of ${new Date(asOf + 'T00:00:00').toLocaleDateString('en-IN', {day: 'numeric', month: 'short'})} close` : '';
  $(slot.when).textContent = b ? `${isToday ? 'Written today' : 'Last written'}, ${b.generatedIst}${asOfText}` : '';
  $(slot.btn).hidden = need;
  if (need) {
    $(slot.body).innerHTML = `<div class="brief-empty">${kind === 'morning'
      ? '<h3>Add companies to your watchlist</h3><p>At 8:30 every market morning you get each one’s last close, overnight news and what to watch today.</p>'
      : '<h3>Upload your holdings</h3><p>At 3:15, fifteen minutes before the close, you get today’s profit or loss, the biggest movers, news on what you own and what to check before the bell.</p>'}</div>`;
    return;
  }
  if (!b) {
    $(slot.body).innerHTML = `<div class="brief-empty"><h3>No brief yet</h3><p>The next one is written at ${kind === 'morning' ? '8:30 AM' : '3:15 PM'} on a market day. Choose “Write it now” to see one today.</p></div>`;
    return;
  }
  const closing = kind === 'closing';
  const t = b.totals;
  const tiles = closing && t ? `<dl class="tiles compact">
      ${tile('Holdings value', inr(t.value, 0), `${b.items.filter(i => !i.error).length} priced`)}
      ${tile('Today', `<span class="${cls(t.dayPnL)}">${money(t.dayPnL)}</span>`, pct(t.dayPnLPct))}
      ${tile('Overall', `<span class="${cls(t.totalPnL)}">${money(t.totalPnL)}</span>`, pct(t.totalPnLPct, 1))}</dl>` : '';
  const sorted = b.items.slice().sort((a, c) => closing ? (c.value || 0) - (a.value || 0) : Math.abs(c.changePct || 0) - Math.abs(a.changePct || 0));
  const watchMoves = closing && (b.watchMoves || []).length ? `<section class="b-watch"><h3>On your watchlist today</h3><p>${b.watchMoves.map(w =>
      `<b>${esc(w.ticker)}</b> <span class="${cls(w.changePct)}">${pct(w.changePct)}</span>`).join(', ')}</p></section>` : '';
  $(slot.body).innerHTML = `<article class="brief-card ${closing ? 'closing' : 'morning'}">
    <header class="b-head"><span></span>
      <a class="b-trace" href="trace.html?run=${encodeURIComponent(b.runId)}" target="_blank" rel="noopener">How it was written</a></header>
    ${tiles}
    ${summaryBlock(b.summary)}
    <ul class="b-list">${sorted.map(i => stockRow(i, closing)).join('')}</ul>
    ${watchMoves}
    <p class="b-note">Prices from ${esc([...new Set(b.items.filter(i => i.source).map(i => i.source))].join(', ') || 'free sources')}, delayed up to 15 minutes. Educational, not investment advice.</p>
  </article>`;
}

/* ---------------- Profile page: notifications ---------------- */
async function loadNotifications() {
  try {
    await loadBriefs();
    $('emToggle').checked = !!watchData.emailOn;
    $('emToggle').disabled = !watchData.emailAvailable;
    $('emNote').textContent = watchData.emailAvailable
      ? 'Sent to your sign-in email at 8:30 and 3:15 on market days.'
      : 'Email is not set up on this server yet.';
  } catch (e) { /* leave as is */ }
  renderTelegram(await api('/api/telegram').catch(() => ({available: false})));
}
window.loadNotifications = loadNotifications;
let tgPoll = null;
function renderTelegram(t) {
  clearInterval(tgPoll);
  if (!t.available) {
    $('tgNote').textContent = 'Telegram is not set up on this server yet.';
    $('tgAct').innerHTML = '';
  } else if (t.linked) {
    $('tgNote').textContent = 'Connected. Briefs and alerts arrive in Telegram.';
    $('tgAct').innerHTML = '<button type="button" class="link-btn" id="tgOff">Disconnect</button>';
    $('tgOff').onclick = async () => renderTelegram({...(await api('/api/telegram', {method: 'DELETE'})), available: true});
  } else {
    $('tgNote').textContent = 'Get the 8:30 and 3:15 briefs and every alert on your phone. Free.';
    $('tgAct').innerHTML = '<button type="button" class="secondary small" id="tgOn">Connect Telegram</button>';
    $('tgOn').onclick = async () => {
      try {
        const l = await api('/api/telegram/link', {method: 'POST'});
        window.open(l.url, '_blank', 'noopener');
        $('tgNote').innerHTML = `Telegram opened. Press <b>Start</b> in the chat. <a href="${esc(l.url)}" target="_blank" rel="noopener">Open the link again</a>`;
        let tries = 0;
        tgPoll = setInterval(async () => {
          const s = await api('/api/telegram').catch(() => null);
          if (s && s.linked) renderTelegram(s);
          if (++tries > 60) clearInterval(tgPoll);
        }, 5000);
      } catch (e) { $('tgNote').textContent = e.message; }
    };
  }
}
$('emToggle').addEventListener('change', async e => {
  try {
    const d = await api('/api/briefs/settings', {method: 'PUT', headers: {'Content-Type': 'application/json'},
                                                body: JSON.stringify({email: e.target.checked})});
    watchData.emailOn = d.emailOn;
  } catch (err) { e.target.checked = !e.target.checked; }
});

pollBadge();
setInterval(pollBadge, 5 * 60 * 1000);
