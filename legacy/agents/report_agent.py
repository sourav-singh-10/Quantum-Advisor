class ReportAgent:

    def analyze(self, ticker, market, risk, sentiment):
        """
        Generates a plain-text narrative report.

        Parameters
        ----------
        ticker    : str
        market    : dict  (from MarketAgent)
        risk      : dict  (from RiskAgent)
        sentiment : dict  (from NewsSentimentAgent)
        """

        sentiment = sentiment or {}

        news_sentiment  = sentiment.get("newsSentiment", "N/A")
        sentiment_score = sentiment.get("sentimentScore", 0)
        top_headlines   = sentiment.get("topHeadlines", [])
        pos_count       = sentiment.get("positiveCount", 0)
        neg_count       = sentiment.get("negativeCount", 0)

        # Sentiment impact blurb
        if sentiment_score == 1:
            sentiment_impact = "📈 Positive news flow supports the bullish case."
        elif sentiment_score == -1:
            sentiment_impact = "📉 Negative news flow adds downside pressure."
        else:
            sentiment_impact = "➡️ News sentiment is neutral with no strong directional bias."

        # Top headlines block
        if top_headlines:
            headlines_block = "\n".join(f"  • {h}" for h in top_headlines)
        else:
            headlines_block = "  • No recent headlines found."

        text = f"""
========================================
  PORTFOLIO ANALYZER — STOCK REPORT
========================================

Stock    : {ticker}
Price    : {market.get('priceDisplay', market.get('currentPrice', 'N/A'))}
Trend    : {market.get('trend', 'N/A')}
RSI      : {market.get('rsi', 'N/A')}
Volatility: {market.get('volatility', 'N/A')}%

----------------------------------------
RISK ASSESSMENT
----------------------------------------
Risk Level  : {risk.get('riskLevel', 'N/A')}
Risk Score  : {risk.get('riskScore', 'N/A')}
Risk Factors: {', '.join(risk.get('riskFactors', [])) or 'None identified'}

----------------------------------------
NEWS SENTIMENT
----------------------------------------
Overall     : {news_sentiment}
Signal      : {'+' if sentiment_score > 0 else ''}{sentiment_score}
Pos keywords: {pos_count}   Neg keywords: {neg_count}
{sentiment_impact}

Recent Headlines:
{headlines_block}

----------------------------------------
Recommendation based on real-time analysis combining technical
indicators, risk profile, and news sentiment.
========================================
""".strip()

        return {
            "aiReport": text,
        }