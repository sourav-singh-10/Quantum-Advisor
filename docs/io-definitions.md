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

Sample:

<!-- sample:analysis-response -->
Real output, shortened for reading from [`docs/samples/normal_response.json`](../docs/samples/normal_response.json) (run `r_20261022_043338_945e02`, 21 of 21 decisions by the model). Strings over 160 characters and lists over 2 items are cut; the file itself is unedited.

```json
{
  "action": {
    "holding": false,
    "label": "Avoid",
    "text": "Do not buy: the committee expects it to do poorly.",
    "tooRiskyForYou": false
  },
  "aiReport": "INFY: Technical Overextension and Missing Fundamentals Point to a Sell Recommendation\n\nInfosys (INFY) is currently assigned a SELL rating at a price of ₹1,170.…",
  "avgVolume50": 10295637,
  "bbLower": 927.44,
  "bbPercentB": 0.97,
  "bbState": "Near upper band",
  "bbUpper": 1176.55,
  "bbWidthPct": 23.68,
  "belowHighPct": -5.92,
  "buyScore": 36,
  "change1mPct": 12.69,
  "change3mPct": 11.23,
  "confidence": "Low",
  "constraints": [
    "No specific stated goals",
    "Moderate risk appetite limits aggressive equity exposure",
    "… 1 more"
  ],
  "currentPrice": 1170.3,
  "dataQuality": "Good",
  "de": null,
  "debate": [
    {
      "critique": {
        "followup": null,
        "objections": [
          {
            "id": "R1",
            "severity": "major",
            "text": "The asset lacks fundamental data to support a valuation, making a 'HOLD' recommendation speculative rather than investment-grade."
          },
          {
            "id": "R2",
            "severity": "blocking",
            "text": "The technical indicators (RSI 77, high volatility) combined with institutional selling pressure create an unacceptable risk of capital loss for a retail invest…"
          },
          "… 1 more"
        ],
        "reasoning": "The recommendation to 'HOLD' is rejected because the asset exhibits extreme technical overextension (RSI 77), high volatility, and a complete lack of fundament…",
        "verdict": "veto"
      },
      "draft": {
        "confidence": "Low",
        "rationale": [
          "The stock score of 32 falls within the HOLD range of 20-40.",
          "The RSI of 76.7 indicates the stock is overbought, suggesting a high probability of a near-term pullback.",
          "… 2 more"
        ],
        "recommendation": "HOLD",
        "responses": [
          {
            "objection_id": "Risk Manager",
            "response": "I have conceded to the risk manager's objection regarding the suitability gap and technical risks by maintaining a HOLD recommendation rather than a BUY, despi…"
          }
        ]
      },
      "round": 1
    },
    {
      "critique": {
        "followup": null,
        "objections": [],
        "reasoning": "The strategist has addressed all previous objections by downgrading the recommendation to SELL. Given the lack of fundamental data, the high volatility, and th…",
        "verdict": "approve"
      },
      "draft": {
        "confidence": "Low",
        "rationale": [
          "The stock score of 32 is adjusted to SELL due to the blocking risk of technical overextension and lack of fundamental transparency.",
          "RSI of 76.7 indicates extreme overbought conditions, increasing the probability of a sharp correction.",
          "… 2 more"
        ],
        "recommendation": "SELL",
        "responses": [
          {
            "objection_id": "R1",
            "response": "I concede that without fundamental data, a HOLD recommendation is speculative; therefore, I have downgraded to SELL to protect the investor's capital."
          },
          {
            "objection_id": "R2",
            "response": "I agree that the combination of RSI 77 and institutional selling creates an unacceptable risk profile for a moderate-risk investor, necessitating an exit."
          },
          "… 1 more"
        ]
      },
      "round": 2
    }
  ],
  "decidedBy": "Risk approved in round 2",
  "documentAvailable": false,
  "documentConflicts": [],
  "expectedRange": "Typical 1-month range: ₹1,051 – ₹1,290 (±10.2%)",
  "financialHealth": "Unknown",
  "followups": [
    {
      "agent": "FundamentalsAnalyst",
      "answer": "The current P/E ratio and consensus earnings growth projections for INFY cannot be determined from the provided financial health data.",
      "changesView": false,
      "evidence": [
        "financialHealth: Unknown"
      ],
      "from": "StrategyAgent",
      "granted": true,
      "instruction": "Calculate the current P/E ratio for INFY and provide the consensus earnings growth projections for the next two fiscal years to assess valuation.",
      "question": "What are the current P/E ratio and earnings growth projections for INFY?",
      "reasoning": "The user requires fundamental valuation data to evaluate INFY as a long-term holding, which is a critical component of the investment thesis.",
      "round": 1
    },
    {
      "agent": "FundamentalsAnalyst",
      "answer": "The available facts do not contain the recent closing price, trailing twelve-month earnings per share, or the year-over-year revenue growth percentage for INFY…",
      "changesView": false,
      "evidence": [
        "financialHealth: Unknown"
      ],
      "from": "StrategyAgent",
      "granted": true,
      "instruction": "Calculate the trailing twelve-month (TTM) P/E ratio for INFY using the most recent closing price and TTM earnings per share, and determine the year-over-year r…",
      "question": "Can you provide the trailing twelve-month (TTM) P/E ratio and the latest quarterly revenue growth percentage for INFY?",
      "reasoning": "The previous attempt failed to provide specific metrics. Providing these fundamental data points is essential for the StrategyAgent to assess valuation and gro…",
      "round": 1
    }
  ],
  "fundamentalsAvailable": false,
  "fundamentalsPoints": [],
  "fundamentalsSummary": "Unavailable: no fundamentals available for INFY.NS",
  "headlineCount": 12,
  "headlineLabels": [
    {
      "material": false,
      "sentiment": "Neutral",
      "source": "Univest",
      "title": "Infosys Share Price News: Price Action and Valuation Check - Univest"
    },
    {
      "material": true,
      "sentiment": "Negative",
      "source": "MarketBeat",
      "title": "Infosys Ltd. $INFY Shares Sold by Robeco Institutional Asset Management B.V. - MarketBeat"
    },
    "… 10 more"
  ],
  "healthScore": null,
  "holding": false,
  "horizonYears": 7.0,
  "keyRisks": [
    "1. Technical Overextension: The stock is strongly overbought (RSI 77) and trading near its upper Bollinger Band, indicating a high risk of a short-term correct…",
    "2. Lack of Fundamental Transparency: The absence of fundamental data makes it impossible to justify the current valuation or assess long-term viability.",
    "… 2 more"
  ],
  "lastRun": null,
  "ma20": 1052.0,
  "ma50": 1086.18,
  "macd": 22.92,
  "macdHist": 20.43,
  "macdSignal": 2.49,
  "macdState": "Bullish",
  "marketSummary": "INFY is exhibiting a strong upward trend, trading near its upper Bollinger Band with an overbought RSI of 76.7. Despite the elevated momentum and low volatilit…",
  "materialHeadlines": [
    "Infosys Ltd. $INFY Shares Sold by Robeco Institutional Asset Management B.V. - MarketBeat",
    "Infosys Q2 results, dividend 2026 amount, record date announcement date-time: Preview, earnings schedule, history, yield - Livemint",
    "… 3 more"
  ],
  "maxDrawdownPct": -20.79,
  "maxPositionPct": 15.0,
  "meta": {
    "debateRounds": 2,
    "degradedAgents": [],
    "durationMs": 86987,
    "failedAgents": [],
    "followups": 2,
    "llmAvailable": true,
    "llmCalls": 21,
    "llmFailures": 0,
    "models": {
      "gemini-3.1-flash-lite": 9,
      "gemini-3.5-flash": 3,
      "gemini-3.5-flash-lite": 9
    },
    "replans": 1,
    "runId": "r_20261022_043338_945e02",
    "status": "ok"
  },
  "momentum": "Strong up",
  "newsAvailable": true,
  "newsSentiment": "Neutral",
  "newsSource": "google_rss",
  "newsSummary": "The recent news headlines for Infosys show a mixed sentiment. While there are positive indicators such as sector rallies, expanded collaborations, and upbeat s…",
  "observations": 126,
  "pe": null,
  "plan": {
    "focus": "Does INFY present a solid fundamental growth and valuation profile to serve as a core long-term investment within a moderate-risk portfolio?",
    "replans": 1
  },
  "portfolioAdvice": [
    "Do not buy INFY as the current recommendation is SELL with a target price of ₹1,039.81 and ₹909.32.",
    "Allocate 0.0 percent (0 units, ₹0.0) of your portfolio to this trade to respect single stock concentration limits.",
    "… 1 more"
  ],
  "positionSizing": {
    "amount": 0.0,
    "positionPct": 0.0,
    "units": 0
  },
  "preferenceNotes": [],
  "priceDates": [
    "2026-04-30",
    "2026-05-04",
    "… 118 more"
  ],
  "priceDisplay": "₹1,170.30",
  "priceHistory": [
    1156.77,
    1143.65,
    "… 118 more"
  ],
  "priceSource": "yfinance",
  "profileSummary": "Intermediate investor with a moderate risk appetite and a long-term horizon managing an INR 300,000 portfolio.",
  "reasoning": [
    "The stock score of 32 is adjusted to SELL due to the blocking risk of technical overextension and lack of fundamental transparency.",
    "RSI of 76.7 indicates extreme overbought conditions, increasing the probability of a sharp correction.",
    "… 2 more"
  ],
  "recommendation": "SELL",
  "recommendationClass": "sell",
  "reportHeadline": "INFY: Technical Overextension and Missing Fundamentals Point to a Sell Recommendation",
  "requestedTicker": "INFY",
  "resistance": 1190.7,
  "riskBreakdown": [
    {
      "label": "Volatility",
      "points": 12
    },
    {
      "label": "Momentum",
      "points": 12
    },
    "… 2 more"
  ],
  "riskCapacityScore": 80,
  "riskFactors": [
    "Above-average volatility (2.2% daily)",
    "Strongly overbought (RSI 77)",
    "… 1 more"
  ],
  "riskLevel": "High",
  "riskScore": 32,
  "riskSummary": "The recommendation to invest in INFY is rejected due to a suitability gap and significant technical risks. The stock is currently overbought with an RSI of 77…",
  "roe": null,
  "rsi": 76.7,
  "scorecard": {
    "entry": {
      "verdict": "Stretched",
      "why": "Price is high in its recent range; entries after a run-up often see a pullback."
    },
    "redFlags": [
      "Deeply overbought (RSI 77)"
    ],
    "scores": [
      {
        "name": "Momentum",
        "score": 10,
        "why": "Uptrend, +12.7% in a month, MACD bullish"
      },
      {
        "name": "News",
        "score": 5,
        "why": "Neutral across 12 headlines"
      }
    ]
  },
  "sentimentScore": 0,
  "sourcesTried": [
    "yfinance"
  ],
  "stopLoss": 1300.79,
  "suitabilityGap": -4,
  "suitable": false,
  "support": 992.0,
  "symbolUsed": "INFY",
  "targetPrice1": 1039.81,
  "targetPrice2": 909.32,
  "ticker": "INFY",
  "toResistancePct": 1.74,
  "toSupportPct": -15.24,
  "topHeadlines": [
    "Infosys Share Price News: Price Action and Valuation Check - Univest",
    "Infosys Ltd. $INFY Shares Sold by Robeco Institutional Asset Management B.V. - MarketBeat",
    "… 1 more"
  ],
  "trend": "Uptrend",
  "userType": "Intermediate Investor",
  "volatility": 2.23,
  "volumeHistory": [
    12205669,
    7735811,
    "… 118 more"
  ],
  "volumeLevel": "Normal",
  "volumeRatio": 1.49
}
```
<!-- /sample:analysis-response -->

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

