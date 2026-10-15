import sys
import os
import hashlib
import secrets
import sqlite3
from functools import wraps

sys.path.append(os.path.dirname(__file__))
from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS

from legacy.orchestrator import Orchestrator
from agents.portfolio_analyzer import PortfolioAnalyzer

# ─────────────────────────────────────────────
#  PATHS
# ─────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
DB_PATH      = os.path.join(BASE_DIR, "users.db")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
app.secret_key = secrets.token_hex(32)
CORS(app, supports_credentials=True)

orc           = Orchestrator()
port_analyzer = PortfolioAnalyzer()


# ─────────────────────────────────────────────
#  SERVE FRONTEND PAGES
# ─────────────────────────────────────────────
@app.route("/")
def root():
    return send_from_directory(FRONTEND_DIR, "login.html")

@app.route("/login.html")
def login_page():
    return send_from_directory(FRONTEND_DIR, "login.html")

@app.route("/signup.html")
def signup_page():
    return send_from_directory(FRONTEND_DIR, "signup.html")

@app.route("/index.html")
def index_page():
    return send_from_directory(FRONTEND_DIR, "index.html")


# ─────────────────────────────────────────────
#  DATABASE INIT
# ─────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT    UNIQUE NOT NULL,
                pw    TEXT    NOT NULL
            )
        """)
        db.commit()


init_db()


# ─────────────────────────────────────────────
#  AUTH HELPERS
# ─────────────────────────────────────────────
def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_email" not in session:
            return jsonify({"error": "Not authenticated"}), 401
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────
#  AUTH ENDPOINTS
# ─────────────────────────────────────────────
@app.route("/signup", methods=["POST"])
def signup():
    data  = request.json or {}
    email = (data.get("email") or "").strip().lower()
    pw    = data.get("password") or ""
    if not email or not pw:
        return jsonify({"error": "Email and password required"}), 400
    try:
        with get_db() as db:
            db.execute("INSERT INTO users (email, pw) VALUES (?, ?)",
                       (email, hash_pw(pw)))
            db.commit()
        session["user_email"] = email
        return jsonify({"ok": True, "email": email})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already registered"}), 409


@app.route("/login", methods=["POST"])
def login():
    data  = request.json or {}
    email = (data.get("email") or "").strip().lower()
    pw    = data.get("password") or ""
    with get_db() as db:
        row = db.execute("SELECT pw FROM users WHERE email=?", (email,)).fetchone()
    if not row or row["pw"] != hash_pw(pw):
        return jsonify({"error": "Invalid email or password"}), 401
    session["user_email"] = email
    return jsonify({"ok": True, "email": email})


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/me", methods=["GET"])
def me():
    email = session.get("user_email")
    if not email:
        return jsonify({"loggedIn": False})
    return jsonify({"loggedIn": True, "email": email})


# ─────────────────────────────────────────────
#  STOCK ANALYSIS
# ─────────────────────────────────────────────
@app.route("/api/analyze", methods=["POST"])
#@login_required
def analyze():
    try:
        data   = request.json or {}
        ticker = data.get("ticker", "RELIANCE")
        user   = {
            "age":            data.get("age", 30),
            "experience":     data.get("experience", "Beginner"),
            "riskAppetite":   data.get("riskAppetite", "Moderate"),
            "portfolioValue": data.get("portfolioValue", 50000),
            "timeHorizon":    data.get("timeHorizon", "Medium-term"),
        }
        result = orc.analyze(ticker, user)
        return jsonify(result)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
#  PORTFOLIO UPLOAD & ANALYSIS
# ─────────────────────────────────────────────
@app.route("/upload_portfolio", methods=["POST"])
#@login_required
def upload_portfolio():
    try:
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "No file uploaded"}), 400
        filename = file.filename.lower()
        if not (filename.endswith(".csv") or filename.endswith(".xlsx")):
            return jsonify({"error": "Only CSV or XLSX files accepted"}), 400
        result = port_analyzer.analyze_portfolio(file, filename)
        return jsonify(result)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────────



@app.route("/api/health", methods=["GET"])
def health():
    return {
        "status": "ok"
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)