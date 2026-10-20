"""Flask app: pages, auth, the analysis API (JSON and live stream), traces and portfolio upload."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import queue
import re
import secrets
import sys
import threading
import time
from datetime import timedelta
from functools import wraps

from flask import (Flask, Response, jsonify, request, send_from_directory, session,
                   stream_with_context)
from flask_cors import CORS
from pydantic import ValidationError
from werkzeug.security import check_password_hash, generate_password_hash

import config
from agents.portfolio_review_agent import PortfolioReviewAgent
from core import db as dbm
from core.context import RunContext
from core.memory import RunMemory
from core.runner import run_analysis
from core.schemas import AnalyzeRequest, InvestorProfile
from core.tracer import Tracer, load_run
from core.watch_store import MAX_WATCHLIST, WatchStore
from services import briefs as brief_service
from services import telegram
from services.notify import email_enabled, send_brief
from services.track_record import track_record
from tools.market_snapshot import _yf_year
from tools.market_data import RENAMED as RENAMED_SYMBOLS
from tools import symbols
from tools.market_snapshot import snapshot
from services.llm_service import LLMClient
from tools.base import ToolError
from tools.document_data import load_pdf
from tools.portfolio_analyzer import PortfolioAnalyzer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("quantum-advisor")

FRONTEND_DIR = str(config.BASE_DIR / "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
if config.SECRET_KEY:
    app.secret_key = config.SECRET_KEY
else:
    app.secret_key = secrets.token_hex(32)
    log.warning("SECRET_KEY not set: sessions will reset when the server restarts")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024   # company PDFs up to 15 MB
app.permanent_session_lifetime = timedelta(days=30)    # "Remember me": stay signed in for 30 days
app.config.update(SESSION_COOKIE_HTTPONLY=True,          # scripts on the page cannot read the session
                  SESSION_COOKIE_SAMESITE="Lax",         # not sent on cross-site form posts
                  SESSION_COOKIE_SECURE=config.SECURE_COOKIES)
CORS(app, supports_credentials=True)


# ------------------------------------------------------------------ database
def get_db():
    return dbm.connect()


def init_db():
    with get_db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS users (
                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                          email TEXT UNIQUE NOT NULL,
                          pw TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS profiles (
                          email TEXT PRIMARY KEY,
                          data TEXT NOT NULL)""")


init_db()


def memory() -> RunMemory:
    return RunMemory()


# ------------------------------------------------------------------ auth
def _legacy_hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def verify_password(stored: str, pw: str) -> bool:
    if stored.startswith("google:"):        # created with Google: only Google can sign it in
        return False
    if stored.startswith(("scrypt:", "pbkdf2:")):
        return check_password_hash(stored, pw)
    return secrets.compare_digest(stored, _legacy_hash(pw))  # accounts created before the fix


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if config.REQUIRE_LOGIN and "user_email" not in session:
            return jsonify({"error": "Not authenticated"}), 401
        return f(*args, **kwargs)
    return wrapper


def current_user() -> str:
    return session.get("user_email", "anonymous")


def start_session(email: str, remember: bool = True) -> None:
    """Sign the user in. With remember, the cookie lasts 30 days; without, it ends with the browser."""
    session["user_email"] = email
    session.permanent = bool(remember)


@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    pw = data.get("password") or ""
    if "@" not in email or len(pw) < 6:
        return jsonify({"error": "Valid email and a password of at least 6 characters required"}), 400
    try:
        with get_db() as db:
            db.execute("INSERT INTO users (email, pw) VALUES (?, ?)",
                       (email, generate_password_hash(pw)))
    except dbm.IntegrityError:
        return jsonify({"error": "Email already registered"}), 409
    start_session(email, data.get("remember", True))
    return jsonify({"ok": True, "email": email})


_login_failures: dict[tuple[str, str], list[float]] = {}
_login_lock = threading.Lock()


def _recent_failures(key: tuple[str, str]) -> list[float]:
    """Failed sign-ins for this email from this address within the lockout window."""
    cutoff = time.time() - config.LOGIN_LOCKOUT_MINUTES * 60
    with _login_lock:
        recent = [t for t in _login_failures.get(key, []) if t > cutoff]
        _login_failures[key] = recent
        return recent


