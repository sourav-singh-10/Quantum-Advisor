<div align="center">

# 🔮 Quantum Advisor

### A committee of AI agents that plans, argues and explains an investment decision

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/Agents-LangGraph-1C3C3C)
![Gemini](https://img.shields.io/badge/LLM-Gemini-4285F4?logo=google&logoColor=white)
![Flask](https://img.shields.io/badge/Backend-Flask-000000?logo=flask&logoColor=white)
![Tests](https://github.com/sourav-singh-10/quantum-advisor/actions/workflows/tests.yml/badge.svg)
![Cost](https://img.shields.io/badge/Running%20cost-%E2%82%B90-brightgreen)

**Live demo:** https://quantum-advisor.onrender.com

</div>

> [!IMPORTANT]
> Educational decision-support prototype. Not investment advice; consult a SEBI-registered adviser.

## What it does

You enter an NSE ticker and your investor profile (and, optionally, a goal such as *"saving for a house in 3 years"*). Nine agents then work on it together, and you watch their conversation live:

1. **Planner** decides which analysts this request needs and what each should focus on, using memory of your previous runs.
2. **Market, Fundamentals and News analysts** work in parallel. They choose their own data sources and switch when one fails.
3. **Planner** checks their results, **re-plans** failed work, and caps the confidence the data can support.
4. **Strategy agent** proposes BUY / HOLD / SELL. **Risk manager** approves it, asks for a revision with numbered objections, or vetoes it. They go up to 3 rounds, then the Planner arbitrates.
5. **Portfolio agent** sizes the position from *your* portfolio value; **Report agent** explains the result, including the disagreement.

All maths and data fetching are done by tools, so the LLM decides and explains but never invents numbers. If the LLM is unavailable, each agent falls back to its rule-based path and the result is marked *degraded*; nothing crashes.

## Why several agents instead of one

A single prompt that sees everything tends to commit to its first answer. Here the analysts are independent (so they run in parallel and can fail independently), and the Strategy agent's answer must survive a critic whose only job is to protect this particular investor. The Planner adapts the plan when data is missing. The trace shows all of it.

## Architecture

![Architecture](docs/architecture.svg)

Pattern: **orchestrator–worker with a critic loop**, built as a LangGraph state machine (`core/graph.py`). Details, interaction rules and design choices: [`docs/design-document.md`](docs/design-document.md).

| Agent | Decides | Tools |
|---|---|---|
| Planner | plan, re-plan, confidence cap, arbitration | run memory |
| Profile | constraints from profile + goal | `risk_capacity` |
| Market analyst | which price source; reading of indicators | `get_price_history`, `compute_indicators` |
| Fundamentals analyst | health vs. sector | `get_fundamentals`, `score_fundamentals` |
| News analyst | which news source; sentiment + materiality per headline | `get_headlines` |
| Risk manager | approve / revise / veto with objections | `market_risk_score`, `suitability_gap` |
| Strategy | BUY / HOLD / SELL; answers to objections | `price_targets` |
| Portfolio | concrete actions | `position_size` |
| Report | final explanation | — |

## Free to run

| Service | Free tier used | Needed? |
|---|---|---|
| Google Gemini API (AI Studio key) | free tier; the app rate-limits itself (`GEMINI_RPM`) | Recommended (without it agents use rules) |
| yfinance | no key | Default price + fundamentals source |
| Google News RSS | no key | Default news source |
| Alpha Vantage | 25 requests / day | Optional fallback |
| MarketStack | 100 requests / month | Optional fallback |
| NewsAPI | 100 requests / day (developer plan) | Optional |
| Render | free web service (sleeps when idle) | Hosting |
| GitHub Actions | free for public repos | CI |

Prices and news are cached for 15 minutes to stay within these limits.

## Quick start (Windows PowerShell)

```powershell
git clone https://github.com/sourav-singh-10/quantum-advisor.git
cd quantum-advisor
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

copy .env.example .env      # then fill in the keys you have
$env:GEMINI_API_KEY = "your_key"
$env:REQUIRE_LOGIN  = "0"   # skip login while developing

python app.py               # open http://localhost:5000/index.html
```

Check your configuration with `http://localhost:5000/api/health?deep=1`; it makes one tiny Gemini call and reports whether the model answers.

## Tests

```powershell
pytest -q
```

97 tests, no network or keys needed (a scripted fake LLM and stubbed data sources). They cover every agentic path: revision changes the decision, deadlock leads to arbitration, the market agent switches source after a failure, the planner re-plans a failed analyst, graceful failure without price data, the guardrail overriding an unsafe approval, memory on a second run; plus tools, the LLM client, API validation, streaming, password hashing, and the documented JSON Schemas against real output. CI runs them on every push and pull request.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/analyze` | Run the agents, return JSON (schema: `schemas/analyze_response.schema.json`) |
| POST | `/api/analyze/stream` | Same, as Server-Sent Events: `start`, one `trace` per agent message, `result` |
| GET | `/api/runs/<run_id>/trace` | The saved execution trace of a run |
| GET | `/api/history` | Your previous runs (memory) |
| POST | `/upload_portfolio` | Analyse a CSV/XLSX of holdings |
| GET | `/api/health` | Status; `?deep=1` also tests the LLM |

Inputs and outputs with samples: [`docs/io-definitions.md`](docs/io-definitions.md).

## Execution traces (CA3 evidence)

Every run writes `logs/traces/<run_id>.jsonl`: one line per message with sender, receiver, type (`plan`, `task`, `tool_call`, `tool_result`, `result`, `error`, `replan`, `assessment`, `draft`, `critique`, `arbitration`, `decision`, `memory`, `final`), debate round, payload and the LLM model and latency. To capture submission evidence from the live site, unedited:

```powershell
python scripts/capture_run.py https://quantum-advisor.onrender.com you@example.com yourpassword --name normal --ticker TCS --age 30 --risk Aggressive --horizon Long-term
python scripts/capture_run.py https://quantum-advisor.onrender.com you@example.com yourpassword --name conflict --ticker ADANIENT --age 64 --risk Conservative --horizon Short-term --experience Beginner
```

## Deploy (Render, free)

`render.yaml` defines the service (`gunicorn app:app --workers 1 --threads 8 --timeout 180`). In Render → Environment, set `GEMINI_API_KEY` and any optional data keys; `SECRET_KEY` is generated automatically. Render's free disk is temporary, so users and traces reset on redeploy; keep evidence traces in `docs/traces/`.

## Repository structure

```text
agents/     nine agents (LLM decisions + rule fallbacks)
core/       graph.py (LangGraph), runner.py, schemas.py, tracer.py, memory.py, context.py
tools/      data sources and maths the agents call
services/   Gemini client (structured output, retry, rate limit)
schemas/    JSON Schemas for request, response and trace events
frontend/   index.html, css/, js/ (live agent feed)
tests/      pytest suite with a fake LLM
scripts/    capture_run.py (genuine run evidence)
docs/       synopsis, design document, I/O definitions, architecture, traces, samples
```

## Limitations

Data quality depends on free third-party sources; LLM judgement can be wrong within the guardrails; the risk formulas are simple and not back-tested; this is not investment advice.