Sample:

<!-- sample:portfolio-response -->
Real output, shortened for reading from [`docs/samples/portfolio_response.json`](../docs/samples/portfolio_response.json) (run `r_20261022_043713_7b0f17`, 1 of 1 decisions by the model). Strings over 160 characters and lists over 2 items are cut; the file itself is unedited.

```json
{
  "advice": [
    "TCS is down 26.1% — review if fundamentals have changed.",
    "INFY is down 23.0% — review if fundamentals have changed.",
    "… 3 more"
  ],
  "diversificationScore": 70,
  "investmentStyle": "Diversified Long-Term Investor",
  "livePriced": 8,
  "meta": {
    "llmAvailable": true,
    "llmCalls": 1,
    "llmFailures": 0,
    "runId": "r_20261022_043713_7b0f17"
  },
  "recommendations": [
    {
      "action": "REVIEW",
      "note": "Down 26.1%; check the reason you bought still holds.",
      "ticker": "TCS"
    },
    {
      "action": "REVIEW",
      "note": "Down 23.0%; check the reason you bought still holds.",
      "ticker": "INFY"
    },
    "… 6 more"
  ],
  "review": {
    "actions": [
      "Review investment theses for deeply negative holdings like ITC and TCS.",
      "Monitor banking sector concentration which forms nearly 30.4% of the portfolio.",
      "… 2 more"
    ],
    "degraded": false,
    "holdings": [
      {
        "action": "REVIEW",
        "reason": "Down 26.1% with an elevated RSI of 86.24, warranting a check on the original thesis.",
        "ticker": "TCS"
      },
      {
        "action": "REVIEW",
        "reason": "Down 23.0% despite an uptrend and high RSI of 76.7, requiring a fundamental check.",
        "ticker": "INFY"
      },
      "… 6 more"
    ],
    "summary": "The portfolio shows an overall loss of 12.8% with moderate diversification across six sectors, though several major holdings are currently in a downtrend. Risk…"
  },
  "riskScore": 20,
  "sectorAllocation": {
    "Banking": 30.4,
    "FMCG": 15.2,
    "IT": 15.9,
    "Infra": 14.1,
    "Oil & Gas": 11.6,
    "Pharma": 12.7
  },
  "skippedRows": [],
  "stocks": [
    {
      "buyPrice": 3400.0,
      "costBasis": 20400.0,
      "currentPrice": 2512.4,
      "currentValue": 15074.4,
      "history": [
        2385.32,
        2433.66,
        "… 58 more"
      ],
      "isHighVol": false,
      "pe": null,
      "pnl": -5325.6,
      "pnlPct": -26.11,
      "priceSource": "live (yfinance)",
      "quantity": 6.0,
      "reason": "Down 26.1%; check the reason you bought still holds.",
      "recommendation": "REVIEW",
      "rsi": 86.24,
      "sector": "IT",
      "ticker": "TCS",
      "trend": "Uptrend",
      "volatility": 2.2,
      "weight": 7.4
    },
    {
      "buyPrice": 1520.0,
      "costBasis": 22800.0,
      "currentPrice": 1170.3,
      "currentValue": 17554.5,
      "history": [
        1105.7,
        1155.6,
        "… 58 more"
      ],
      "isHighVol": false,
      "pe": null,
      "pnl": -5245.5,
      "pnlPct": -23.01,
      "priceSource": "live (yfinance)",
      "quantity": 15.0,
      "reason": "Down 23.0%; check the reason you bought still holds.",
      "recommendation": "REVIEW",
      "rsi": 76.7,
      "sector": "IT",
      "ticker": "INFY",
      "trend": "Uptrend",
      "volatility": 2.23,
      "weight": 8.6
    },
    "… 6 more"
  ],
  "totalCost": 235100.0,
  "totalPnL": -30038.8,
  "totalPnLPct": -12.78,
  "totalValue": 205061.2
}
```
<!-- /sample:portfolio-response -->

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
