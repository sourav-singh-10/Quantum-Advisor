/* A run as a sequence diagram: one lane per agent, time running down the page, and an
   arrow for every message from the sender's lane to the receiver's. Tool calls sit on the
   agent's own lane; messages to the whole committee span every lane. It reads the same
   events as AgentFlow, so Replay can drive either view. No dependencies. */
(function (global) {
  const LANES = {
    User: ['You', 'You'], Planner: ['Planner', 'Plan'], ProfileAgent: ['Profile', 'Prof'],
    MarketAnalyst: ['Market', 'Mkt'], FundamentalsAnalyst: ['Fundamentals', 'Fund'], NewsAnalyst: ['News', 'News'],
    DocumentAnalyst: ['Document', 'Doc'], RiskManager: ['Risk manager', 'Risk'], StrategyAgent: ['Strategist', 'Strat'],
    PortfolioAgent: ['Portfolio', 'Port'], ReportAgent: ['Reporter', 'Rep'],
  };
  const ORDER = Object.keys(LANES);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const tool = t => String(t || '').replace(/^tool:/, '').replace(/^get_/, '').replace(/_/g, ' ');

  function label(e) {
    const p = e.payload || {};
    switch (e.type) {
      case 'request': return `Analyse ${p.ticker || ''}`;
      case 'task': return 'Task';
      case 'result': return 'Report';
      case 'error': return 'Failed';
      case 'plan': return `Plan: ${(p.tasks || []).length} agents`;
      case 'assessment': return p.action === 'retry' ? 'Re-plan' : 'Reports checked';
      case 'replan': return 'Retry';
      case 'draft': return `Draft: ${p.recommendation || ''}`;
      case 'critique': return p.verdict === 'approve' ? 'Approved' : `Objection${(p.objections || []).length ? ' ' + p.objections.map(o => o.id).join(', ') : ''}`;
      case 'followup': return 'Asks for evidence';
      case 'answer': return 'Evidence';
      case 'decision': return p.recommendation ? `Decision: ${p.recommendation}` : (p.followup === 'granted' ? 'Go back to your tools' : 'Declined');
      case 'arbitration': return `Ruling: ${p.recommendation || ''}`;
      case 'challenge': return 'Challenge';
      case 'reply': return 'Reply';
      case 'reconciliation': return 'Ruling';
      case 'final': return 'Final report';
      case 'memory': return 'Last analysis';
      default: return e.type;
    }
  }
  function kind(e) {
    const p = e.payload || {};
    if (e.type === 'critique') return p.verdict === 'approve' ? 'approve' : 'objection';
    if (['error', 'replan', 'challenge'].includes(e.type)) return 'objection';
    if (['followup', 'answer'].includes(e.type) || (e.type === 'decision' && p.followup)) return 'follow';
    if (e.type === 'decision' && p.recommendation) return 'decide';
    return '';
  }

  function SequenceView(host, opts = {}) {
    const used = new Set();
    (opts.events || []).forEach(e => { [e.from, e.to].forEach(a => { if (LANES[a]) used.add(a); }); });
    this.lanes = (used.size ? ORDER.filter(a => used.has(a)) : ORDER);
    this.n = this.lanes.length;
    this.t0 = opts.events && opts.events[0] ? Date.parse(opts.events[0].ts) : null;
    this.root = document.createElement('div');
    this.root.className = 'sq';
    this.root.style.setProperty('--lanes', this.n);
    this.root.innerHTML = `<div class="sq-head" role="row"><span class="sq-t">Time</span><div class="sq-lanes">${this.lanes.map(a =>
      `<span class="sq-lane" data-lane="${a}"><i></i><b class="long">${LANES[a][0]}</b><b class="short">${LANES[a][1]}</b></span>`).join('')}</div></div>
      <div class="sq-body" tabindex="0" aria-label="Messages in order"><div class="sq-inner"><div class="sq-rails" aria-hidden="true">${this.lanes.map(() => '<i></i>').join('')}</div><ol class="sq-rows"></ol></div>
      <p class="sq-empty">Messages appear here, top to bottom, as the run plays.</p></div>`;
    host.appendChild(this.root);
    this.rows = this.root.querySelector('.sq-rows');
    this.body = this.root.querySelector('.sq-body');
    this.lastTool = {};
  }
  SequenceView.prototype.x = function (agent) {
    const i = this.lanes.indexOf(agent);
    return i < 0 ? null : (i + 0.5) / this.n * 100;
  };
  SequenceView.prototype.reset = function () {
    this.rows.textContent = ''; this.lastTool = {};
    this.root.classList.remove('has-rows');
    this.root.querySelectorAll('.sq-lane').forEach(l => l.className = 'sq-lane');
  };
  SequenceView.prototype.lane = function (agent, st) {
    const l = this.root.querySelector(`.sq-lane[data-lane="${agent}"]`);
    if (l) l.className = 'sq-lane ' + st;
  };
  SequenceView.prototype.time = function (e) {
    if (!this.t0 || !e.ts) return '';
    const s = Math.max(0, Math.round((Date.parse(e.ts) - this.t0) / 1000));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  };
  SequenceView.prototype.apply = function (e, opts = {}) {
    const from = e.from === 'team' ? 'Planner' : e.from, to = e.to;
    const animate = opts.animate !== false;
    // a tool's answer marks the call it answers, instead of a row of its own
    if (e.type === 'tool_result') {
      const pill = this.lastTool[to];
      if (pill) { pill.classList.add((e.payload || {}).ok === false ? 'bad' : 'ok'); }
      return;
    }
    const li = document.createElement('li');
    li.className = 'sq-row' + (animate ? ' new' : '') + (opts.beat ? ' beat' : '');
    let inner = '';
    const k = kind(e);
    if (e.type === 'tool_call' && LANES[from]) {
      const x = this.x(from);
      inner = `<span class="sq-tool" style="left:${x}%">${esc(tool(e.to))}</span>`;
      this.lane(from, 'working');
    } else if (LANES[from] && (to === 'team' || to === 'committee' || !LANES[to])) {
      const x = this.x(from);
      inner = `<span class="sq-all ${k}" style="left:${100 / this.n / 2}%;right:${100 / this.n / 2}%"></span><span class="sq-dot ${k}" style="left:${x}%"></span>
        <span class="sq-label ${k}" style="left:${x}%">${esc(label(e))}</span>`;
    } else if (LANES[from] && LANES[to]) {
      const a = this.x(from), b = this.x(to), left = Math.min(a, b), w = Math.abs(a - b);
      inner = `<span class="sq-arrow ${k} ${b > a ? 'right' : 'left'}" style="left:${left}%;width:${w}%"><i></i></span>
        <span class="sq-dot ${k}" style="left:${a}%"></span>
        <span class="sq-label ${k}" style="left:${left + w / 2}%">${esc(label(e))}</span>`;
      this.lane(from, e.type === 'error' ? 'failed' : 'done');
      if (['task', 'replan', 'followup', 'draft'].includes(e.type)) this.lane(to, 'working');
    } else return;
    li.innerHTML = `<span class="sq-t">${this.time(e)}</span><div class="sq-lanes">${inner}</div>`;
    if (e.type === 'tool_call') this.lastTool[from] = li.querySelector('.sq-tool');
    this.rows.appendChild(li);
    this.root.classList.add('has-rows');
    this.rows.querySelectorAll('.sq-row.now').forEach(r => r.classList.remove('now'));
    li.classList.add('now');
    const top = li.offsetTop - this.body.clientHeight + li.offsetHeight + 24;
    this.body.scrollTo({top: Math.max(0, top), behavior: animate ? 'smooth' : 'auto'});
  };
  global.SequenceView = SequenceView;
})(window);
