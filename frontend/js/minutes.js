/* Shared helpers: turn trace events (agent messages) into readable minutes.
   Used by the main app and by trace.html. */
const AGENT_NAMES = {
  User: 'You', Planner: 'Planner', ProfileAgent: 'Profile', MarketAnalyst: 'Market analyst',
  FundamentalsAnalyst: 'Fundamentals', NewsAnalyst: 'News analyst', DocumentAnalyst: 'Document analyst', RiskManager: 'Risk manager',
  StrategyAgent: 'Strategist', PortfolioAgent: 'Portfolio', ReportAgent: 'Reporter',
  PortfolioReviewAgent: 'Portfolio reviewer', BriefAgent: 'Market watch', Scheduler: 'Scheduler', memory: 'Memory', team: 'the committee',
};
const KIND_NAMES = {
  request: 'request', plan: 'plan', task: 'task', tool_call: 'uses a tool', tool_result: 'tool result',
  result: 'result', error: 'error', replan: 're-plan', assessment: 'assessment', draft: 'draft',
  critique: 'critique', arbitration: 'arbitration', challenge: 'challenge', reply: 'reply',
  reconciliation: 'ruling', decision: 'decision', final: 'final', memory: 'memory',
  followup: 'asks for evidence', answer: 'answer',
};

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}
function partyName(p) {
  if (!p) return '';
  if (p.startsWith('tool:')) return p.slice(5).replace(/_/g, ' ');
  return AGENT_NAMES[p] || p;
}
function inr(n, digits = 2) {
  return '₹' + Number(n).toLocaleString('en-IN', {minimumFractionDigits: digits, maximumFractionDigits: digits});
}

function describeEvent(e) {
  const p = e.payload || {};
  switch (e.type) {
    case 'request':
      return p.ticker ? `Analyse ${p.ticker} for ${/^[aeiou]/i.test(p.experience || '') ? 'an' : 'a'} ${String(p.experience || '').toLowerCase()} investor, ${String(p.timeHorizon || '').toLowerCase()} horizon.`
                      : `Review ${p.file || 'the uploaded portfolio'}.`;
    case 'plan': return `${p.reasoning} Assigned: ${(p.tasks || []).map(t => partyName(t.agent)).join(', ')}.`;
    case 'task': return p.instruction || '';
    case 'tool_call': {
      const t = partyName(e.to);
      const why = p.thought && p.thought !== 'default order' ? ` ${p.thought}` : '';
      return `${t}(${p.argument ?? ''}).${why}`;
    }
    case 'tool_result':
      if (!p.ok) return `Failed: ${p.error}`;
      if (p.summary) return p.summary;
      return Object.entries(p).filter(([k, v]) => k !== 'ok' && v !== null && typeof v !== 'object').slice(0, 5).map(([k, v]) => `${k} ${v}`).join(', ');
    case 'result':
      return p.marketSummary || p.fundamentalsSummary || p.newsSummary || p.documentSummary || p.riskSummary || p.profileSummary || p.summary ||
        (p.portfolioAdvice ? p.portfolioAdvice.join(' ') : Object.entries(p).filter(([, v]) => v !== null && typeof v !== 'object').slice(0, 4).map(([k, v]) => `${k} ${v}`).join(', '));
    case 'error': return p.error;
    case 'replan': return p.instruction;
    case 'assessment':
      return `${p.action === 'retry' ? 'Retry needed.' : 'Results are good enough.'} ${p.reasoning} Highest confidence allowed: ${p.confidence_cap}.`;
    case 'draft': {
      const answers = (p.responses || []).map(r => `${r.objection_id}: ${r.response}`).join(' ');
      return `${p.recommendation}, ${String(p.confidence).toLowerCase()} confidence. ${(p.rationale || []).join('; ')}.${answers ? ' Answers: ' + answers : ''}`;
    }
    case 'critique': {
      const obj = (p.objections || []).map(o => `${o.id} (${o.severity}): ${o.text}`).join(' ');
      return `${String(p.verdict).toUpperCase()}. ${p.reasoning}${obj ? ' ' + obj : ''}`;
    }
    case 'challenge': return `${(p.issues || []).join('. ')}.${p.question ? ' ' + p.question : ''}`;
    case 'reply': return p.basis || '';
    case 'reconciliation': return `Rely on ${p.trust === 'both' ? 'both, noting the difference' : p.trust + ' figures'}. ${p.reasoning} Highest confidence allowed: ${p.confidence_cap}.`;
    case 'arbitration': return `Final call ${p.recommendation} (${String(p.confidence).toLowerCase()} confidence). ${p.reasoning}`;
    case 'followup': return `Asks ${partyName(p.agent)}: ${p.question}${p.why ? ' (' + p.why + ')' : ''}`;
    case 'answer': return `${p.answer}${p.changesView ? ' This changes the earlier view.' : ''}`;
    case 'decision':
      if (p.followup) return p.followup === 'granted' ? `Sends ${partyName(p.agent)}: ${p.instruction}. ${p.reasoning}` : `Declines: ${p.reasoning}`;
      if (p.note) return p.note;
      if (p.action === 'finish') return p.check ? `Wants to stop, but ${p.check.charAt(0).toLowerCase()}${p.check.slice(1)}` : `Done: ${p.thought || 'has what it needs'}`;
      if (p.thought) return p.thought;
      return `${p.recommendation}, ${String(p.confidence || '').toLowerCase()} confidence. ${p.decidedBy || ''}`;
    case 'memory': return `Your last analysis (${String(p.created_at || '').slice(0, 10)}): ${p.recommendation}, risk ${p.riskScore}, ${String(p.trend || '').toLowerCase()}.`;
    case 'final': return p.headline || p.reason || p.status || 'Done.';
    default: return JSON.stringify(p).slice(0, 200);
  }
}

function minuteItem(e) {
  const failed = e.type === 'error' || (e.type === 'tool_result' && e.payload && e.payload.ok === false);
  let llm = '';
  if (e.llm) llm = e.llm.ok ? `<span class="m-llm">LLM, ${e.llm.latency_ms ?? '?'} ms</span>`
                            : `<span class="m-llm off">rule fallback</span>`;
  const to = e.to === e.from ? '' : `<span class="arrow">to</span>${esc(partyName(e.to))}`;
  const round = e.round ? `, round ${e.round}` : '';
  return `<li class="${failed ? 'm-fail' : ''}">
    <div><span class="m-route">${esc(partyName(e.from))} ${to}</span>
    <span class="m-kind ${esc(e.type)}">${esc(KIND_NAMES[e.type] || e.type)}${round}</span>${llm}</div>
    <div class="m-text">${esc(describeEvent(e))}</div></li>`;
}
