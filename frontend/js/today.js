/* Today: the screen you land on after signing in. */
attachSuggest(document.getElementById('todayInput'), document.getElementById('todaySuggest'), c => {
  document.getElementById('todayInput').value = '';
  analyseStock(c.symbol);
});
document.getElementById('todaySearch').addEventListener('submit', e => {
  e.preventDefault();
  const v = document.getElementById('todayInput').value.trim();
  if (v) { document.getElementById('todayInput').value = ''; analyseStock(v.toUpperCase()); }
});

let todayLoading = false;
async function loadToday() {
  if (todayLoading) return;
  todayLoading = true;
  try {
    const t = await api('/api/today');
    renderTodayHead(t);
    renderSetup(t);
    renderTodayBrief(t);
    renderRecent(t.recent);
    renderTodayAlerts(t);
    renderGoals(t.goals);
    setBadge(t.unseen);
    $('tHoldings').innerHTML = cardHead('tHoldTitle', 'Your holdings today', 'portfolio', 'Portfolio') +
      (t.holdingsCount ? '<p class="t-muted">Pricing your holdings…</p>' :
        '<p class="t-muted">Upload your holdings to see today’s profit or loss here and get a closing brief at 3:15.</p><button class="secondary small" type="button" data-page="portfolio">Upload holdings</button>');
    $('tWatch').innerHTML = cardHead('tWatchTitle', 'Watchlist', 'watchlist', 'Watchlist') +
      (t.watchCount ? '<p class="t-muted">Fetching prices…</p>' :
        '<p class="t-muted">Follow companies to get a morning brief on them at 8:30.</p><button class="secondary small" type="button" data-page="watchlist">Add companies</button>');
    if (t.holdingsCount || t.watchCount) loadTodayLive(t);
  } catch (e) {
    $('tBrief').innerHTML = `<p class="t-muted">${esc(e.message)}</p>`;
  } finally { todayLoading = false; }
}
window.loadToday = loadToday;

function cardHead(id, title, page, linkText) {
  return `<header class="card-head"><h2 id="${id}">${esc(title)}</h2>${page ? `<a href="#${page}" data-page="${page}">${esc(linkText)}</a>` : ''}</header>`;
}

function renderTodayHead(t) {
  $('todayDate').textContent = t.dateText;
  $('todayTitle').textContent = t.name ? `${t.greeting}, ${t.name}` : t.greeting;
  $('todayMarket').textContent = t.marketStatus;
  if (t.name) setUser(ME.email, t.name);
}

function renderSetup(t) {
  const steps = [
    [t.hasProfile, 'Tell us about you and your goals', 'profile'],
    [t.watchCount > 0, 'Add companies to your watchlist', 'watchlist'],
    [t.holdingsCount > 0, 'Upload your holdings', 'portfolio'],
  ];
  const left = steps.filter(s => !s[0]).length;
  const el = $('todaySetup');
  el.hidden = left === 0;
  if (!left) return;
  el.innerHTML = `<p class="setup-title"><b>Finish setting up</b> <span>${steps.length - left} of ${steps.length} done</span></p>
    <ol class="setup-steps">${steps.map(([done, text, page]) =>
      `<li class="${done ? 'done' : ''}">${done ? `<span>${esc(text)}</span>` : `<a href="#${page}" data-page="${page}">${esc(text)}</a>`}</li>`).join('')}</ol>`;
}

function renderTodayBrief(t) {
  // After 3:15 the closing brief is the fresher one.
  const b = (t.closing && t.closing.day === t.today) ? t.closing : t.morning;
  const head = cardHead('tBriefTitle', b ? (b.kind === 'closing' ? 'Closing brief' : 'Morning brief') : 'Your briefs',
                        b && b.kind === 'closing' ? 'portfolio' : 'watchlist', 'Full brief');
  if (!b) {
    $('tBrief').innerHTML = head + `<p class="t-muted">At 8:30 on market days the market watch agent writes a brief on your watchlist, and at 3:15 one on your holdings. They appear here.</p>`;
    return;
  }
  const s = b.summary || {};
  const when = b.day === t.today ? `Today, ${b.generatedIst.split(', ').pop()}` : b.generatedIst;
  $('tBrief').innerHTML = head + `<p class="t-when">${esc(when)}</p>
    <p class="t-headline">${esc(s.headline || '')}</p>
    ${(s.points || []).length ? `<ul class="t-points">${s.points.slice(0, 3).map(p => `<li>${esc(p)}</li>`).join('')}</ul>` : ''}
    ${(s.actions || []).length ? `<p class="t-check"><b>To check:</b> ${esc(s.actions[0])}</p>` : ''}`;
}

