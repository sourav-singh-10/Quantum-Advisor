/* Home page: the walkthrough in the hero, the replay of a recorded run, and small touches.
   The page reads fine without this script; motion respects reduced-motion settings. */
(function () {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const $ = id => document.getElementById(id);

  /* ---------- signed in? ---------- */
  fetch('/me', {credentials: 'include'}).then(r => r.json()).then(me => {
    if (!me.loggedIn) return;
    ['navCta', 'heroCta', 'finalCta'].forEach(id => {
      const a = $(id);
      if (a) { a.href = '/app'; a.textContent = 'Open the app'; }
    });
    $('navSignIn').hidden = true;
  }).catch(() => {});

  /* ---------- the bar turns light once the dark hero has scrolled away ---------- */
  const nav = $('nav'), hero = document.querySelector('.h-hero'), finale = document.querySelector('.h-final');
  const onScroll = () => {
    const h = hero.getBoundingClientRect(), f = finale.getBoundingClientRect();
    nav.classList.toggle('light', h.bottom < 90 && !(f.top < 40 && f.bottom > 40));
  };
  addEventListener('scroll', onScroll, {passive: true}); onScroll();

  const seen = (el, fn, opts = {threshold: 0.35}) => {
    if (!('IntersectionObserver' in window)) { fn(true); return; }
    new IntersectionObserver(es => es.forEach(e => fn(e.isIntersecting)), opts).observe(el);
  };

  /* ---------- counters ---------- */
  document.querySelectorAll('[data-count]').forEach(el => {
    const end = Number(el.dataset.count);
    if (reduce) return;
    let done = false;
    seen(el, on => {
      if (!on || done) return;
      done = true;
      const t0 = performance.now();
      const tick = now => {
        const t = Math.min(1, (now - t0) / 1100);
        el.textContent = Math.round(end * (1 - Math.pow(1 - t, 3)));
        if (t < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
  });

  /* ---------- the walkthrough: how a run moves (an illustration, not a recording) ---------- */
  (function walkthrough() {
    const host = $('demoFlow');
    if (!host || !window.AgentFlow) return;
    const f = new AgentFlow(host, {theme: 'dark', label: 'How a run moves between the agents'});
    let timers = [];
    const later = (I, ms, fn) => {
      if (I) { fn(); return; }
      const t = setTimeout(() => { timers = timers.filter(x => x !== t); fn(); }, ms);
      timers.push(t);
    };
    const send = (I, a, b, kind) => f.send(a, b, kind, undefined, I);

    const STEPS = [
      ['You ask', 'You pick a stock. The Profile agent turns your age, horizon and attitude to risk into limits every other agent must respect.', I => {
        f.node('you', 'done', 'Asked about a stock'); f.focus('you');
        send(I, 'you', 'planner'); f.node('planner', 'working', 'Reading your request');
        later(I, 900, () => { send(I, 'planner', 'profile'); f.node('profile', 'working', 'Reading your answers'); f.check('profile', 'active'); f.focus('profile'); });
        later(I, 2100, () => { f.node('profile', 'done', 'Limits set'); send(I, 'profile', 'planner'); f.check('profile', 'done'); });
      }],
      ['Plan', 'The Planner reads your past analyses of the stock and decides which analysts this request needs. No PDF attached, so the document analyst sits this one out.', I => {
        f.focus('planner');
        f.node('planner', 'done', 'Chose 3 analysts'); f.node('docs', 'skipped', 'No PDF attached');
        f.check('plan', 'done'); f.check('research', 'active', 'Research 0/3');
      }],
      ['Research', 'The analysts work in parallel. Each one decides which tools to call: prices and indicators, company accounts, recent headlines.', I => {
        send(I, 'planner', 'market'); send(I, 'planner', 'fund'); send(I, 'planner', 'news');
        f.node('market', 'working', 'Fetching prices'); f.node('fund', 'working', 'Reading the accounts'); f.node('news', 'working', 'Reading headlines');
        f.focus('fund');
      }],
      ['Adapt', 'A price source fails. The market analyst sees the error, picks another source and carries on. Nothing is made up to fill the gap.', I => {
        f.focus('market'); f.node('market', 'warn', 'Source failed, trying another');
        if (!I) f.send('market', 'market', 'objection');
        later(I, 1800, () => f.node('market', 'working', 'Switched source'));
      }],
      ['Review', 'Each analyst reports to the Planner, which checks the reports before anyone decides. Weak or failed work is sent back and the confidence allowed is capped.', I => {
        f.node('market', 'done', 'Trend measured'); send(I, 'market', 'check');
        later(I, 350, () => { f.node('fund', 'done', 'Profit and debt checked'); send(I, 'fund', 'check'); });
        later(I, 700, () => { f.node('news', 'done', 'Tone of the news'); send(I, 'news', 'check'); f.check('research', 'active', 'Research 3/3'); });
        later(I, 1700, () => { f.node('check', 'done', 'Reports checked'); f.focus('check'); f.check('research', 'done', 'Research 3/3'); f.check('review', 'done'); });
      }],
      ['Draft', 'The strategist proposes buy, hold or sell, citing the analysts’ numbers, and sends the draft to the risk manager.', I => {
        send(I, 'check', 'strategy'); f.node('strategy', 'working', 'Writing a draft');
        later(I, 1100, () => { f.node('strategy', 'done', 'Round 1: a draft call'); f.focus('strategy'); send(I, 'strategy', 'risk');
          f.node('risk', 'working', 'Reviewing the draft'); f.check('debate', 'active', 'Debate, round 1'); });
      }],
      ['Object', 'The risk manager approves, or objects by number: R1, R2. Here it is not convinced the draft covers how much the price swings.', I => {
        f.focus('risk'); f.node('risk', 'warn', 'Round 1: objection R1');
        send(I, 'risk', 'strategy', 'objection'); f.node('strategy', 'working', 'Answering R1'); f.check('debate', 'warn', 'Objection, round 1');
      }],
      ['Ask', 'Unsure, it asks the Planner for evidence instead of guessing. The Planner sends the market analyst back to its tools, and the answer goes straight to the risk manager.', I => {
        f.node('risk', 'working', 'Asked for evidence'); send(I, 'risk', 'check', 'follow'); f.check('evidence', 'active');
        later(I, 1300, () => { f.node('check', 'working', 'Sending an analyst back'); send(I, 'check', 'market', 'follow'); f.node('market', 'working', 'Fetching a year of prices'); f.focus('market'); });
        later(I, 3000, () => { f.node('market', 'done', 'Answered the question'); send(I, 'market', 'risk', 'follow'); f.check('evidence', 'done'); });
      }],
      ['Revise', 'The strategist answers each objection with the new evidence, and the call can change. Up to three rounds; after that the Planner rules.', I => {
        f.node('strategy', 'done', 'Round 2: revised call'); f.focus('strategy'); send(I, 'strategy', 'risk');
        later(I, 1400, () => { f.node('risk', 'done', 'Approved in round 2'); f.focus('risk'); send(I, 'risk', 'strategy', 'approve'); f.check('debate', 'done', 'Approved, round 2'); });
      }],
      ['Decide', 'The Planner records the decision, the portfolio agent sizes it to your money, and the reporter explains what changed since your last analysis.', I => {
        f.node('check', 'done', 'Decision recorded'); f.focus('check'); f.check('decision', 'done', 'Decision');
        later(I, 700, () => { send(I, 'check', 'portfolio'); f.node('portfolio', 'working', 'Sizing it for you'); });
        later(I, 2000, () => { f.node('portfolio', 'done', 'Sized to your money'); f.check('sizing', 'done'); send(I, 'portfolio', 'report'); f.focus('report'); });
        later(I, 3000, () => { f.node('report', 'done', 'Report written'); f.check('report', 'done'); send(I, 'report', 'you'); });
        later(I, 4300, () => { f.node('you', 'done', 'Got the verdict'); f.focus('you'); });
      }],
    ];
    const STEP_MS = [4200, 3600, 3800, 4200, 4800, 4200, 4000, 6200, 4800, 6600];
    const items = [...$('steps').children];
    let k = -1, playing = !reduce, auto = null, visible = false;

    function go(n) {
      const unfinished = timers.length > 0;
      timers.forEach(clearTimeout); timers = []; clearTimeout(auto);
      n = (n + STEPS.length) % STEPS.length;
      if (n !== k + 1 || unfinished || n === 0) { f.reset(); for (let j = 0; j < n; j++) STEPS[j][2](true); }
      k = n;
      STEPS[k][2](false);
      $('stepNo').textContent = `Step ${k + 1} of ${STEPS.length}`;
      for (const [id, t] of [['demoTitle', STEPS[k][0]], ['stepText', STEPS[k][1]]]) {
        const el = $(id); el.textContent = t; el.classList.remove('in'); void el.offsetWidth; el.classList.add('in');
      }
      items.forEach((li, j) => { li.classList.toggle('done', j < k); li.classList.toggle('now', j === k);
        li.querySelector('button').setAttribute('aria-current', j === k ? 'step' : 'false'); });
      $('steps').style.setProperty('--step-ms', STEP_MS[k] + 'ms');
      schedule();
    }
    function schedule() {
      clearTimeout(auto);
      $('steps').classList.toggle('paused', !playing);
      if (playing && visible) auto = setTimeout(() => go(k + 1), STEP_MS[k]);
    }
    function setPlaying(on) {
      playing = on;
      const b = $('stepPlay');
      b.setAttribute('aria-pressed', String(on));
      b.querySelector('span').textContent = on ? 'Pause' : 'Play';
      if (on && visible) go(k + 1); else schedule();
    }
    $('stepPlay').addEventListener('click', () => setPlaying(!playing));
    $('stepNext').addEventListener('click', () => { playing = false; setPlaying(false); go(k + 1); });
    $('stepPrev').addEventListener('click', () => { playing = false; setPlaying(false); go(k - 1); });
    items.forEach((li, j) => li.querySelector('button').addEventListener('click', () => { setPlaying(false); go(j); }));
    go(0);
    if (reduce) setPlaying(false);
    seen(host, on => { visible = on; schedule(); }, {threshold: 0.2});
  })();

  /* ---------- a recorded run, replayed ---------- */
  (function recordedRun() {
    const host = $('runSeq');
    if (!host || !window.SequenceView || !window.Replay) return;
    fetch('samples/story_run.json').then(r => r.json()).then(story => {
      const events = story.events;
      const beats = Object.fromEntries(story.beats.map(b => [b.seq, b]));
      const seq = new SequenceView(host, {events});
      const flow = {apply: (e, o) => seq.apply(e, {...o, beat: !!beats[e.seq]}), reset: () => seq.reset()};
      const chapters = [];
      story.beats.forEach(b => { if (!chapters.find(c => c.name === b.chapter)) chapters.push({name: b.chapter, seq: b.seq}); });
      const idxOf = seq => events.findIndex(e => e.seq === seq);
      const chEl = $('runChapters');
      chEl.innerHTML = chapters.map(c => `<li><button type="button" data-seq="${c.seq}">${esc(c.name)}</button></li>`).join('');
      const day = new Date(story.date + 'T12:00:00').toLocaleDateString('en-IN', {day: 'numeric', month: 'short', year: 'numeric'});
      $('runMeta').innerHTML = `Run <code>${esc(story.runId)}</code>, recorded ${day}: ${story.messages} messages from ${story.started} to ${story.finished} UTC, ${story.llmDecisions} of ${story.llmCalls} decisions made by the model. Nothing has been edited.`;
      let chapter = null;
      const setCall = (rec, note) => { $('runCall').textContent = rec || 'None yet'; $('runCall').className = 'v ' + (rec ? rec.toLowerCase() : ''); $('runCallNote').textContent = note || ''; };
      const player = new Replay(flow, events, {
        pauseFor(e) {
          if (beats[e.seq]) return 3900;
          if (e.type === 'tool_result') return 200;
          if (e.type === 'tool_call' || e.type === 'task') return 600;
          return 1000;
        },
        onReset() { setCall(null, ''); },
        onEvent(e, k, animate) {
          const p = e.payload || {};
          if (e.type === 'draft') setCall(p.recommendation, `Round ${e.round} draft`);
          if (e.type === 'critique') $('runCallNote').textContent = `Round ${e.round}: ${p.verdict === 'approve' ? 'approved' : 'sent back'}`;
          if (e.type === 'decision' && p.recommendation) setCall(p.recommendation, `Final, ${String(p.confidence || '').toLowerCase()} confidence`);
          const b = beats[e.seq];
          if (b && b.chapter !== chapter) {
            chapter = b.chapter;
            chEl.querySelectorAll('button').forEach(x => {
              const i = chapters.findIndex(c => c.name === x.textContent), cur = chapters.findIndex(c => c.name === chapter);
              x.setAttribute('aria-current', i === cur ? 'step' : 'false'); x.classList.toggle('done', i < cur);
            });
          }
          if (e.type === 'tool_result') return;
          const route = e.to && e.to !== e.from ? `${partyName(e.from)} to ${partyName(e.to)}` : partyName(e.from);
          $('runRoute').innerHTML = `<span class="chapter">${esc(chapter || 'Brief')}</span><span>${esc(route)}, ${esc(KIND_NAMES[e.type] || e.type)}</span>`;
          if (b) {
            const cap = $('runCaption'), q = $('runQuote');
            cap.textContent = b.caption;
            const quote = String(b.quote || '');
            q.textContent = quote ? `“${quote.length > 300 ? quote.slice(0, 298).trimEnd() + '…' : quote}”` : '';
            if (animate) { cap.classList.remove('now-in'); void cap.offsetWidth; cap.classList.add('now-in'); }
          }
        },
        onState(on) {
          const btn = $('runPlay');
          btn.setAttribute('aria-pressed', String(on));
          btn.querySelector('span').textContent = on ? 'Pause' : (player && player.i >= events.length ? 'Replay' : 'Play');
          btn.querySelector('svg').innerHTML = on ? '<path d="M4 2.5h3v11H4zM9 2.5h3v11H9z"/>' : '<path d="M4 2.5v11L13.5 8z"/>';
        },
      });
      let autoplay = !reduce;   // until the visitor takes control
      $('runPlay').addEventListener('click', () => { autoplay = false; player.toggle(); });
      $('runNext').addEventListener('click', () => { autoplay = false; player.step(1); });
      $('runPrev').addEventListener('click', () => { autoplay = false; player.step(-1); });
      chEl.addEventListener('click', ev => {
        const b = ev.target.closest('button'); if (!b) return;
        autoplay = false; chapter = null;
        player.setPlaying(false); player.seek(idxOf(Number(b.dataset.seq))); player.step(1);
      });
      seen($('runPlayer'), on => {
        if (on && autoplay && !player.playing && player.i < events.length) player.setPlaying(true);
        else if (!on && player.playing) player.setPlaying(false);
      }, {threshold: 0.45});
    }).catch(() => { $('runCaption').textContent = 'The recorded run could not be loaded. Open the full trace instead.'; });
  })();
})();