def _note_failure(key: tuple[str, str]) -> None:
    with _login_lock:
        _login_failures.setdefault(key, []).append(time.time())


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    pw = data.get("password") or ""
    key = (email, request.remote_addr or "")
    failures = _recent_failures(key)
    if len(failures) >= config.LOGIN_MAX_FAILURES:
        wait = max(1, round((failures[0] + config.LOGIN_LOCKOUT_MINUTES * 60 - time.time()) / 60))
        return jsonify({"error": f"Too many failed attempts. Try again in {wait} minute{'s' if wait != 1 else ''}."}), 429
    with get_db() as db:
        row = db.execute("SELECT pw FROM users WHERE email=?", (email,)).fetchone()
        if row and row["pw"].startswith(GOOGLE_MARK):
            return jsonify({"error": "This account uses Google. Choose \u201cContinue with Google\u201d."}), 401
        if not row or not verify_password(row["pw"], pw):
            _note_failure(key)
            return jsonify({"error": "Invalid email or password"}), 401
        if not row["pw"].startswith(("scrypt:", "pbkdf2:")):
            db.execute("UPDATE users SET pw=? WHERE email=?", (generate_password_hash(pw), email))
    with _login_lock:
        _login_failures.pop(key, None)
    start_session(email, data.get("remember", True))
    return jsonify({"ok": True, "email": email})


GOOGLE_MARK = "google:"     # password field of accounts created with Google: no password login


def verify_google_token(token: str) -> dict:
    """Check a Google ID token (signature, audience, expiry). Raises ValueError if invalid."""
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token
    return id_token.verify_oauth2_token(token, google_requests.Request(), config.GOOGLE_CLIENT_ID)


def verify_google_access_token(token: str) -> dict:
    """Check an access token from Google's sign-in popup: it must be live, issued to this app's
    client ID, and carry a verified email. Returns {email, email_verified, given_name}."""
    import requests
    res = requests.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": token}, timeout=8)
    if res.status_code != 200:
        raise ValueError("token rejected by Google")
    info = res.json()
    if config.GOOGLE_CLIENT_ID not in (info.get("aud"), info.get("azp")):
        raise ValueError("token was issued to another app")
    if int(info.get("expires_in") or 0) <= 0:
        raise ValueError("token expired")
    out = {"email": info.get("email"), "email_verified": str(info.get("email_verified")).lower() == "true"}
    try:   # the first name, for the greeting; optional
        who = requests.get("https://openidconnect.googleapis.com/v1/userinfo",
                           headers={"Authorization": f"Bearer {token}"}, timeout=8)
        if who.ok:
            out["given_name"] = who.json().get("given_name")
    except Exception:
        pass
    return out


@app.route("/api/auth/config")
def auth_config():
    return jsonify({"googleClientId": config.GOOGLE_CLIENT_ID or None})


@app.route("/auth/google", methods=["POST"])
def google_sign_in():
    if not config.GOOGLE_CLIENT_ID:
        return jsonify({"error": "Google sign-in is not set up on this server"}), 400
    body = request.get_json(silent=True) or {}
    try:
        if body.get("accessToken"):          # our own "Continue with Google" button (popup)
            info = verify_google_access_token(body["accessToken"])
        else:                                # Google's ID-token button or One Tap
            info = verify_google_token(body.get("credential") or "")
    except Exception:
        return jsonify({"error": "Google could not confirm this sign-in. Try again."}), 401
    email = (info.get("email") or "").strip().lower()
    if not email or not info.get("email_verified", False):
        return jsonify({"error": "Your Google account has no verified email"}), 401
    created = False
    with get_db() as db:
        row = db.execute("SELECT pw FROM users WHERE email=?", (email,)).fetchone()
        if not row:
            db.execute("INSERT INTO users (email, pw) VALUES (?, ?)",
                       (email, GOOGLE_MARK + generate_password_hash(secrets.token_hex(16))))
            created = True
    start_session(email, body.get("remember", True))
    if created and info.get("given_name"):
        with get_db() as db:             # start the profile with their first name for the greeting
            db.execute("INSERT OR IGNORE INTO profiles VALUES (?, ?)",
                       (email, json.dumps({**InvestorProfile().model_dump(), "name": info["given_name"][:40]})))
    return jsonify({"ok": True, "email": email, "new": created})


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/me")
def me():
    email = session.get("user_email")
    method = None
    if email:
        with get_db() as db:
            row = db.execute("SELECT pw FROM users WHERE email=?", (email,)).fetchone()
        method = "google" if row and row["pw"].startswith(GOOGLE_MARK) else "password"
    return jsonify({"loggedIn": bool(email), "email": email, "authMethod": method,
                    "loginRequired": config.REQUIRE_LOGIN})


