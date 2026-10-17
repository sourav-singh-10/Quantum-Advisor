"""Document analyst: reads the company document the investor uploaded.

It decides which pages to read (search, then read), extracts the reported figures, and
afterwards challenges the Fundamentals analyst when the document and the live data
disagree. Every figure it reports must be printed in the document: an LLM figure that
cannot be found on the pages it read is replaced by the rule-based value or dropped.
"""
from __future__ import annotations

import re

from agents.base import BaseAgent, Tool
from core.schemas import DocumentFigures, DocumentFindings
from tools import document_data as dd
from tools.base import ToolError
from tools.safety import untrusted

MONEY = ("revenue", "netProfit", "borrowings", "equity")


class DocumentAnalyst(BaseAgent):
    name = "DocumentAnalyst"
    system = ("You are a financial document analyst. The investor uploaded a company document "
              "(annual report, quarterly results or balance sheet). Find the pages with the "
              "income statement and the balance sheet, read them, and report the figures for "
              "the latest period exactly as printed. Never estimate a figure that is not on "
              "the page; leave it empty instead.")

    # ------------------------------------------------------------ analysis
    def run(self, ctx, ticker: str, instruction: str = "") -> dict:
        doc = ctx.document
        if not doc:
            raise ToolError("no document was attached to this request")

        tools = [
            Tool("find_pages", f"search the {len(doc['pages'])}-page document; argument = a few "
                 "words, e.g. 'statement of profit and loss revenue'",
                 run=lambda q: dd.search_pages(doc, q),
                 summarize=lambda r: "; ".join(f"p{x['page']} (score {x['score']}): "
                                               f"{x['snippet'][:70]}" for x in r[:4])),
            Tool("read_page", "read one page; argument = page number",
                 run=lambda n: dd.read_page(doc, n),
                 summarize=lambda r: f"page {r['page']}, unit {r['unit'] or 'not stated'}, "
                                     f"{len(r['text'])} chars: {' '.join(r['text'][:120].split())}"),
        ]
        default = [("find_pages", "statement of profit and loss revenue from operations profit"),
                   ("find_pages", "balance sheet borrowings total equity")]
        pages_read = lambda obs: [o for o in obs if o["ok"] and o["tool"] == "read_page"]
        goal = (f"Find and read the pages of '{doc['name']}' that show {ticker}'s revenue, net "
                f"profit, EPS, borrowings and total equity for the latest period. Read at most "
                f"3 pages. {instruction}".strip())
        obs = self.tool_loop(ctx, goal, tools, default, lambda o: len(pages_read(o)) >= 2)

        # If the loop only searched (no LLM, or it stopped early), read the best hits.
        if len(pages_read(obs)) < 2:
            hits = [h for o in obs if o["ok"] and o["tool"] == "find_pages" for h in o["result"]]
            already = {o["result"]["page"] for o in pages_read(obs)}
            for h in sorted(hits, key=lambda h: -h["score"]):
                if len(pages_read(obs)) >= 3:
                    break
                if h["page"] not in already:
                    already.add(h["page"])
                    self._call(ctx, tools[1], str(h["page"]), obs, thought="read the best match")
        read = [(o["result"]["page"], doc["pages"][o["result"]["page"] - 1]) for o in pages_read(obs)]
        if not read:
            raise ToolError("could not find the financial statements in the document")

        # Rules first: they are the fallback and the check on the LLM.
        ctx.emit(self.name, "tool:extract_figures", "tool_call",
                 {"argument": f"pages {[p for p, _ in read]}"})
        rule_figs = dd.extract_figures(read)
        if len(rule_figs) < 3:          # statements were elsewhere; scan the whole document
            rule_figs = {**dd.extract_figures(list(enumerate(doc["pages"], 1))), **rule_figs}
        flags = dd.scan_red_flags(doc)
        injected = doc.get("injections") or []
        if injected:
            pages_hit = sorted({x["page"] for x in injected})
            ctx.emit(self.name, "Planner", "decision",
                     {"note": f"Ignored {len(injected)} line(s) on page(s) {pages_hit} that were written "
                              f"as instructions to an AI (e.g. '{injected[0]['text'][:90]}'). They were "
                              "removed before any agent read the document."})
            flags = flags + [{"flag": f"Text addressed to an AI system on page {p} was ignored",
                              "page": p} for p in pages_hit[:2]]
        ctx.emit("tool:extract_figures", self.name, "tool_result",
                 {"ok": True, "figures": {k: v["value"] for k, v in rule_figs.items()},
                  "redFlags": [f["flag"] for f in flags]})

        def fallback():
            figs = DocumentFigures(**{k: v["value"] for k, v in rule_figs.items()},
                                   unit="crore" if any(v["unit"] == "₹ crore"
                                                       for v in rule_figs.values()) else None)
            ratios = dd.derived_ratios({k: v for k, v in rule_figs.items()
                                        if k in MONEY and v["unit"] == "₹ crore"})
            parts = []
            if "revenue" in rule_figs:
                parts.append(f"revenue {rule_figs['revenue']['value']:,.0f}")
            if "netProfit" in rule_figs:
                parts.append(f"net profit {rule_figs['netProfit']['value']:,.0f}")
            if "profitMargin" in ratios:
                parts.append(f"a {ratios['profitMargin']:.1f}% margin")
            if "de" in ratios:
                parts.append(f"debt/equity {ratios['de']:.2f}")
            pages = ", ".join(str(p) for p in sorted({v["page"] for v in rule_figs.values()}))
            summary = (f"The statements on page{'s' if ',' in pages else ''} {pages} show "
                       + ", ".join(parts) + "." if parts else
                       "The statements could not be read with the rule-based parser.")
            if flags:
                summary += f" Flag: {flags[0]['flag'].lower()} (p{flags[0]['page']})."
            return DocumentFindings(
                about_company=dd.mentions_company(doc, ticker),
                figures=figs, key_points=[],
                red_flags=[f["flag"] for f in flags],
                summary=summary)

        excerpt = "\n\n".join(untrusted(t[:3000], f"document page {p}") for p, t in read[:3])
        prompt = (f"Stock: {ticker}. Document: {doc['name']} ({doc['pageCount']} pages).\n"
                  f"Rule-based extraction found: "
                  f"{ {k: (v['value'], 'p' + str(v['page'])) for k, v in rule_figs.items()} }.\n"
                  f"Possible red flags found by keyword: {[f['flag'] for f in flags] or 'none'}.\n"
                  f"Pages read:\n{excerpt}\n\nReport the latest-period figures exactly as printed "
                  "(in the unit printed on the page), whether the document is about this "
                  "company, key points, and real red flags only.")
        findings, meta = self.decide(ctx, prompt, DocumentFindings, fallback)

        # Guardrail: every LLM figure must be printed on a page that was read.
        text = "\n".join(t for _, t in read)
        figures = findings.figures.model_dump()
        rejected = []
        for key in ("revenue", "netProfit", "eps", "borrowings", "equity"):
            v = figures.get(key)
            if v is not None and meta.get("ok") and not dd.appears_in(v, text):
                rejected.append(dd.FIGURE_NAMES[key])
                figures[key] = None
        if rejected:
            ctx.emit(self.name, self.name, "decision",
                     {"note": f"Dropped figures not printed in the document: {rejected}"})

        # Convert money to crore for comparison with the live data.
        unit = re.sub(r"[^a-z ]", " ", (figures.get("unit") or "").lower())
        factor = next((f for k, f in dd._TO_CRORE.items() if k in unit.split()
                       or any(w.startswith(k) for w in unit.split())), None)
        if meta.get("ok"):
            in_crore = {k: {"value": round(figures[k] * factor, 2), "page": None}
                        for k in MONEY if figures.get(k) is not None and factor}
        else:
            in_crore = {k: v for k, v in rule_figs.items() if k in MONEY and v["unit"] == "₹ crore"}
        derived = dd.derived_ratios(in_crore)

        shown = {dd.FIGURE_NAMES[k]: figures[k] for k in ("revenue", "netProfit", "eps",
                                                         "borrowings", "equity")
                 if figures.get(k) is not None}
        return {
            "documentAvailable": True,
            "documentName": doc["name"],
            "documentPages": doc["pageCount"],
            "documentPagesUsed": [p for p, _ in read],
            "documentPeriod": figures.get("period"),
            "documentUnit": figures.get("unit"),
            "documentFigures": shown,
            "documentRatios": derived,
            # The model chooses the red flags it thinks matter, but a planted instruction is always
            # reported: it is a fact about the document, not a judgement.
            "documentRedFlags": findings.red_flags + [
                f["flag"] for f in flags if "addressed to an AI" in f["flag"]
                and f["flag"] not in findings.red_flags],
            # Rules can only confirm a match by symbol; "not found" stays undecided (None)
            # until the cross-check can compare with the company's registered name.
            "documentAboutCompany": findings.about_company if meta.get("ok")
                                    else (True if findings.about_company else None),
            "documentPoints": findings.key_points,
            "documentSummary": findings.summary,
            "_llm": meta,
        }

    # ------------------------------------------------------------ cross-check
    def challenge(self, ctx, document: dict, fundamentals: dict, ticker: str) -> list[dict]:
        """Compare the document with the live fundamentals and raise any disagreement."""
        if document.get("documentAboutCompany") is None and ctx.document:
            document["documentAboutCompany"] = dd.mentions_company(
                ctx.document, ticker, fundamentals.get("companyName"))
        if document.get("documentAboutCompany") is False:
            issue = {"metric": "company", "text": f"The document does not appear to be about "
                     f"{fundamentals.get('companyName') or ticker}; its figures were not used"}
            ctx.emit(self.name, "Planner", "challenge", {"issues": [issue["text"]]})
            document["documentRatios"] = {}
            return [issue]
        ctx.emit(self.name, "tool:compare_with_live", "tool_call",
                 {"argument": f"document {document['documentRatios']} vs live "
                              f"margin {fundamentals.get('profitMargin')}, D/E {fundamentals.get('de')}"})
        issues = dd.compare_with_live(document["documentRatios"], fundamentals)
        ctx.emit("tool:compare_with_live", self.name, "tool_result",
                 {"ok": True, "issues": [i["text"] for i in issues]})
        if issues:
            ctx.emit(self.name, "FundamentalsAnalyst", "challenge",
                     {"issues": [i["text"] for i in issues],
                      "question": "Which figures should the committee rely on?"})
        return issues

    # ------------------------------------------------------------ follow-up questions
    def followup_facts(self, ctx, ticker: str, question: str, previous: dict):
        """Search the uploaded document for the question's words and read the best page."""
        doc = ctx.document
        if not doc:
            return ["No document was attached."], "No document was attached, so it cannot answer this."
        hits = self.use_tool(ctx, "find_pages", question[:80], lambda: dd.search_pages(doc, question, 3),
                             lambda v: "pages " + ", ".join(str(h["page"]) for h in v))
        facts = [f"Page {h['page']}: …{h['snippet']}…" for h in (hits or [])]
        if hits:
            page = self.use_tool(ctx, "read_page", str(hits[0]["page"]),
                                 lambda: dd.read_page(doc, hits[0]["page"], 900),
                                 lambda v: f"page {v['page']}, {len(v['text'])} characters")
            if page:
                facts.append(f"Page {page['page']} text: {' '.join(page['text'].split())[:700]}")
            rule = f"The document discusses this on page {hits[0]['page']}: …{hits[0]['snippet']}…"
        else:
            rule = "The document does not appear to discuss this."
        return facts, rule
