# Quantum Advisor — Input and Output Definitions

Machine-readable schemas live in `schemas/` and are enforced in code: requests by `core.schemas.AnalyzeRequest` (Pydantic), responses by `tests/test_schemas.py` (JSON Schema validation of real output).

## 1. Inputs

### 1.1 Stock analysis request — `POST /api/analyze` (JSON) or `POST /api/analyze/stream` (Server-Sent Events)

Schema: [`schemas/analyze_request.schema.json`](../schemas/analyze_request.schema.json)

| Field | Type | Rules | Default |
|---|---|---|---|
| `ticker` | string | NSE symbol, 1–20 of `A–Z 0–9 & -`; `.NS` / `.BO` suffix and lower case accepted | required |
| `age` | integer | 18–100 | 30 |
| `experience` | enum | `Beginner`, `Intermediate`, `Experienced` | `Beginner` |
| `riskAppetite` | enum | `Conservative`, `Moderate`, `Aggressive` | `Moderate` |
| `portfolioValue` | number | > 0, INR | 50000 |
| `timeHorizon` | enum | `Short-term`, `Medium-term`, `Long-term` | `Medium-term` |
| `goal` | string or null | ≤ 300 characters, free text | null |

Sample (also in `docs/samples/`):

```json
{
  "ticker": "RELIANCE",
  "age": 34,
  "experience": "Intermediate",
  "riskAppetite": "Moderate",
  "portfolioValue": 200000,
  "timeHorizon": "Long-term",
  "goal": "Building a retirement corpus; I can wait out a bad year"
}
```

Invalid input returns HTTP 400:

```json
{"error": "Invalid input", "details": [{"field": "age", "message": "Input should be greater than or equal to 18"}]}
```

### 1.2 Portfolio upload — `POST /upload_portfolio` (multipart, field `file`)

CSV or XLSX up to 5 MB with columns `ticker, quantity, buy_price` (a Zerodha holdings export is also recognised).

```csv
ticker,quantity,buy_price
RELIANCE,10,2400
TCS,5,3500
HDFCBANK,20,1550
INFY,12,1450
ITC,100,420
```

## 2. Outputs

### 2.1 Analysis response (HTTP 200)

Schema: [`schemas/analyze_response.schema.json`](../schemas/analyze_response.schema.json). Groups of fields and the agent that produces them:

| Group | Fields | Produced by |
|---|---|---|
| Market | `ticker, currentPrice, priceDisplay, priceSource, sourcesTried, trend, rsi, volatility, ma20, ma50, change1mPct, marketSummary, momentum, dataQuality` | Market analyst |
| Investor | `userType, riskCapacityScore, profileSummary, maxPositionPct, horizonYears, constraints` | Profile agent |
| Fundamentals | `pe, roe, de, profitMargin, sector, healthScore, financialHealth, fundamentalsSummary, fundamentalsPoints` | Fundamentals analyst |
| News | `newsSentiment, sentimentScore, headlineCount, newsSource, topHeadlines, materialHeadlines, newsSummary` | News analyst |
| Risk | `riskScore, riskLevel, riskFactors, suitabilityGap, riskSummary, keyRisks, suitable` | Risk manager |
| Decision | `recommendation, recommendationClass, confidence, decidedBy, buyScore, targetPrice1, targetPrice2, stopLoss, reasoning` | Strategy agent (+ Planner if arbitrated) |
| Debate | `debate[]: {round, draft{recommendation, confidence, rationale, responses[]}, critique{verdict, reasoning, objections[]}}` | Strategy ↔ Risk |
| Portfolio | `portfolioAdvice, positionSizing{positionPct, units, amount}, expectedRange` | Portfolio agent |
| Report | `aiReport, reportHeadline` | Report agent |
| Run | `plan{focus, replans}, lastRun, meta{runId, status, llmAvailable, llmCalls, llmFailures, degradedAgents, failedAgents, durationMs, replans, debateRounds}, trace[]` | Planner / tracer |

`meta.status` is `ok`, `degraded` (some agent used its rule fallback or had no data) or `failed`.

When no price source works the response is HTTP 502:

```json
{"ticker": "NOSUCH", "error": "Could not get price data for NOSUCH from any source. Check the symbol (NSE code, e.g. RELIANCE).",
 "errors": {"MarketAnalyst": "no price source worked (yfinance: ...; alphavantage: ...; marketstack: ...)"},
 "meta": {"status": "failed", "...": "..."}, "trace": ["..."]}
```

### 2.2 Execution trace — one message per line

Schema: [`schemas/trace_event.schema.json`](../schemas/trace_event.schema.json). Streamed as `event: trace` during `/api/analyze/stream`, returned in `trace[]`, saved to `logs/traces/<run_id>.jsonl`, and served by `GET /api/runs/<run_id>/trace`.

```json
{"run_id": "r_20261020_091211_a1b2c3", "seq": 31, "ts": "2026-10-20T09:12:40.512+00:00",
 "from": "RiskManager", "to": "StrategyAgent", "type": "critique", "round": 1,
 "payload": {"verdict": "revise", "reasoning": "...",
             "objections": [{"id": "R1", "text": "...", "severity": "major"}]},
 "llm": {"model": "<GEMINI_REASONING_MODEL>", "latency_ms": 1840, "ok": true}}
```

## 3. Real samples

`docs/samples/*_request.json`, `docs/samples/*_response.json` and `docs/traces/*.jsonl` are captured from the live deployment with `scripts/capture_run.py` and are not edited by hand.
