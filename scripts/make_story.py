"""Build the home page's "watch one decision" story from a real execution trace.

    python scripts/make_story.py docs/traces/followup_changes_call.jsonl

Writes frontend/samples/story_run.json: the whole trace, unchanged, under "events" (the replay
on the home page and the sample on the trace page play it), plus "beats", the moments the home
page pauses on. Every quoted line is copied verbatim from a field of the trace; the only words
added are the short chapter captions, which say what is happening.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (seq, chapter, caption, field to quote, extra beams drawn at the same moment)
BEATS = [
    (1, "Brief", "A 62-year-old beginner asks about TCS. They want to protect their savings.", None, []),
    (5, "Brief", "The Profile agent turns the answers into limits.", "profileSummary", []),
    (6, "Plan", "The Planner decides what this investor needs to know, and who should find out.", "focus",
     [["Planner", "MarketAnalyst"], ["Planner", "FundamentalsAnalyst"], ["Planner", "NewsAnalyst"]]),
    (12, "Research", "The analysts work in parallel. Each one picks its own data source.", "thought", []),
    (21, "Research", "The market analyst reports a sharp rally, and a warning.", "marketSummary", []),
    (20, "Research", "The fundamentals analyst finds a very healthy company.", "fundamentalsSummary", []),
    (22, "Research", "The news analyst reads 12 headlines. The tone is positive.", "newsSummary", []),
    (23, "Check", "The Planner checks every report before anyone decides.", "reasoning", []),
    (27, "Check", "The risk manager scores the stock against this investor.", "riskSummary", []),
    (29, "Debate", "The strategist drafts a call.", "rationale", []),
    (30, "Debate", "The risk manager is not convinced.", "reasoning", []),
    (31, "Ask", "Instead of guessing, it asks the Planner for evidence.", "question", []),
    (32, "Ask", "The Planner agrees and sends the market analyst back to its tools.", "reasoning",
     [["Planner", "MarketAnalyst"]]),
    (36, "Ask", "A year of prices tells a different story.", "answer", []),
    (37, "Revise", "The strategist changes its call because of the new evidence.", "responses", []),
    (38, "Revise", "This time the risk manager approves.", "reasoning", []),
    (39, "Decide", "The Planner records the decision.", None, []),
    (43, "Decide", "The portfolio agent turns it into an action for this investor.", "portfolioAdvice", []),
]


def inr(n: float) -> str:
    """Indian digit grouping: 1500000 -> 15,00,000."""
    s = f"{int(round(n))}"
    head, tail = s[:-3], s[-3:]
    while len(head) > 2:
        tail = head[-2:] + "," + tail
        head = head[:-2]
    return (head + "," + tail) if head else tail


def quote_of(payload: dict, field: str | None) -> str:
    if field is None:
        return ""
    value = payload.get(field)
    if field == "rationale" and isinstance(value, list):
        return value[2] if len(value) > 2 else value[0]
    if field == "responses" and isinstance(value, list):
        return value[0]["response"]
    if field == "portfolioAdvice" and isinstance(value, list):
        return value[-1]
    return str(value or "")


def main(path: str) -> None:
    events = {e["seq"]: e for e in map(json.loads, Path(path).read_text(encoding="utf-8").splitlines())}
    first = events[min(events)]
    beats = []
    for seq, chapter, caption, field, extra in BEATS:
        e = events[seq]
        p = e["payload"]
        beat = {"seq": seq, "ts": e["ts"][11:19], "from": e["from"], "to": e["to"], "type": e["type"],
                "round": e.get("round"), "chapter": chapter, "caption": caption, "quote": quote_of(p, field),
                "beams": [[e["from"], e["to"]]] + extra}
        if e["type"] in ("draft", "decision") and p.get("recommendation"):
            beat["verdict"] = p["recommendation"]
        if e["type"] == "critique":
            beat["critique"] = p["verdict"]
            if p.get("objections"):
                beat["objection"] = p["objections"][0]["text"]
        if e["type"] == "request":
            beat["quote"] = (f"TCS · age {p['age']} · {p['experience']} · {p['riskAppetite']} · "
                             f"{p['timeHorizon']} · ₹{inr(p['portfolioValue'])} to invest")
        if e["type"] == "decision" and p.get("recommendation"):
            beat["quote"] = f"{p['recommendation']}, {p['confidence']} confidence. {p['decidedBy']}."
        beats.append(beat)
    llm_calls = sum(1 for e in events.values() if isinstance(e.get("llm"), dict))
    llm_ok = sum(1 for e in events.values() if isinstance(e.get("llm"), dict) and e["llm"].get("ok"))
    out = {
        "runId": first["run_id"], "date": first["ts"][:10], "started": first["ts"][11:19],
        "finished": events[max(events)]["ts"][11:19], "messages": len(events),
        "llmDecisions": llm_ok, "llmCalls": llm_calls,
        "source": f"docs/traces/{Path(path).name}", "beats": beats,
        "events": [events[k] for k in sorted(events)],
    }
    dest = ROOT / "frontend" / "samples" / "story_run.json"
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {dest} ({len(beats)} beats from {len(events)} messages)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "docs" / "traces" / "followup_changes_call.jsonl"))
