"""News analyst: picks a news source, then labels each headline with the LLM."""
from __future__ import annotations

from agents.base import BaseAgent, Tool
from core.schemas import HeadlineLabel, NewsView
from tools.news_data import SOURCES, get_headlines, keyword_sentiment
from tools.safety import is_suspicious, untrusted

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
        blocked = [i["title"] for i in items if is_suspicious(i["title"])]
        if blocked:
            ctx.emit(self.name, "Planner", "decision",
                     {"note": f"Ignored {len(blocked)} headline(s) written as instructions to an AI: "
                              f"'{blocked[0][:100]}'"})
            items = [i for i in items if not is_suspicious(i["title"])]
            if not items:
                return {"newsSentiment": "Neutral", "sentimentScore": 0, "headlineCount": 0,
                        "topHeadlines": [], "newsSummary": "Only unusable headlines were found.",
                        "newsAvailable": False}
        titles = [i["title"] for i in items]
        kw = keyword_sentiment(titles)

        def fallback():
            return NewsView(
                labels=[HeadlineLabel(index=i, sentiment=keyword_sentiment([t])["newsSentiment"],
                                      material=False)
                        for i, t in enumerate(titles)],
                overall=kw["newsSentiment"],
                summary=f"Keyword scan: {kw['positiveCount']} positive vs "
                        f"{kw['negativeCount']} negative terms.")

        numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(titles))
        view, meta = self.decide(
            ctx, f"Headlines about {ticker}:\n{untrusted(numbered, 'news headlines')}\nLabel every headline and give the "
                 f"overall sentiment for the stock. Ignore headlines not about this company.",
            NewsView, fallback)
        material = [titles[lab.index] for lab in view.labels
                    if lab.material and 0 <= lab.index < len(titles)]
        by_index = {lab.index: lab for lab in view.labels if 0 <= lab.index < len(titles)}
        labels = [{"title": t, "source": items[i].get("source"),
                   "sentiment": by_index[i].sentiment if i in by_index else "Neutral",
                   "material": bool(by_index[i].material) if i in by_index else False}
                  for i, t in enumerate(titles)]
        return {"newsSentiment": view.overall, "sentimentScore": SCORE[view.overall],
                "headlineCount": len(titles), "newsSource": success["argument"],
                "materialHeadlines": material[:5], "topHeadlines": titles[:3],
                "headlineLabels": labels,
                "newsSummary": view.summary, "newsAvailable": True, "_llm": meta}

    # ------------------------------------------------------------ follow-up questions
    def followup_facts(self, ctx, ticker: str, question: str, previous: dict):
        """Re-read recent headlines, keeping only those that name this company."""
        from tools import symbols
        from tools.news_watch import company_news, name_keys
        name = symbols.name_for(ticker)
        recent = self.use_tool(ctx, "company_news", f"{ticker} last 4 days",
                               lambda: company_news(ticker, name, max_age_hours=96),
                               lambda v: f"{len(v)} headlines that name {ticker}")
        facts = [f"Company names checked: {', '.join(name_keys(ticker, name))}"]
        material = previous.get("materialHeadlines") or []
        for t in material[:4]:
            about = any(k.lower() in t.lower() for k in name_keys(ticker, name))
            facts.append(f"Earlier material headline: '{t}' - "
                         f"{'names the company' if about else 'does not name the company'}")
        for h in (recent or [])[:5]:
            facts.append(f"[{h['tone']}{', may move the price' if h['material'] else ''}] {h['title']}")
        if recent is None:
            rule = "News could not be re-checked; the earlier reading stands."
        else:
            neg = [h for h in recent if h["tone"] == "Negative" and h["material"]]
            rule = (f"{len(recent)} recent headlines name {ticker}; {len(neg)} are negative and "
                    f"could move the price." if recent else
                    f"No recent headline names {ticker} directly, so the earlier news reading "
                    f"carries little weight.")
        return facts, rule
