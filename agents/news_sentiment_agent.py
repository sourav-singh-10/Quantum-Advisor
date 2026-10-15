import requests
from config import NEWS_API_KEY


class NewsSentimentAgent:
    """
    Fetches recent news headlines for a stock ticker and scores overall
    sentiment as Positive / Neutral / Negative with a numeric contribution
    value (+1 / 0 / -1) that other agents can use to adjust their signals.
    """

    POSITIVE_KEYWORDS = [
        "surge", "soar", "rally", "beat", "record", "profit", "growth",
        "upgrade", "buy", "strong", "bullish", "gain", "rise", "breakout",
        "outperform", "expansion", "dividend", "acquisition", "partnership",
        "launch", "award", "approval", "deal", "contract", "innovation",
    ]

    NEGATIVE_KEYWORDS = [
        "fall", "drop", "plunge", "miss", "loss", "decline", "downgrade",
        "sell", "weak", "bearish", "crash", "fraud", "lawsuit", "recall",
        "investigation", "fine", "penalty", "bankruptcy", "default", "layoff",
        "cut", "risk", "warning", "debt", "concern", "probe", "scandal",
    ]

    # ------------------------------------------------------------------ #
    #  News fetch                                                          #
    # ------------------------------------------------------------------ #

    def fetch_headlines(self, ticker: str) -> list[str]:
        """Return up to 10 headline strings for the ticker."""

        url = "https://newsapi.org/v2/everything"

        params = {
            "q": ticker,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 10,
            "apiKey": NEWS_API_KEY,
        }

        try:
            r = requests.get(url, params=params, timeout=8)
            data = r.json()

            articles = data.get("articles", [])

            headlines = []
            for a in articles:
                title = a.get("title") or ""
                desc  = a.get("description") or ""
                # combine title + description for richer signal
                headlines.append(f"{title}. {desc}")

            return headlines

        except Exception as e:
            print(f"[NewsSentimentAgent] News fetch failed: {e}")
            return []

    # ------------------------------------------------------------------ #
    #  Sentiment scoring                                                   #
    # ------------------------------------------------------------------ #

    def score_headlines(self, headlines: list[str]) -> dict:
        """
        Simple keyword-based sentiment scoring.

        Returns
        -------
        {
            "newsSentiment":    "Positive" | "Neutral" | "Negative",
            "sentimentScore":   int  (positive=+1, neutral=0, negative=-1),
            "positiveCount":    int,
            "negativeCount":    int,
            "headlineCount":    int,
            "topHeadlines":     list[str],   # first 3 headlines
        }
        """

        if not headlines:
            return {
                "newsSentiment":  "Neutral",
                "sentimentScore": 0,
                "positiveCount":  0,
                "negativeCount":  0,
                "headlineCount":  0,
                "topHeadlines":   [],
            }

        pos = 0
        neg = 0

        for h in headlines:
            lower = h.lower()
            pos += sum(1 for w in self.POSITIVE_KEYWORDS if w in lower)
            neg += sum(1 for w in self.NEGATIVE_KEYWORDS if w in lower)

        if pos > neg:
            sentiment = "Positive"
            score     = 1
        elif neg > pos:
            sentiment = "Negative"
            score     = -1
        else:
            sentiment = "Neutral"
            score     = 0

        return {
            "newsSentiment":  sentiment,
            "sentimentScore": score,
            "positiveCount":  pos,
            "negativeCount":  neg,
            "headlineCount":  len(headlines),
            "topHeadlines":   [h.split(".")[0] for h in headlines[:3]],
        }

    # ------------------------------------------------------------------ #
    #  Public interface                                                    #
    # ------------------------------------------------------------------ #

    def analyze(self, ticker: str) -> dict:
        headlines = self.fetch_headlines(ticker)
        return self.score_headlines(headlines)