# ------------------------------------------------------------------ pages
@app.route("/")
@app.route("/home.html")
def home_page():
    return send_from_directory(FRONTEND_DIR, "home.html")


@app.route("/login.html")
def login_page():
    return send_from_directory(FRONTEND_DIR, "login.html")


@app.route("/signup.html")
def signup_page():
    return send_from_directory(FRONTEND_DIR, "signup.html")


@app.route("/app")
@app.route("/index.html")
def index_page():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.errorhandler(404)
def not_found(_):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(FRONTEND_DIR, "404.html"), 404


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "Invalid input", "details": [
        {"field": "document", "message": "The file is larger than 15 MB"}]}), 413


# ------------------------------------------------------------------ account
@app.route("/api/profile", methods=["GET"])
@login_required
def get_profile():
    with get_db() as db:
        row = db.execute("SELECT data FROM profiles WHERE email=?", (current_user(),)).fetchone()
    saved = json.loads(row["data"]) if row else None
    return jsonify({"saved": saved is not None,
                    "profile": InvestorProfile.model_validate(saved or {}).model_dump()})


@app.route("/api/profile", methods=["PUT"])
@login_required
def put_profile():
    try:
        profile = InvestorProfile.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        details = [{"field": ".".join(str(p) for p in e["loc"]) or "body",
                    "message": e["msg"].removeprefix("Value error, ")} for e in exc.errors()]
        return jsonify({"error": "Invalid profile", "details": details}), 400
    with get_db() as db:
        db.execute("INSERT OR REPLACE INTO profiles VALUES (?, ?)",
                   (current_user(), json.dumps(profile.model_dump())))
    return jsonify({"saved": True, "profile": profile.model_dump()})


@app.route("/api/account/password", methods=["POST"])
@login_required
def change_password():
    if "user_email" not in session:
        return jsonify({"error": "Sign in to change your password"}), 401
    data = request.get_json(silent=True) or {}
    current, new = data.get("current") or "", data.get("new") or ""
    if len(new) < 6:
        return jsonify({"error": "The new password needs at least 6 characters"}), 400
    with get_db() as db:
        row = db.execute("SELECT pw FROM users WHERE email=?", (session["user_email"],)).fetchone()
        google_only = bool(row) and row["pw"].startswith(GOOGLE_MARK)
        if not row or (not google_only and not verify_password(row["pw"], current)):
            return jsonify({"error": "Your current password is not correct"}), 403
        db.execute("UPDATE users SET pw=? WHERE email=?",
                   (generate_password_hash(new), session["user_email"]))
    return jsonify({"ok": True})


# ------------------------------------------------------------------ analysis
def _parse_request():
    """JSON body, or a multipart form (fields + optional 'document' PDF)."""
    if request.files or request.form:
        body = {k: v for k, v in request.form.items() if v != ""}
    else:
        body = request.get_json(silent=True) or {}
    try:
        return AnalyzeRequest.model_validate(body).model_dump(), None
    except ValidationError as exc:
        details = [{"field": ".".join(str(p) for p in e["loc"]) or "body",
                    "message": e["msg"].removeprefix("Value error, ")} for e in exc.errors()]
        return None, (jsonify({"error": "Invalid input", "details": details}), 400)


FAULT_RE = re.compile(r"^(tool:[a-z_]+(:[A-Za-z0-9_.-]+)?|agent:[A-Za-z]+)$")


def _faults() -> frozenset:
    """Simulated failures requested by the evaluation script (only when EVAL_FAULTS is on)."""
    if not config.EVAL_FAULTS:
        return frozenset()
    raw = request.headers.get("X-Eval-Fault", "")
    return frozenset(f.strip() for f in raw.split(",") if FAULT_RE.match(f.strip()))


def _mark_holding(req: dict) -> None:
    """Whether the investor already owns this stock (from saved holdings, unless the client said)."""
    if req.get("holding") is None:
        try:
            req["holding"] = any(h["ticker"] == req["ticker"] for h in watch_store().holdings(current_user()))
        except Exception:      # holdings are a convenience; never block an analysis on them
            req["holding"] = False


