# Quantum Advisor — Project Synopsis

Quantum Advisor is an educational investment-analysis decision-support prototype. Investors often need to consider market trends, technical indicators, news sentiment, risk tolerance, and portfolio constraints separately. The project brings these signals together into one consolidated analysis to make the information easier to understand.

The application uses a Flask backend and a custom orchestrator to coordinate specialized components, including User, Market, Fundamentals, News Sentiment, Risk, Strategy, Portfolio, and Report agents. The Market Agent retrieves price history from configured data providers, while the Risk Agent assesses risk and reviews the initial strategy. The Strategy Agent generates a recommendation using the implemented decision logic, with Gemini used to provide explanatory text when configured and available. The Portfolio and Report agents help prepare the final result for the user.

The system is intended for educational demonstrations of multi-agent coordination and investment-analysis workflows. Market-data availability depends on external APIs, and the current Fundamentals Agent returns placeholder values rather than verified financial metrics. Recommendations may rely on rule-based logic and should not be treated as professional financial advice.
