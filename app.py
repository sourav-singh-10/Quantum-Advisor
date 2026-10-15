"""Flask app: pages, auth, the analysis API (JSON and live stream), traces and portfolio upload."""
from __future__ import annotations

import hashlib
import json
import logging
import queue
import secrets
import sqlite3
import threading
from functools import wraps

from flask import (Flask, Response, jsonify, request, send_from_directory, session,
                   stream_with_context)
from flask_cors import CORS
from pydantic import ValidationError
from werkzeug.security import check_password_hash, generate_password_hash

import config
from core.memory import RunMemory
from core.runner import run_analysis
from core.schemas import AnalyzeRequest
from core.tracer import Tracer, load_run
from services.llm_service import LLMClient
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
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
CORS(app, supports_credentials=True)

port_analyzer = PortfolioAnalyzer()


# ------------------------------------------------------------------ database
def get_db():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS users (
                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                          email TEXT UNIQUE NOT NULL,
                          pw TEXT NOT NULL)""")


init_db()


def memory() -> RunMemory:
    return RunMemory(config.DB_PATH)


# ------------------------------------------------------------------ auth
def _legacy_hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def verify_password(stored: str, pw: str) -> bool:
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
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already registered"}), 409
    session["user_email"] = email
    return jsonify({"ok": True, "email": email})


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    pw = data.get("password") or ""
    with get_db() as db:
        row = db.execute("SELECT pw FROM users WHERE email=?", (email,)).fetchone()
        if not row or not verify_password(row["pw"], pw):
            return jsonify({"error": "Invalid email or password"}), 401
        if not row["pw"].startswith(("scrypt:", "pbkdf2:")):
            db.execute("UPDATE users SET pw=? WHERE email=?", (generate_password_hash(pw), email))
    session["user_email"] = email
    return jsonify({"ok": True, "email": email})


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/me")
def me():
    email = session.get("user_email")
    return jsonify({"loggedIn": bool(email), "email": email,
                    "loginRequired": config.REQUIRE_LOGIN})


# ------------------------------------------------------------------ pages
@app.route("/")
@app.route("/login.html")
def login_page():
    return send_from_directory(FRONTEND_DIR, "login.html")


@app.route("/signup.html")
def signup_page():
    return send_from_directory(FRONTEND_DIR, "signup.html")


@app.route("/index.html")
def index_page():
    return send_from_directory(FRONTEND_DIR, "index.html")


# ------------------------------------------------------------------ analysis
def _parse_request():
    try:
        return AnalyzeRequest.model_validate(request.get_json(silent=True) or {}).model_dump(), None
    except ValidationError as exc:
        details = [{"field": ".".join(str(p) for p in e["loc"]) or "body",
                    "message": e["msg"].removeprefix("Value error, ")} for e in exc.errors()]
        return None, (jsonify({"error": "Invalid input", "details": details}), 400)


@app.route("/api/analyze", methods=["POST"])
@login_required
def analyze():
    req, err = _parse_request()
    if err:
        return err
    try:
        result = run_analysis(req, user_key=current_user(), memory=memory())
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
    user = current_user()
    events: queue.Queue = queue.Queue()
    tracer = Tracer()
    tracer.subscribe(lambda e: events.put(("trace", e)))

    def worker():
        try:
            out = run_analysis(req, user_key=user, tracer=tracer, memory=memory())
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
@app.route("/upload_portfolio", methods=["POST"])
@login_required
def upload_portfolio():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No file uploaded"}), 400
    filename = file.filename.lower()
    if not filename.endswith((".csv", ".xlsx")):
        return jsonify({"error": "Only CSV or XLSX files accepted"}), 400
    try:
        return jsonify(port_analyzer.analyze_portfolio(file, filename))
    except Exception as exc:
        log.exception("portfolio analysis failed")
        return jsonify({"error": f"Could not read this file: {exc}"}), 400


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