def _read_document():
    """(document, error_response). No file attached is fine: (None, None)."""
    f = request.files.get("document")
    if not f or not f.filename:
        return None, None
    if not f.filename.lower().endswith(".pdf"):
        return None, (jsonify({"error": "Invalid input", "details": [
            {"field": "document", "message": "Attach the company document as a PDF"}]}), 400)
    try:
        return load_pdf(f.read(), name=os.path.basename(f.filename)[:120]), None
    except ToolError as exc:
        return None, (jsonify({"error": "Invalid input", "details": [
            {"field": "document", "message": f"Could not use this PDF: {exc}"}]}), 400)


def _precheck_symbol(ticker: str):
    """A 400 with suggestions when no source has prices for this symbol, else None."""
    if not config.SYMBOL_PRECHECK or symbols.name_for(ticker) or ticker in RENAMED_SYMBOLS:
        return None
    try:
        snapshot(ticker)
        return None
    except ToolError:
        pass
    hints = symbols.close_matches(ticker) or symbols.live_search(ticker)
    hint = (" Did you mean " + ", ".join(f"{h['symbol']} ({h['name']})" for h in hints[:3]) + "?") if hints else \
           " Use the NSE symbol, for example RELIANCE or TCS."
    return jsonify({"error": f"No NSE prices were found for {ticker}.{hint}",
                    "details": [{"field": "ticker", "message": "unknown NSE symbol"}],
                    "suggestions": hints[:3]}), 400


@app.route("/api/analyze", methods=["POST"])
@login_required
def analyze():
    req, err = _parse_request()
    if err:
        return err
    err = _precheck_symbol(req["ticker"])
    if err:
        return err
    _mark_holding(req)
    doc, err = _read_document()
    if err:
        return err
    try:
        result = run_analysis(req, user_key=current_user(), memory=memory(), document=doc,
                              faults=_faults())
    except Exception:
        log.exception("analysis crashed")
        return jsonify({"error": "Internal error while running the agents"}), 500
    return jsonify(result), (502 if result.get("error") else 200)


