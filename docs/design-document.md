# Quantum Advisor — Design Document

## 1. Architecture

Quantum Advisor uses a custom orchestrator-worker pattern. The Flask application receives the user's request and invokes the orchestrator, which coordinates specialized agents and combines their outputs into a final report.

Architecture diagram: `architecture.svg`

Main flow:

1. User Interface → Flask Application
2. Flask Application → Orchestrator
3. Orchestrator → User Agent, Market Agent, Fundamentals Agent, News Sentiment Agent
4. Their outputs feed into Risk Assessment
5. Strategy Agent generates an initial recommendation
6. Risk Agent reviews the strategy and can request revision when the implemented conditions require it
7. Portfolio Agent processes the available analysis
8. Report Agent consolidates the final output

The actual execution order and branching should be interpreted from `orchestrator.py` and the genuine execution trace.

## 2. Component Responsibilities

- **User Agent:** Processes investor profile information and risk-capacity inputs.
- **Market Agent:** Retrieves available price history and calculates indicators such as trend, RSI, and volatility.
- **Fundamentals Agent:** Currently returns placeholder fundamental metrics; these are not verified financial data.
- **News Sentiment Agent:** Supplies the sentiment result available from the configured news pipeline.
- **Risk Agent:** Calculates a risk assessment and reviews the proposed strategy.
- **Strategy Agent:** Produces a recommendation using the implemented decision logic and may use Gemini to generate explanatory text.
- **Portfolio Agent:** Produces portfolio-oriented analysis from available inputs.
- **Report Agent:** Consolidates the analysis into the final response.
- **Orchestrator:** Coordinates execution and records run events.

## 3. Coordination and Adaptation

The orchestrator passes structured outputs between components. The Risk Agent reviews the initial strategy. When the implemented risk conditions require revision, the workflow can request a revised recommendation; otherwise it continues to portfolio analysis and reporting.

The execution trace records actual events such as agent completion, risk assessment, strategy review, and run completion. The current trace format records event metadata rather than every full inter-agent message.

## 4. Technology Choices

- **Python:** Main implementation language.
- **Flask:** HTTP backend for the application.
- **Pandas and NumPy:** Price-series and indicator calculations.
- **Requests:** External API calls.
- **Google GenAI SDK:** Optional Gemini-generated explanation.
- **pytest:** Automated tests.
- **Git and GitHub:** Version control and source review.
- **Render:** Hosted application deployment.

## 5. Input and Output Contracts

The system accepts a stock ticker and investor-profile fields supported by the application. Its output can include market price, trend, RSI, volatility, risk assessment, recommendation, portfolio insights, and a consolidated report.

Refer to `agent-io-schemas.md` for the detailed schemas and sample payloads. Confirm each field against the current implementation before submission.

## 6. Limitations

- Market data depends on external providers, their API keys, quotas, and supported symbols.
- The Fundamentals Agent currently uses placeholder values.
- Strategy recommendations use implemented decision logic; Gemini is used for explanatory text rather than being the sole decision-maker.
- Execution traces record events but do not capture every full message exchanged between agents.
- The application is an educational prototype and does not provide professional investment advice.
