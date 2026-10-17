/* The investor profile form, shared by the welcome step after sign-up and the Account page.
   ProfileForm.mount(container, {submitLabel, skipHref, onSaved}) loads the saved profile,
   renders the form and saves it with PUT /api/profile. */
const ProfileForm = (() => {
  const AVOID = ['Tobacco', 'Alcohol', 'Gambling and betting', 'Defence and weapons', 'Coal, oil and gas'];
  const HORIZON = [['Short-term', 'Within a year'], ['Medium-term', 'In 1 to 3 years'], ['Long-term', 'In 5 years or more']];
  const FALL = [['Conservative', 'Sell to stop the loss'], ['Moderate', 'Hold and wait'], ['Aggressive', 'Buy more']];
  const EXPERIENCE = [['Beginner', 'New to it'], ['Intermediate', 'Some years'], ['Experienced', '5+ years']];
  const MAX_GOALS = 4;
  let uid = 0;
  const e = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

  function choices(name, options, value) {
    return `<div class="choice-row" role="radiogroup">${options.map(([v, label]) => `
      <label class="choice"><input type="radio" name="${name}" value="${v}" ${v === value ? 'checked' : ''}><span>${label}</span></label>`).join('')}</div>`;
  }
  function goalRow(g = {}, i = 0) {
    const id = ++uid;
    return `<div class="goal-row" data-goal>
      <div class="field"><label for="gT${id}">Goal</label><input id="gT${id}" data-k="title" maxlength="80" value="${e(g.title)}" placeholder="${i ? 'e.g. Retirement' : 'e.g. Daughter&#39;s college'}"></div>
      <div class="field"><label for="gA${id}">Amount (₹)</label><input id="gA${id}" data-k="amount" type="number" min="0" step="1000" value="${g.amount ?? ''}" placeholder="${i ? 'optional' : '20,00,000'}"></div>
      <div class="field"><label for="gY${id}">By year</label><input id="gY${id}" data-k="year" type="number" min="2025" max="2100" value="${g.year ?? ''}" placeholder="${i ? 'optional' : '2032'}"></div>
      <button type="button" class="goal-remove" aria-label="Remove this goal">Remove</button>
    </div>`;
  }

  function render(root, p, opts) {
    const goals = (p.goals && p.goals.length) ? p.goals : (p.goal ? [{title: p.goal.slice(0, 80)}] : [{}]);
    const n = ++uid;
    root.innerHTML = `<form class="pf" novalidate>
      <p class="form-ok" data-ok hidden>Saved. Every new analysis and brief uses these details.</p>
      <p class="form-error" data-err role="alert" hidden></p>

      <fieldset><legend>Your money</legend>
        <div class="row-2">
          <div class="field"><label for="pfMoney${n}">Money you could invest now (₹)</label>
            <input id="pfMoney${n}" name="portfolioValue" type="number" min="1000" step="1000" value="${p.portfolioValue ?? ''}" required></div>
          <div class="field"><label for="pfMonthly${n}">Added each month (₹) <span class="hint">optional</span></label>
            <input id="pfMonthly${n}" name="monthlyInvest" type="number" min="0" step="500" value="${p.monthlyInvest ?? ''}" placeholder="e.g. a SIP of 5,000"></div>
        </div>
      </fieldset>

      <fieldset><legend>About you</legend>
        <div class="field"><label for="pfName${n}">What should we call you? <span class="hint">optional</span></label>
          <input id="pfName${n}" name="name" maxlength="40" value="${e(p.name)}" placeholder="Your first name" autocomplete="given-name"></div>
        <div class="row-2">
          <div class="field"><label for="pfAge${n}">Age</label><input id="pfAge${n}" name="age" type="number" min="18" max="100" value="${p.age ?? ''}" required></div>
          <div class="field"><span class="label">Investing experience</span>${choices('experience' + n, EXPERIENCE, p.experience)}</div>
        </div>
        <div class="field"><span class="label">When will you need this money?</span>${choices('timeHorizon' + n, HORIZON, p.timeHorizon)}</div>
        <div class="field"><span class="label">If it fell 20% next month, you would…</span>${choices('riskAppetite' + n, FALL, p.riskAppetite)}</div>
      </fieldset>

      <fieldset><legend>Your goals</legend>
        <p class="hint">What you are saving for. The committee checks each stock against your nearest goal.</p>
        <div data-goals>${goals.map(goalRow).join('')}</div>
        <button type="button" class="link-btn" data-add-goal>Add another goal</button>
      </fieldset>

      <fieldset><legend>Companies to avoid <span class="hint">optional</span></legend>
        <p class="hint">An analysis of a company like this gets a clear note. The recommendation itself is not changed.</p>
        <div class="avoid-row">${AVOID.map(a => `<label class="choice"><input type="checkbox" name="avoid" value="${e(a)}" ${(p.avoidSectors || []).includes(a) ? 'checked' : ''}><span>${e(a)}</span></label>`).join('')}</div>
      </fieldset>

      <div class="pf-actions">
        <button class="primary" type="submit">${e(opts.submitLabel || 'Save profile')}</button>
        ${opts.skipHref ? `<a class="link-btn" href="${e(opts.skipHref)}">Skip for now</a>` : ''}
      </div>
    </form>`;

    const form = root.querySelector('form');
    const goalsBox = root.querySelector('[data-goals]'), addBtn = root.querySelector('[data-add-goal]');
    const syncAdd = () => { addBtn.hidden = goalsBox.querySelectorAll('[data-goal]').length >= MAX_GOALS; };
    syncAdd();
    addBtn.addEventListener('click', () => {
      goalsBox.insertAdjacentHTML('beforeend', goalRow({}, 1));
      goalsBox.lastElementChild.querySelector('input').focus(); syncAdd();
    });
    goalsBox.addEventListener('click', ev => {
      if (!ev.target.closest('.goal-remove')) return;
      const rows = goalsBox.querySelectorAll('[data-goal]');
      if (rows.length > 1) ev.target.closest('[data-goal]').remove();
      else rows[0].querySelectorAll('input').forEach(i => { i.value = ''; });
      syncAdd();
    });

    form.addEventListener('submit', async ev => {
      ev.preventDefault();
      const ok = root.querySelector('[data-ok]'), err = root.querySelector('[data-err]');
      ok.hidden = err.hidden = true;
      form.querySelectorAll('[aria-invalid]').forEach(x => x.removeAttribute('aria-invalid'));
      const val = name => form.querySelector(`[name="${name}"]`).value;
      const radio = name => (form.querySelector(`input[name="${name}${n}"]:checked`) || {}).value;
      const goalsOut = [...goalsBox.querySelectorAll('[data-goal]')].map(r => {
        const g = k => r.querySelector(`[data-k="${k}"]`).value.trim();
        return {title: g('title'), amount: g('amount') ? Number(g('amount')) : null, year: g('year') ? parseInt(g('year'), 10) : null};
      }).filter(g => g.title || g.amount || g.year);
      const missingName = goalsOut.find(g => !g.title);
      if (missingName) { err.textContent = 'Give each goal a name, or clear its amount and year.'; err.hidden = false; return; }
      const body = {
        name: val('name').trim() || null,
        portfolioValue: parseFloat(val('portfolioValue')) || 0,
        monthlyInvest: val('monthlyInvest') ? parseFloat(val('monthlyInvest')) : null,
        age: parseInt(val('age'), 10) || 0,
        experience: radio('experience'), timeHorizon: radio('timeHorizon'), riskAppetite: radio('riskAppetite'),
        goals: goalsOut,
        goal: goalsOut.map(g => g.title + (g.amount ? ` (₹${g.amount.toLocaleString('en-IN')})` : '') + (g.year ? ` by ${g.year}` : '')).join('; ').slice(0, 300) || null,
        avoidSectors: [...form.querySelectorAll('input[name="avoid"]:checked')].map(x => x.value),
      };
      const btn = form.querySelector('button[type="submit"]');
      btn.disabled = true;
      try {
        const res = await fetch('/api/profile', {method: 'PUT', credentials: 'include',
          headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        const data = await res.json();
        if (!res.ok) throw data;
        ok.hidden = false;
        if (opts.onSaved) opts.onSaved(data.profile);
      } catch (x) {
        const names = {name: 'Name', portfolioValue: 'Money you could invest', age: 'Age', monthlyInvest: 'Added each month',
                       experience: 'Experience', timeHorizon: 'When you need the money', riskAppetite: 'Reaction to a fall'};
        err.textContent = (x.details || []).map(d => `${names[d.field.split('.')[0]] || d.field.split('.')[0]}: ${d.message}`).join('. ')
          || x.error || 'Could not save the profile.';
        err.hidden = false;
        (x.details || []).forEach(d => { const f = form.querySelector(`[name="${d.field}"]`); if (f) f.setAttribute('aria-invalid', 'true'); });
      } finally { btn.disabled = false; }
    });
  }

  async function mount(root, opts = {}) {
    let profile = {};
    try {
      const res = await fetch('/api/profile', {credentials: 'include'});
      if (res.status === 401) { location.href = 'login.html'; return; }
      profile = (await res.json()).profile || {};
    } catch (x) { /* render with defaults */ }
    render(root, profile, opts);
  }
  return {mount, AVOID};
})();