async function loadTodayLive(t) {
  try {
    const live = await api('/api/today/live');
    const h = live.holdings;
    if (h) {
      $('tHoldings').innerHTML = cardHead('tHoldTitle', 'Your holdings today', 'portfolio', 'Portfolio') + `
        <dl class="tiles compact">
          ${tile('Value', inr(h.value, 0), `${h.priced} of ${h.count} priced`)}
          ${tile('Today', `<span class="${cls(h.dayPnL)}">${money(h.dayPnL)}</span>`, pct(h.dayPnLPct))}
          ${tile('Overall', `<span class="${cls(h.totalPnLPct)}">${pct(h.totalPnLPct, 1)}</span>`, 'since you bought')}
        </dl>
        ${h.movers.length ? `<p class="t-movers">Moving most: ${h.movers.map(m => `<button type="button" class="link-btn tk-btn" data-analyse="${esc(m.ticker)}">${esc(m.ticker)}</button> <span class="${cls(m.changePct)}">${pct(m.changePct, 1)}</span>`).join(', ')}</p>` : ''}
        ${h.asOf ? `<p class="t-muted small">Prices as of ${esc(new Date(h.asOf + 'T00:00:00').toLocaleDateString('en-IN', {day: 'numeric', month: 'short'}))}, delayed up to 15 minutes.</p>` : ''}`;
    }
    if (live.watch.length) {
      $('tWatch').innerHTML = cardHead('tWatchTitle', 'Watchlist', 'watchlist', 'Watchlist') +
        `<ul class="t-watch">${live.watch.map(w => `<li>
          <button type="button" class="link-btn tk-btn" data-analyse="${esc(w.ticker)}" title="Analyse ${esc(w.ticker)}">${esc(w.ticker)}</button>
          <span class="t-spark">${sparkline(w.history, 72, 22)}</span>
          <span class="t-px">${inr(w.price)}</span><span class="t-ch ${cls(w.changePct)}">${pct(w.changePct, 1)}</span></li>`).join('')}</ul>`;
    }
  } catch (e) { /* the cards keep their placeholders */ }
}

function renderRecent(runs) {
  const head = cardHead('tRecentTitle', 'Recent analyses', 'history', 'History and track record');
  $('tRecent').innerHTML = head + (runs.length ? `<ul class="t-recent">${runs.map(r => `<li>
      <button type="button" class="link-btn tk-btn" data-analyse="${esc(r.ticker)}" title="Analyse ${esc(r.ticker)} again">${esc(r.ticker)}</button>
      <span class="rec ${esc(r.recommendation)}">${esc(r.recommendation)}</span>
      <span class="t-muted">${r.price ? 'at ' + inr(r.price) + ', ' : ''}${esc(ago(r.created_at))}</span></li>`).join('')}</ul>`
    : `<p class="t-muted">Pick any NSE company in the search above. Ten agents research it, argue about it, and size a position for you.</p>`);
}

function renderTodayAlerts(t) {
  const head = cardHead('tAlertsTitle', t.unseen ? `Alerts (${t.unseen} new)` : 'Alerts', 'watchlist', 'All alerts');
  $('tAlerts').innerHTML = head + (t.alerts.length ? `<ul class="alerts">${t.alerts.slice(0, 5).map(alertItem).join('')}</ul>`
    : `<p class="t-muted">Price-moving news, moves of 3% or more and your own price levels show up here during market hours.</p>`) +
    (t.priceAlerts.length ? `<p class="t-muted small">Watching ${t.priceAlerts.map(a => `${esc(a.ticker)} ${a.direction === 'below' ? '<' : '>'} ${inr(a.price, 0)}`).join(', ')}</p>` : '');
}

function renderGoals(goals) {
  const head = cardHead('tGoalsTitle', 'Your goals', 'profile', 'Edit');
  $('tGoals').innerHTML = head + (goals.length ? `<ul class="t-goals">${goals.map(g => `<li>
      <b>${esc(g.title)}</b>
      <span>${g.amount ? inr(g.amount, 0) : ''}${g.amount && g.year ? ' by ' : ''}${g.year || ''}</span>
      ${g.yearsLeft != null ? `<span class="t-left">${g.yearsLeft <= 0 ? 'this year' : g.yearsLeft === 1 ? '1 year left' : g.yearsLeft + ' years left'}</span>` : ''}</li>`).join('')}</ul>
      <p class="t-muted small">The committee weighs every stock against your nearest goal.</p>`
    : `<p class="t-muted">Add what you are saving for, with an amount and a year. The committee then checks each stock against it.</p><button class="secondary small" type="button" data-page="profile">Add a goal</button>`);
}
