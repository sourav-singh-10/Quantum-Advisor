/* Sign-in and sign-up pages: email and password, "Keep me signed in", and Sign in with Google. */
(function () {
  const mode = document.body.dataset.auth;            // "login" or "signup"
  const $ = id => document.getElementById(id);
  const err = $('formError');
  const fail = msg => { err.textContent = msg; err.hidden = false; err.scrollIntoView({block: 'nearest'}); };
  const go = isNew => { location.href = isNew ? '/welcome.html' : '/app'; };
  const remember = () => $('remember').checked;

  fetch('/me', {credentials: 'include'}).then(r => r.json()).then(d => { if (d.loggedIn) location.href = '/app'; }).catch(() => {});

  /* show / hide password */
  document.querySelectorAll('[data-reveal]').forEach(b => b.addEventListener('click', () => {
    const input = $(b.dataset.reveal), show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    b.setAttribute('aria-pressed', String(show));
    b.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
  }));

  /* email and password */
  $('authForm').addEventListener('submit', async ev => {
    ev.preventDefault();
    err.hidden = true;
    const email = $('email').value.trim(), password = $('password').value;
    if (!email || !password) return fail('Enter your email and password.');
    if (mode === 'signup') {
      if (password.length < 6) return fail('Use at least 6 characters for the password.');
      if (password !== $('confirm').value) return fail('The two passwords are different.');
    }
    const btn = $('submitBtn'), label = btn.textContent;
    btn.disabled = true; btn.textContent = mode === 'signup' ? 'Creating your account…' : 'Signing in…';
    try {
      const res = await fetch(mode === 'signup' ? '/signup' : '/login', {method: 'POST', credentials: 'include',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({email, password, remember: remember()})});
      const data = await res.json();
      if (!res.ok) return fail(data.error || (mode === 'signup' ? 'Could not create the account.' : 'Sign-in failed.'));
      go(mode === 'signup');
    } catch (e) {
      fail('Could not reach the server. Check your connection and try again.');
    } finally { btn.disabled = false; btn.textContent = label; }
  });

  /* Sign in with Google: a popup from Google Identity Services; the server checks the token */
  const gBtn = $('googleBtn'), gNote = $('googleNote');
  let tokenClient = null, configured = null;
  const note = msg => { gNote.textContent = msg; gNote.hidden = !msg; };
  fetch('/api/auth/config').then(r => r.json()).then(cfg => {
    configured = !!cfg.googleClientId;
    if (!configured) return;
    const s = document.createElement('script');
    s.src = 'https://accounts.google.com/gsi/client'; s.async = true;
    s.onload = () => {
      tokenClient = google.accounts.oauth2.initTokenClient({
        client_id: cfg.googleClientId, scope: 'openid email profile',
        callback: resp => {
          if (resp.error) { gBtn.disabled = false; return note(resp.error === 'access_denied' ? 'Google sign-in was cancelled.' : 'Google sign-in did not finish. Try again.'); }
          signInWithGoogle(resp.access_token);
        },
        error_callback: () => { gBtn.disabled = false; note('The Google window was closed before sign-in finished.'); },
      });
    };
    s.onerror = () => note('Could not load Google sign-in. Check your connection, or use your email.');
    document.head.appendChild(s);
  }).catch(() => { configured = false; });

  gBtn.addEventListener('click', () => {
    err.hidden = true; note('');
    if (configured === false) return note('Google sign-in is not switched on for this server yet. Use your email for now.');
    if (!tokenClient) return note('Google sign-in is still loading. Try again in a moment.');
    gBtn.disabled = true;
    tokenClient.requestAccessToken({prompt: 'select_account'});
  });

  async function signInWithGoogle(accessToken) {
    try {
      const res = await fetch('/auth/google', {method: 'POST', credentials: 'include',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({accessToken, remember: remember()})});
      const data = await res.json();
      if (!res.ok) { gBtn.disabled = false; return fail(data.error || 'Google sign-in failed.'); }
      go(data.new);
    } catch (e) { gBtn.disabled = false; fail('Could not reach the server. Check your connection and try again.'); }
  }
})();