@app.route("/api/analyze/stream", methods=["POST"])
@login_required
def analyze_stream():
    """Server-Sent Events: one `trace` event per agent message, then one `result` event."""
    req, err = _parse_request()
    if err:
        return err
    err = _precheck_symbol(req["ticker"])
    if err:
        return err
    _mark_holding(req)
    doc, err = _read_document()
    if err:
        return err
    user = current_user()
    faults = _faults()
    events: queue.Queue = queue.Queue()
    tracer = Tracer()
    tracer.subscribe(lambda e: events.put(("trace", e)))

    def worker():
        try:
            out = run_analysis(req, user_key=user, tracer=tracer, memory=memory(), document=doc,
                               faults=faults)
            out.pop("trace", None)
            events.put(("result", out))
        except Exception:
            log.exception("analysis crashed")
            events.put(("result", {"error": "Internal error while running the agents",
                                   "meta": {"runId": tracer.run_id}}))
        events.put(("end", None))

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        yield f"event: start\ndata: {json.dumps({'runId': tracer.run_id})}\n\n"
        while True:
            try:
                kind, payload = events.get(timeout=15)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if kind == "end":
                break
            yield f"event: {kind}\ndata: {json.dumps(payload, default=str)}\n\n"

    return Response(stream_with_context(stream()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/runs/<run_id>/trace")
def run_trace(run_id):
    try:
        return jsonify({"runId": run_id, "events": load_run(run_id)})
    except (ValueError, FileNotFoundError):
        return jsonify({"error": "Unknown run id"}), 404


@app.route("/api/history")
@login_required
def history():
    return jsonify({"runs": memory().recent(current_user())})


# ------------------------------------------------------------------ portfolio upload
def _json_safe(o):
    """Replace NaN/infinity (invalid in JSON) with null, recursively."""
    if isinstance(o, float):
        return o if o == o and o not in (float("inf"), float("-inf")) else None
    if isinstance(o, dict):
        return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_safe(v) for v in o]
    return o


def _review_portfolio(file, filename: str):
    """Price holdings live and ask the Portfolio Review agent. Returns (body, status)."""
    llm, tracer = LLMClient(), Tracer()
    ctx = RunContext(llm=llm, tracer=tracer, user_key=current_user())
    agent = PortfolioReviewAgent.name
    ctx.emit("User", agent, "request", {"file": filename})

    def on_quote(ticker, quote, error):
        ctx.emit(agent, "tool:live_quote", "tool_call", {"argument": ticker})
        if quote:
            ctx.emit("tool:live_quote", agent, "tool_result",
                     {"ok": True, "summary": f"{ticker} {quote['price']} via {quote['source']}, "
                                             f"daily vol {quote['volatility']}%"})
        else:
            ctx.emit("tool:live_quote", agent, "tool_result", {"ok": False, "error": error})

    try:
        analysis = PortfolioAnalyzer(on_quote=on_quote).analyze_portfolio(file, filename.lower())
    except Exception as exc:
        log.exception("portfolio analysis failed")
        return {"error": f"Could not read this file: {exc}"}, 400
    try:
        review = PortfolioReviewAgent().run(ctx, analysis)
    except Exception:
        log.exception("portfolio review crashed")
        review = None
    ctx.emit(agent, "User", "final", {"status": "ok" if review else "degraded"})
    return _json_safe({**analysis, "review": review,
                       "meta": {"runId": tracer.run_id, "llmAvailable": llm.available,
                                "llmCalls": llm.stats.calls, "llmFailures": llm.stats.failures},
                       "trace": tracer.events}), 200


@app.route("/upload_portfolio", methods=["POST"])
@login_required
def upload_portfolio():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No file uploaded"}), 400
    filename = file.filename.lower()
    if not filename.endswith((".csv", ".xlsx")):
        return jsonify({"error": "Only CSV or XLSX files accepted"}), 400
    data = file.read()
    body, status = _review_portfolio(io.BytesIO(data), filename)
    if status == 200 and request.form.get("save") == "1":
        # keep the holdings for the 3:15 brief and the Today screen
        rows = [{"ticker": s_["ticker"], "quantity": s_["quantity"], "buy_price": s_["buyPrice"]}
                for s_ in body["stocks"]]
        body["saved"] = watch_store().replace_holdings(current_user(), rows)
    return jsonify(body), status


@app.route("/api/holdings/review", methods=["POST"])
@login_required
def review_saved_holdings():
    held = watch_store().holdings(current_user())
    if not held:
        return jsonify({"error": "Upload your holdings first."}), 400
    csv_text = "ticker,quantity,buy_price\n" + "".join(
        f"{h['ticker']},{h['quantity']:g},{h['buy_price']}\n" for h in held)
    body, status = _review_portfolio(io.BytesIO(csv_text.encode()), "saved_holdings.csv")
    return jsonify(body), status


# ------------------------------------------------------------------ watchlist, holdings, briefs
TICKER_RE = re.compile(r"^[A-Z0-9&\-]{1,20}$")
_refresh_at: dict[tuple, float] = {}


def watch_store() -> WatchStore:
    return WatchStore()


def _notify(user: str, brief: dict) -> None:
    store = watch_store()
    if email_enabled() and store.email_briefs(user):
        send_brief(user, brief)
    chat = store.telegram_chat(user)
    if chat:
        telegram.send(chat, telegram.brief_text(brief))


def _on_alert(user: str, alert: dict) -> None:
    chat = watch_store().telegram_chat(user)
    if chat:
        telegram.send(chat, telegram.alert_text(alert))


def _profile(user: str) -> dict | None:
    with get_db() as db:
        row = db.execute("SELECT data FROM profiles WHERE email=?", (user,)).fetchone()
    return json.loads(row["data"]) if row else None


@app.route("/api/symbols")
@login_required
def symbol_search():
    q = (request.args.get("q") or "").strip()[:40]
    return jsonify({"results": symbols.suggest(q) if q else []})


@app.route("/api/watchlist", methods=["GET"])
@login_required
def get_watchlist():
    return jsonify({"items": watch_store().watchlist(current_user()), "max": MAX_WATCHLIST})


@app.route("/api/watchlist", methods=["POST"])
@login_required
def add_watchlist():
    body = request.get_json(silent=True) or {}
    raw = str(body.get("ticker") or "").strip().upper()
    raw = symbols.ALIASES.get(raw, raw.removesuffix(".NS"))
    snap = None
    if TICKER_RE.match(raw):
        try:
            snap = snapshot(raw)
        except ToolError:
            pass
    if snap is None:                          # maybe a company name, e.g. "Infosys"
        hits = symbols.search(raw, 1)
        if hits and hits[0]["symbol"] != raw:
            try:
                snap = snapshot(hits[0]["symbol"])
            except ToolError:
                pass
    if snap is None:
        return jsonify({"error": f"No NSE prices were found for {raw[:30]}. Pick a company from the suggestions."}), 400
    ticker = snap["ticker"]
    name = body.get("name") or symbols.name_for(ticker)
    if not watch_store().add_watch(current_user(), ticker, name):
        return jsonify({"error": f"Your watchlist is full ({MAX_WATCHLIST} stocks). Remove one first."}), 400
    return jsonify({"items": watch_store().watchlist(current_user()), "added": ticker})


@app.route("/api/watchlist/<ticker>", methods=["DELETE"])
@login_required
def remove_watchlist(ticker):
    watch_store().remove_watch(current_user(), ticker.upper())
    return jsonify({"items": watch_store().watchlist(current_user())})


@app.route("/api/holdings", methods=["GET"])
@login_required
def get_holdings():
    return jsonify({"items": watch_store().holdings(current_user())})


@app.route("/api/holdings", methods=["POST"])
@login_required
def save_holdings():
    file = request.files.get("file")
    if not file or not file.filename.lower().endswith((".csv", ".xlsx")):
        return jsonify({"error": "Choose a .csv or .xlsx file of your holdings."}), 400
    analyzer = PortfolioAnalyzer()
    try:
        rows = analyzer._parse(file, file.filename.lower())
    except Exception as exc:
        return jsonify({"error": f"Could not read this file: {exc}"}), 400
    if not rows:
        return jsonify({"error": "No holdings found. Use columns ticker, quantity, buy_price, "
                                 "or a Zerodha holdings export."}), 400
    n = watch_store().replace_holdings(current_user(), rows)
    return jsonify({"items": watch_store().holdings(current_user()), "saved": n,
                    "skippedRows": list(getattr(analyzer, "skipped", []))})


@app.route("/api/holdings", methods=["DELETE"])
@login_required
def clear_holdings():
    watch_store().clear_holdings(current_user())
    return jsonify({"items": []})


def _briefs_payload(store: WatchStore, user: str) -> dict:
    alerts = store.alerts(user)
    now = brief_service.now_ist()
    return {"morning": store.latest_brief(user, "morning"), "closing": store.latest_brief(user, "closing"),
            "alerts": alerts, "unseen": sum(1 for a in alerts if not a["seen"]),
            "watchlist": store.watchlist(user), "holdings": store.holdings(user),
            "emailAvailable": email_enabled(), "emailOn": store.email_briefs(user),
            "today": now.date().isoformat(), "nowIst": now.strftime("%a %d %b, %I:%M %p")}


@app.route("/api/briefs")
@login_required
def get_briefs():
    store, user = watch_store(), current_user()
    for kind in brief_service.due_for_user(store, user):      # the server slept through the time
        (brief_service.build_morning if kind == "morning" else brief_service.build_closing)(store, user)
    return jsonify(_json_safe(_briefs_payload(store, user)))


@app.route("/api/briefs/<kind>/refresh", methods=["POST"])
@login_required
def refresh_brief(kind):
    if kind not in ("morning", "closing"):
        return jsonify({"error": "Unknown brief"}), 404
    store, user = watch_store(), current_user()
    key = (user, kind)
    if time.time() - _refresh_at.get(key, 0) < 60:
        return jsonify({"error": "This brief was just refreshed. Try again in a minute."}), 429
    _refresh_at[key] = time.time()
    build = brief_service.build_morning if kind == "morning" else brief_service.build_closing
    brief = build(store, user)
    if brief is None:
        need = "Add stocks to your watchlist" if kind == "morning" else "Upload your holdings"
        return jsonify({"error": f"{need} first."}), 400
    _notify(user, brief)          # email it too when the user has email turned on
    return jsonify(_json_safe(_briefs_payload(store, user)))


@app.route("/api/alerts/unseen")
@login_required
def alerts_unseen():
    return jsonify({"unseen": sum(1 for a in watch_store().alerts(current_user()) if not a["seen"])})


@app.route("/api/alerts/seen", methods=["POST"])
@login_required
def alerts_seen():
    watch_store().mark_seen(current_user())
    return jsonify({"ok": True})


@app.route("/api/briefs/settings", methods=["PUT"])
@login_required
def brief_settings():
    body = request.get_json(silent=True) or {}
    watch_store().set_email_briefs(current_user(), bool(body.get("email")))
    return jsonify({"emailOn": watch_store().email_briefs(current_user()), "emailAvailable": email_enabled()})


@app.route("/api/cron/tick", methods=["GET", "POST"])
def cron_tick():
    """Called by a free external scheduler (GitHub Actions) so a sleeping server still
    sends the 8:30 and 3:15 briefs. Needs CRON_SECRET."""
    key = request.headers.get("X-Cron-Key") or request.args.get("key", "")
    if not config.CRON_SECRET or not secrets.compare_digest(key, config.CRON_SECRET):
        return jsonify({"error": "Forbidden"}), 403
    # Answer at once and work in the background, so the caller's timeout never matters.
    def work():
        telegram.poll_updates(watch_store())
        brief_service.run_due(watch_store(), notify=_notify, on_alert=_on_alert)
    threading.Thread(target=work, daemon=True).start()
    return jsonify({"started": True, "nowIst": brief_service.now_ist().isoformat(timespec="minutes")}), 202


scheduler = brief_service.Scheduler(notify=_notify, on_alert=_on_alert,
                                    every_minute=lambda: telegram.poll_updates(watch_store()))
if "pytest" not in sys.modules:
    scheduler.start()


# ------------------------------------------------------------------ price alerts, Telegram, track record, Today
@app.route("/api/price-alerts", methods=["GET"])
@login_required
def list_price_alerts():
    return jsonify({"items": watch_store().price_alerts(current_user())})


@app.route("/api/price-alerts", methods=["POST"])
@login_required
def add_price_alert():
    body = request.get_json(silent=True) or {}
    ticker = str(body.get("ticker") or "").strip().upper()
    direction = body.get("direction")
    try:
        price = float(body.get("price"))
    except (TypeError, ValueError):
        price = 0.0
    if not TICKER_RE.match(ticker) or direction not in ("above", "below") or not 0 < price < 1e7:
        return jsonify({"error": "Choose a stock, 'above' or 'below', and a price."}), 400
    try:
        now_price = snapshot(ticker)["price"]
    except ToolError:
        return jsonify({"error": f"No NSE prices were found for {ticker}."}), 400
    if (direction == "below" and price >= now_price) or (direction == "above" and price <= now_price):
        side = "below" if direction == "below" else "above"
        return jsonify({"error": f"{ticker} is at ₹{now_price:,.2f} now. Pick a level {side} that."}), 400
    if watch_store().add_price_alert(current_user(), ticker, direction, round(price, 2)) is None:
        return jsonify({"error": "You have 20 active price alerts. Remove one first."}), 400
    return jsonify({"items": watch_store().price_alerts(current_user()), "nowPrice": now_price})


@app.route("/api/price-alerts/<int:alert_id>", methods=["DELETE"])
@login_required
def delete_price_alert(alert_id):
    watch_store().delete_price_alert(current_user(), alert_id)
    return jsonify({"items": watch_store().price_alerts(current_user())})


@app.route("/api/telegram", methods=["GET"])
@login_required
def telegram_status():
    store = watch_store()
    if telegram.enabled() and not store.telegram_chat(current_user()):
        telegram.poll_updates(store)            # the user may have just pressed Start
    return jsonify({"available": telegram.enabled(), "linked": bool(store.telegram_chat(current_user()))})


@app.route("/api/telegram/link", methods=["POST"])
@login_required
def telegram_link():
    if not telegram.enabled():
        return jsonify({"error": "Telegram is not set up on this server."}), 400
    return jsonify(telegram.new_link(watch_store(), current_user()))


@app.route("/api/telegram", methods=["DELETE"])
@login_required
def telegram_unlink():
    watch_store().unlink_telegram(current_user())
    return jsonify({"linked": False})


@app.route("/api/track-record")
@login_required
def get_track_record():
    runs = memory().recent(current_user(), limit=60)
    return jsonify(_json_safe(track_record(runs, _yf_year)))


def _greeting(hour: int) -> str:
    return "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"


def _market_status(now) -> str:
    if now.weekday() >= 5:
        return "Market closed for the weekend"
    t = now.time()
    if t < brief_service.time(9, 15):
        return "Market opens at 9:15"
    if t <= brief_service.time(15, 30):
        return "Market open until 3:30"
    return "Market closed for the day"


@app.route("/api/today")
@login_required
def today():
    """Everything the Today screen shows that needs no live prices (fast)."""
    store, user = watch_store(), current_user()
    for kind in brief_service.due_for_user(store, user):
        (brief_service.build_morning if kind == "morning" else brief_service.build_closing)(store, user)
    profile = _profile(user)
    now = brief_service.now_ist()
    goals = []
    for g in (profile or {}).get("goals") or []:
        goals.append({**g, "yearsLeft": (g["year"] - now.year) if g.get("year") else None})
    alerts = store.alerts(user, limit=8)
    morning, closing = store.latest_brief(user, "morning"), store.latest_brief(user, "closing")
    slim = lambda b: b and {"day": b["day"], "kind": b["kind"], "summary": b["summary"],
                            "generatedIst": b.get("generatedIst"), "totals": b.get("totals")}
    return jsonify(_json_safe({
        "greeting": _greeting(now.hour), "name": (profile or {}).get("name"),
        "hasProfile": profile is not None, "marketStatus": _market_status(now),
        "dateText": now.strftime("%A, %d %B"), "today": now.date().isoformat(),
        "morning": slim(morning), "closing": slim(closing),
        "alerts": alerts, "unseen": sum(1 for a in alerts if not a["seen"]),
        "watchCount": len(store.watchlist(user)), "holdingsCount": len(store.holdings(user)),
        "recent": memory().recent(user, limit=6), "goals": goals,
        "priceAlerts": [a for a in store.price_alerts(user) if not a["triggered_at"]][:5],
    }))


@app.route("/api/today/live")
@login_required
def today_live():
    """Live numbers for the Today screen: holdings today and watchlist movers (slower)."""
    store, user = watch_store(), current_user()
    held, watch = store.holdings(user), store.watchlist(user)
    tickers = list(dict.fromkeys([h["ticker"] for h in held] + [w["ticker"] for w in watch]))

    def snap(t):
        try:
            return t, snapshot(t)
        except ToolError:
            return t, None
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as pool:
        snaps = dict(pool.map(snap, tickers))
    value = prev = cost = 0.0
    rows = []
    for h in held:
        s_ = snaps.get(h["ticker"])
        if not s_:
            continue
        value += h["quantity"] * s_["price"]
        prev += h["quantity"] * s_["prevClose"]
        cost += h["quantity"] * h["buy_price"]
        rows.append({"ticker": s_["ticker"], "changePct": s_["changePct"],
                     "dayPnL": round(h["quantity"] * (s_["price"] - s_["prevClose"]), 2)})
    holdings = None
    if held:
        holdings = {"value": round(value, 2), "dayPnL": round(value - prev, 2),
                    "dayPnLPct": round((value / prev - 1) * 100, 2) if prev else 0.0,
                    "totalPnLPct": round((value / cost - 1) * 100, 2) if cost else 0.0,
                    "priced": len(rows), "count": len(held),
                    "movers": sorted(rows, key=lambda r: -abs(r["changePct"] or 0))[:3],
                    "asOf": max((snaps[h["ticker"]]["asOf"] or "" for h in held if snaps.get(h["ticker"])), default=None)}
    movers = [{"ticker": s_["ticker"], "name": w.get("name"), "price": s_["price"], "changePct": s_["changePct"],
               "history": s_["history"][-20:]}
              for w in watch if (s_ := snaps.get(w["ticker"]))]
    movers.sort(key=lambda m: -abs(m["changePct"] or 0))
    return jsonify(_json_safe({"holdings": holdings, "watch": movers[:6]}))



SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",                 # files are only used as the type they are served as
    "X-Frame-Options": "DENY",                           # the app cannot be framed by another site
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@app.after_request
def no_stale_pages(resp):
    """Pages and scripts are revalidated on every load, so an update shows without Ctrl+F5;
    every response carries the basic security headers."""
    if request.path in ("/", "/app") or request.path.endswith((".html", ".js", ".css")):
        resp.headers["Cache-Control"] = "no-cache"
    for k, v in SECURITY_HEADERS.items():
        resp.headers.setdefault(k, v)
    return resp


# ------------------------------------------------------------------ health
@app.route("/api/health")
def health():
    body = {"status": "ok", "llmConfigured": bool(config.GEMINI_API_KEY),
            "dataKeys": {"marketstack": bool(config.MARKETSTACK_API_KEY),
                         "alphavantage": bool(config.ALPHAVANTAGE_API_KEY),
                         "newsapi": bool(config.NEWS_API_KEY)}}
    if request.args.get("deep") == "1":
        body["llm"] = LLMClient().ping()
    return jsonify(body)


if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
