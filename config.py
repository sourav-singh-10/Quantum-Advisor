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
GEMINI_FAST_MODEL = os.getenv("GEMINI_FAST_MODEL", "gemini-2.5-flash")
GEMINI_REASONING_MODEL = os.getenv("GEMINI_REASONING_MODEL", GEMINI_FAST_MODEL)
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
# Requests per minute allowed by your Gemini free tier (see AI Studio -> rate limits).
GEMINI_RPM = int(os.getenv("GEMINI_RPM", "10"))

# Web app
SECRET_KEY = os.getenv("SECRET_KEY", "")
REQUIRE_LOGIN = os.getenv("REQUIRE_LOGIN", "1") == "1"
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "users.db"))
LOG_DIR = Path(os.getenv("LOG_DIR", str(BASE_DIR / "logs")))

# Agent behaviour limits
MAX_DEBATE_ROUNDS = int(os.getenv("MAX_DEBATE_ROUNDS", "3"))
MAX_REPLANS = int(os.getenv("MAX_REPLANS", "1"))
MAX_TOOL_STEPS = int(os.getenv("MAX_TOOL_STEPS", "4"))
HTTP_TIMEOUT_SECONDS = int(os.getenv("HTTP_TIMEOUT_SECONDS", "8"))
DATA_CACHE_SECONDS = int(os.getenv("DATA_CACHE_SECONDS", "900"))
