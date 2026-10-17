"""Central configuration. Every value comes from the environment (see .env.example)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Data providers
MARKETSTACK_API_KEY = os.getenv("MARKETSTACK_API_KEY", "")
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# LLM
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Fast model for the analyst agents, stronger model for Strategy / Risk / Planner.
# Set these to model ids listed in your Google AI Studio account.
GEMINI_FAST_MODEL = os.getenv("GEMINI_FAST_MODEL", "gemini-3.5-flash-lite")
GEMINI_REASONING_MODEL = os.getenv("GEMINI_REASONING_MODEL", "gemini-3.5-flash")
# Optional second model tried when the main one is overloaded (503/429) or retired (404).
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite")
# Seconds to wait before retrying a busy model, and how long to skip it after it stays busy.
LLM_RETRY_DELAYS = tuple(float(x) for x in os.getenv("LLM_RETRY_DELAYS", "2,5").split(",") if x)
LLM_BUSY_COOLDOWN_SECONDS = int(os.getenv("LLM_BUSY_COOLDOWN_SECONDS", "60"))
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
# Requests per minute allowed by your Gemini free tier (see AI Studio -> rate limits).
GEMINI_RPM = int(os.getenv("GEMINI_RPM", "10"))   # per model: each model has its own quota
# How long a call may queue for its model's quota before trying the next model.
LLM_QUEUE_SECONDS = float(os.getenv("LLM_QUEUE_SECONDS", "20"))
# Same facts, same answer: no sampling randomness, and a fixed seed for the model.
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))
LLM_SEED = int(os.getenv("LLM_SEED", "7"))
# Lets scripts/evaluate.py --scenarios simulate a failing data source or analyst through the
# X-Eval-Fault header. Off by default; never enable it on the public deployment.
EVAL_FAULTS = os.getenv("EVAL_FAULTS", "0").lower() in ("1", "true", "yes")

# Web app
SECRET_KEY = os.getenv("SECRET_KEY", "")
# "Sign in with Google": an OAuth client ID (Web application) from Google Cloud Console. Optional.
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
REQUIRE_LOGIN = os.getenv("REQUIRE_LOGIN", "1") == "1"
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "users.db"))
# A hosted Postgres (e.g. Neon or Supabase, free) keeps data across redeploys. Leave blank for SQLite.
DATABASE_URL = os.getenv("DATABASE_URL", "")
LOG_DIR = Path(os.getenv("LOG_DIR", str(BASE_DIR / "logs")))

# Agent behaviour limits
MAX_DEBATE_ROUNDS = int(os.getenv("MAX_DEBATE_ROUNDS", "3"))
MAX_REPLANS = int(os.getenv("MAX_REPLANS", "1"))
MAX_TOOL_STEPS = int(os.getenv("MAX_TOOL_STEPS", "4"))
# Requests for more evidence (Strategy or Risk -> Planner -> an analyst) allowed per analysis.
MAX_FOLLOWUPS = int(os.getenv("MAX_FOLLOWUPS", "2"))
HTTP_TIMEOUT_SECONDS = int(os.getenv("HTTP_TIMEOUT_SECONDS", "8"))
DATA_CACHE_SECONDS = int(os.getenv("DATA_CACHE_SECONDS", "900"))

# Watchlist briefs (8:30 morning, 3:15 closing, alerts during market hours)
BRIEF_SCHEDULER = os.getenv("BRIEF_SCHEDULER", "1") == "1"
# Shared secret for /api/cron/tick, which a free external scheduler calls to wake the server.
CRON_SECRET = os.getenv("CRON_SECRET", "")
# Optional email delivery of briefs (e.g. Gmail with an app password). Leave blank to disable.
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
MAIL_FROM = os.getenv("MAIL_FROM", "") or SMTP_USER
APP_URL = os.getenv("APP_URL", "")
# Optional phone notifications through a Telegram bot (free; create one with @BotFather).
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_NAME = os.getenv("TELEGRAM_BOT_NAME", "")      # without the @

# Reject a symbol that no price source knows before starting the agents (answers in seconds
# with suggestions instead of a minute of failing tool calls).
SYMBOL_PRECHECK = os.getenv("SYMBOL_PRECHECK", "1") == "1"
