"""The scripts that turn real captures into documentation samples."""
import json

import pytest

from scripts import capture_run, sample_to_docs


def test_shorten_cuts_long_values_and_drops_the_trace():
    sample = {"aiReport": "x" * 500, "headlines": ["a", "b", "c", "d"], "trace": [{"seq": 1}],
              "meta": {"llmCalls": 17, "llmFailures": 0}}
    short = sample_to_docs.shorten(sample)
    assert "trace" not in short
    assert len(short["aiReport"]) == sample_to_docs.MAX_STR and short["aiReport"].endswith("…")
    assert short["headlines"] == ["a", "b", "… 2 more"]
    assert short["meta"] == sample["meta"]


@pytest.mark.parametrize("meta", [{"llmCalls": 17, "llmFailures": 3}, {"llmCalls": 0, "llmFailures": 0}, {}])
def test_rule_fallback_samples_are_refused(meta):
    with pytest.raises(ValueError):
        sample_to_docs.check_genuine({"meta": meta}, "x.json", allow_rules=False)
    sample_to_docs.check_genuine({"meta": meta}, "x.json", allow_rules=True)


def test_samples_are_written_between_the_markers(tmp_path, monkeypatch):
    doc = tmp_path / "io.md"
    doc.write_text("# IO\n<!-- sample:analysis-response -->\nold\n<!-- /sample:analysis-response -->\nend\n"
                   "<!-- sample:portfolio-response -->\nold\n<!-- /sample:portfolio-response -->\n", encoding="utf-8")
    monkeypatch.setattr(sample_to_docs, "DOC", doc)
    monkeypatch.setattr(sample_to_docs, "ROOT", tmp_path)
    sample = tmp_path / "normal_response.json"
    sample.write_text(json.dumps({"ticker": "TCS", "recommendation": "HOLD",
                                  "meta": {"runId": "r_1", "llmCalls": 15, "llmFailures": 0}}), encoding="utf-8")
    assert sample_to_docs.main(["--analysis", str(sample)]) == 0
    text = doc.read_text(encoding="utf-8")
    assert '"recommendation": "HOLD"' in text and "run `r_1`" in text and "15 of 15 decisions" in text
    assert "old\n<!-- /sample:portfolio-response -->" in text and text.endswith("-->\n")


def test_real_docs_have_both_markers():
    text = sample_to_docs.DOC.read_text(encoding="utf-8")
    for key in ("analysis-response", "portfolio-response"):
        assert f"<!-- sample:{key} -->" in text and f"<!-- /sample:{key} -->" in text


class _Resp:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def json(self):
        return json.loads(json.dumps(self._body))


def test_capture_saves_the_response_and_trace_unedited(tmp_path, monkeypatch, capsys):
    (tmp_path / "docs/samples").mkdir(parents=True)
    (tmp_path / "docs/traces").mkdir(parents=True)
    monkeypatch.setattr(capture_run, "ROOT", tmp_path)
    events = [{"seq": 1, "type": "request"}, {"seq": 2, "type": "final"}]
    capture_run.save("portfolio", _Resp({"stocks": [], "meta": {"runId": "r_2", "llmCalls": 2, "llmFailures": 0},
                                         "trace": events}))
    saved = json.loads((tmp_path / "docs/samples/portfolio_response.json").read_text(encoding="utf-8"))
    lines = (tmp_path / "docs/traces/portfolio.jsonl").read_text(encoding="utf-8").splitlines()
    assert "trace" not in saved and [json.loads(x) for x in lines] == events
    assert "2 of 2 decisions by the model" in capsys.readouterr().out
