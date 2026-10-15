"""News analyst: picks a news source, then labels each headline with the LLM."""
from __future__ import annotations

from agents.base import BaseAgent, Tool
from core.schemas import HeadlineLabel, NewsView
from tools.news_data import SOURCES, get_headlines, keyword_sentiment

SCORE = {"Positive": 1, "Neutral": 0, "Negative": -1}


class NewsAnalyst(BaseAgent):
    name = "NewsAnalyst"
    system = ("You are a financial news analyst. Get recent headlines about the company "
              "(try another source if one fails or returns irrelevant items), then judge "
              "each headline's sentiment and whether it is material to the share price.")

    def run(self, ctx, ticker: str, instruction: str = "") -> dict:
        query = f"{ticker} share"
        tool = Tool(
            name="get_headlines",
            description=f"recent headlines for '{query}'; argument = one of {', '.join(SOURCES)}",
            run=lambda src: get_headlines(query, src),
            summarize=lambda items: f"{len(items)} headlines, e.g. '{items[0]['title'][:90]}'",
        )
        default = [(tool.name, s) for s in SOURCES]
        observations = self.tool_loop(ctx, f"Collect news on {ticker}. {instruction}".strip(),
                                      [tool], default, lambda obs: any(o["ok"] for o in obs))
        success = next((o for o in observations if o["ok"]), None)
        if not success:
            return {"newsSentiment": "Neutral", "sentimentScore": 0, "headlineCount": 0,
                    "topHeadlines": [], "newsSummary": "No news source was reachable.",
                    "newsAvailable": False}

        items = success["result"][:12]
        titles = [i["title"] for i in items]
        kw = keyword_sentiment(titles)

        def fallback():
            return NewsView(
                labels=[HeadlineLabel(index=i, sentiment="Neutral", material=False)
                        for i in range(len(titles))],
                overall=kw["newsSentiment"],
                summary=f"Keyword scan: {kw['positiveCount']} positive vs "
                        f"{kw['negativeCount']} negative terms.")

        numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(titles))
        view, meta = self.decide(
            ctx, f"Headlines about {ticker}:\n{numbered}\nLabel every headline and give the "
                 f"overall sentiment for the stock. Ignore headlines not about this company.",
            NewsView, fallback)
        material = [titles[l.index] for l in view.labels
                    if l.material and 0 <= l.index < len(titles)]
        return {"newsSentiment": view.overall, "sentimentScore": SCORE[view.overall],
                "headlineCount": len(titles), "newsSource": success["argument"],
                "materialHeadlines": material[:5], "topHeadlines": titles[:3],
                "newsSummary": view.summary, "newsAvailable": True, "_llm": meta}
