# Quantum Advisor — Input and Output Definitions

Machine-readable schemas live in `schemas/` and are enforced in code: requests by `core.schemas.AnalyzeRequest` (Pydantic), responses by `tests/test_schemas.py` (JSON Schema validation of real output).

## 1. Inputs

### 1.1 Stock analysis request — `POST /api/analyze` or `POST /api/analyze/stream` (Server-Sent Events)

Send JSON, or `multipart/form-data` with the same fields when attaching a company document.

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
| `document` | PDF file (multipart only) | Annual report, quarterly results or balance sheet; must have a text layer; ≤ 15 MB; at most 400 pages are read | none |

Sample:

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

With a document (PowerShell, after signing in to get a session cookie):

```powershell
curl.exe -b cookies.txt -F ticker=TCS -F age=40 -F timeHorizon=Long-term -F riskAppetite=Moderate `
  -F portfolioValue=500000 -F "document=@TCS_Q2_FY27_results.pdf" http://localhost:5000/api/analyze
```

Invalid input returns HTTP 400:

```json
{"error": "Invalid input", "details": [{"field": "age", "message": "Input should be greater than or equal to 18"}]}
```

An unusable document is refused the same way, before any agent runs:

```json
{"error": "Invalid input", "details": [{"field": "document", "message": "Could not use this PDF: the PDF has no readable text (it may be a scanned image)"}]}
```

Optional request field `holding` (true/false): whether the investor already owns the stock. When it is left out, the server checks the investor's saved holdings.

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

### 1.3 Investor profile — `PUT /api/profile` (signed in)

The same fields as the analysis request without `ticker` (`age, experience, riskAppetite, portfolioValue, timeHorizon, goal`), with the same rules. `GET /api/profile` returns `{"saved": bool, "profile": {...}}`; invalid values return HTTP 400 with `details` like the analysis request.

## 2. Outputs

### 2.1 Analysis response (HTTP 200)

Schema: [`schemas/analyze_response.schema.json`](../schemas/analyze_response.schema.json). Groups of fields and the agent that produces them:

| Group | Fields | Produced by |
|---|---|---|
| Market | `ticker, currentPrice, priceDisplay, priceSource, sourcesTried, priceHistory, priceDates, volumeHistory, trend, rsi, volatility, ma20, ma50, change1mPct, maxDrawdownPct, belowHighPct, volumeRatio, volumeLevel, macd, macdSignal, macdHist, macdState, bbUpper, bbLower, bbPercentB, bbWidthPct, bbState, change3mPct, support, resistance, toSupportPct, toResistancePct, marketSummary, momentum, dataQuality` | Market analyst |
| Investor | `userType, riskCapacityScore, profileSummary, maxPositionPct, horizonYears, constraints` | Profile agent |
| Fundamentals | `pe, eps, revenueCr, roe, de, profitMargin, sector, companyName, healthScore, financialHealth, fundamentalsSummary, fundamentalsPoints` | Fundamentals analyst |
| Document | `documentAvailable, documentName, documentPages, documentPagesUsed, documentPeriod, documentUnit, documentFigures{Revenue, Net profit, EPS (basic), Borrowings, Total equity}, documentRatios{profitMargin, de}, documentRedFlags, documentAboutCompany, documentPoints, documentSummary` | Document analyst |
| Cross-check | `documentConflicts[]`, `documentCheck{issues, trust: document/live/both, reasoning}` | Document analyst, Fundamentals analyst, Planner |
| News | `newsSentiment, sentimentScore, headlineCount, newsSource, topHeadlines, materialHeadlines, headlineLabels[] {title, source, sentiment, material}, newsSummary` | News analyst |
| Risk | `riskScore, riskLevel, riskFactors, riskBreakdown[] {label, points}, suitabilityGap, riskSummary, keyRisks, suitable` | Risk manager |
| Decision | `recommendation, recommendationClass, confidence, decidedBy, buyScore, targetPrice1, targetPrice2, stopLoss, reasoning` | Strategy agent (+ Planner if arbitrated) |
| Debate | `debate[]: {round, draft{recommendation, confidence, rationale, responses[]}, critique{verdict, reasoning, objections[]}}` | Strategy ↔ Risk |
| Position | `holding` (from saved holdings, or sent in the request), `action{label: Buy/Wait/Avoid or Add more/Keep/Sell, text, holding, tooRiskyForYou}` | `tools/actions.py` |
| Follow-ups | `followups[]: {from, round, agent, question, instruction, granted, reasoning, answer, evidence[], changesView}` | Strategy or Risk asks, Planner routes, an analyst answers |
| Scorecard | `scorecard{scores[]: {name, score 0-10, why}, entry{verdict: Good/Fair/Stretched, why}, redFlags[]}` | Computed from the fields above (`tools/scorecard.py`) |
| Preferences | `preferenceNotes[]`: the stock is in a sector the investor asked to avoid (the call is not changed) | Planner |
| Portfolio | `portfolioAdvice, positionSizing{positionPct, units, amount}, expectedRange` | Portfolio agent |
| Report | `aiReport, reportHeadline` | Report agent |
| Run | `plan{focus, replans}, lastRun, meta{runId, status, llmAvailable, llmCalls, llmFailures, degradedAgents, failedAgents, durationMs, replans, debateRounds, followups, models{model: calls}}, trace[]` | Planner / tracer |

`meta.status` is `ok`, `degraded` (some agent used its rule fallback or had no data) or `failed`.

When no price source works the response is HTTP 502:

```json
{"ticker": "NOSUCH", "error": "Could not get price data for NOSUCH from any source. Check the symbol (NSE code, e.g. RELIANCE).",
 "errors": {"MarketAnalyst": "no price source worked (yfinance: ...; alphavantage: ...; marketstack: ...)"},
 "meta": {"status": "failed", "...": "..."}, "trace": ["..."]}
