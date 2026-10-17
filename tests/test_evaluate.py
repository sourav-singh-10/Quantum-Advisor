"""The evaluation script reads only what the server returned and reports it faithfully."""
import importlib.util
from argparse import Namespace
from pathlib import Path

spec = importlib.util.spec_from_file_location("evaluate", Path(__file__).resolve().parents[1] / "scripts" / "evaluate.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def body(rec, first, pct, llm_ok=True, followups=0):
    return {"recommendation": rec, "confidence": "Moderate", "positionSizing": {"positionPct": pct},
            "debate": [{"draft": {"recommendation": first}, "critique": {"objections": [{"id": "G1"}]}}],
            "meta": {"runId": "r1", "debateRounds": 2 if first != rec else 1, "replans": 0, "followups": followups},
            "trace": [{"type": "decision", "llm": {"ok": llm_ok}, "payload": {}},
                      {"type": "decision", "payload": {"note": "Ignored 1 headline(s) written as instructions to an AI"}},
                      {"type": "assessment", "payload": {"confidence_cap": "Low"}}], "_seconds": 12.0}


def test_summary_counts_come_from_the_response():
    s = ev.summarise(body("HOLD", "BUY", 0.0, llm_ok=False, followups=1))
    assert s["debateChanged"] and s["ruleDecisions"] == 1 and s["llmDecisions"] == 0
    assert s["guardrailVetoes"] == 1 and s["confidenceCapped"] and s["injectionNotes"] == 1 and s["followups"] == 1
    assert ev.summarise({"error": "Invalid input", "details": [{"field": "age", "message": "too low"}]})["error"] \
        == "Invalid input (age: too low)"


def test_report_measures_consistency_and_personalisation(tmp_path):
    rows = []
    for rep in (1, 2):
        rows.append({"repeat": rep, "ticker": "TCS", "profile": "Cautious retiree", "s": ev.summarise(body("HOLD", "HOLD", 0.0))})
        rows.append({"repeat": rep, "ticker": "TCS", "profile": "Balanced saver",
                     "s": ev.summarise(body("BUY" if rep == 1 else "HOLD", "BUY", 4.0))})
    md = ev.report(rows, Namespace(url="http://x", stocks=["TCS"], repeats=2, out=str(tmp_path / "e.md")))
    assert "| Same input, same recommendation (model runs only) | 1 of 2 stock-profile pairs (50%) |" in md
    assert "| Profiles got different position sizes (model runs only) | 2 of 2 stock runs (100%) |" in md
    assert "TCS, Balanced saver: BUY, HOLD" in md


def test_cut_off_runs_are_marked_and_left_out_of_comparisons(tmp_path):
    model = ev.summarise(body("HOLD", "HOLD", 0.0))
    rules = ev.summarise({**body("BUY", "BUY", 4.0, llm_ok=False)})
    assert not ev.limited(model) and ev.limited(rules)
    rows = [{"repeat": 1, "ticker": "TCS", "profile": "Cautious retiree", "s": model},
            {"repeat": 2, "ticker": "TCS", "profile": "Cautious retiree", "s": rules}]
    md = ev.report(rows, Namespace(url="http://x", stocks=["TCS"], repeats=2, out=str(tmp_path / "e.md")))
    assert "| Runs where the model was cut off (over 20% rule decisions) | 1 of 2 |" in md
    assert "not measured (needs two model runs" in md and "1 / 0 (cut off)" not in md and "0 / 1 (cut off)" in md