```

### 2.2 Portfolio review (HTTP 200)

Schema: [`schemas/portfolio_response.schema.json`](../schemas/portfolio_response.schema.json), checked against real output by `tests/test_schemas.py`.

| Group | Fields |
|---|---|
| Per holding (`stocks[]`) | `ticker, quantity, buyPrice, currentPrice, priceSource, pnl, pnlPct, volatility, trend, rsi, pe, sector, isHighVol, recommendation, reason, weight, history[]` |
| Totals | `totalValue, totalCost, totalPnL, totalPnLPct, livePriced, sectorAllocation, riskScore, diversificationScore, investmentStyle` |
| Agent review | `review.summary, review.actions[], review.holdings[] {ticker, action: ADD/HOLD/TRIM/REVIEW, reason}, review.degraded` |
| Run | `meta {runId, llmAvailable, llmCalls, llmFailures}, trace[]` |

`priceSource` is `live (yfinance)`, `live (alphavantage)`, `live (marketstack)`, `from your file`, or `unavailable (buy price used)`.

### 2.3 Execution trace — one message per line

Schema: [`schemas/trace_event.schema.json`](../schemas/trace_event.schema.json). Streamed as `event: trace` during `/api/analyze/stream`, returned in `trace[]`, saved to `logs/traces/<run_id>.jsonl`, and served by `GET /api/runs/<run_id>/trace`.

```json
{"run_id": "r_20261020_091211_a1b2c3", "seq": 24, "ts": "2026-10-20T09:12:31.204+00:00",
 "from": "DocumentAnalyst", "to": "FundamentalsAnalyst", "type": "challenge", "round": null,
 "payload": {"issues": ["Profit margin is 10.0% in the document but 18.0% in the live data"],
             "question": "Which figures should the committee rely on?"}}
{"run_id": "r_20261020_091211_a1b2c3", "seq": 31, "ts": "2026-10-20T09:12:40.512+00:00",
 "from": "RiskManager", "to": "StrategyAgent", "type": "critique", "round": 1,
 "payload": {"verdict": "revise", "reasoning": "...",
             "objections": [{"id": "R1", "text": "...", "severity": "major"}]},
 "llm": {"model": "<GEMINI_REASONING_MODEL>", "latency_ms": 1840, "ok": true}}
```

A follow-up in the trace, in order (`round` is the debate round it belongs to):

```json
{"from": "RiskManager", "to": "Planner", "type": "followup", "round": 1,
 "payload": {"agent": "MarketAnalyst", "question": "How does the one-month rise compare with the past year?",
             "why": "A 13% month could be a spike near the top of the yearly range."}}
{"from": "Planner", "to": "team", "type": "decision", "round": 1,
 "payload": {"followup": "granted", "agent": "MarketAnalyst", "instruction": "...", "reasoning": "..."}}
{"from": "MarketAnalyst", "to": "RiskManager", "type": "answer", "round": 1,
 "payload": {"question": "...", "answer": "...", "evidence": ["1-year return +21.4%", "price 4% below the 1-year high"], "changesView": true}}
```

### 2.4 Account and sign-in

| Endpoint | Body | Result |
|---|---|---|
| `POST /signup`, `POST /login` | `{email, password}` | Session cookie; `{ok: true}` or `{error}` |
| `GET /api/auth/config` | – | `{googleClientId}` (empty when Google sign-in is off) |
| `POST /auth/google` | `{credential}`: the ID token from Google Identity Services | Verified on the server; session cookie and `{ok, email, new}`; `new` is true for a first sign-in |
| `GET /me` | – | `{loggedIn, email, authMethod: "password" or "google"}` |

## 3. Real samples

Every file in `docs/traces/` is a run trace exactly as the server logged it: `followup_changes_call.jsonl` (the run replayed on the home page) and the three `scenario_*.jsonl` failure scenarios from `docs/scenarios.md`, all decided by the model. Further request, response and trace samples are captured from the live deployment with `scripts/capture_run.py` (into `docs/samples/` and `docs/traces/`) and are never edited by hand.

## Watchlist briefs

`GET /api/briefs` returns the latest briefs and alerts for the signed-in user.

```json
{
  "morning": {
    "kind": "morning", "day": "2026-10-19", "runId": "r_20261019_030012_a1b2c3",
    "generatedIst": "19 Oct 2026, 08:30 AM",
    "summary": {"headline": "2 of 3 watchlist stocks closed higher; the biggest move was TCS +4.9% at ₹2,465.00.",
                "points": ["TCS: TCS Q2 profit rises 4% QoQ; company declares interim dividend of Rs 12/share",
                           "TCS: overbought (RSI 81)."],
                "actions": ["Read the latest news on TCS before the market opens."], "byLLM": false},
    "items": [{"ticker": "TCS", "name": "Tata Consultancy Services Limited", "price": 2465.0,
               "prevClose": 2350.0, "changePct": 4.89, "change5dPct": 15.6, "high52": 2611.0, "low52": 1983.0,
               "rangeLabel": "52-week", "trend": "Uptrend", "rsi": 81.2, "volumeRatio": 2.6,
               "flags": [{"text": "Up 4.9% on the day", "tone": "up"}, {"text": "Overbought (RSI 81)", "tone": "watch"}],
               "news": [{"title": "TCS launches industrial AI platform", "tone": "Positive", "material": false,
                         "ageHours": 6.5, "link": "https://..."}]}]
  },
  "closing": {"kind": "closing", "totals": {"value": 208121, "dayPnL": 1936, "dayPnLPct": 0.94,
              "totalPnL": -26979, "totalPnLPct": -11.5, "sectors": {"IT": 15.5, "Banking": 28.2},
              "suggestions": []}, "items": ["... as above, plus quantity, buyPrice, value, dayPnL, pnlPct, weight, sector"],
              "watchMoves": [], "summary": {"...": "..."}},
  "alerts": [{"id": 7, "ticker": "INFY", "kind": "news", "title": "Infosys shares slump after SEBI probe",
              "detail": "Mint", "tone": "down", "link": "https://...", "created_at": "2026-10-19T05:12:00+00:00", "seen": 0}],
  "unseen": 1, "watchlist": [{"ticker": "TCS", "name": "Tata Consultancy Services Limited"}],
  "holdings": [{"ticker": "TCS", "quantity": 6, "buy_price": 3400}], "emailAvailable": false, "emailOn": false
}
```

Values in the example are illustrative of the shape; real briefs carry the numbers fetched at run time.
