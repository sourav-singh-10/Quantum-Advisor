"""Document analyst: reading a company PDF, guarding against invented figures, and
challenging the live fundamentals when the two disagree."""
import io
from pathlib import Path

import pytest

from agents.document_agent import DocumentAnalyst
from core.runner import run_analysis
from core.schemas import AnalyzeRequest
from tests.agent_helpers import make_ctx
from tests.fakes import FUNDAMENTALS, FakeLLM, patch_data
from tools import document_data as dd
from tools.base import ToolError

FIXTURES = Path(__file__).parent / "fixtures"
REPORT = (FIXTURES / "demo_annual_report.pdf").read_bytes()


def doc():
    return dd.load_pdf(REPORT, "demo_annual_report.pdf")


# ------------------------------------------------------------------ tools
def test_rules_read_the_statements_in_crore():
    d = doc()
    figs = dd.extract_figures(list(enumerate(d["pages"], 1)))
    assert figs["revenue"]["value"] == 12450.75 and figs["revenue"]["page"] == 4   # skips "Note 23"
    assert figs["netProfit"]["value"] == 1245.6
    assert figs["eps"]["value"] == 24.91
    assert figs["borrowings"]["value"] == 2800.0            # non-current + current
    assert figs["equity"]["value"] == 9875.2
    assert dd.derived_ratios(figs) == {"profitMargin": 10.0, "de": 0.28}


def test_only_real_red_flags_are_raised():
    flags = [f["flag"] for f in dd.scan_red_flags(doc())]
    # "going concern basis" and "contingent liabilities" are routine wording, not flags
    assert flags == ["Auditor gave a qualified opinion"]


@pytest.mark.parametrize("data,message", [
    (b"", "empty"), (b"hello world", "not a PDF"),
    ((FIXTURES / "scanned.pdf").read_bytes(), "no readable text"),
])
def test_unusable_files_are_refused(data, message):
    with pytest.raises(ToolError, match=message):
        dd.load_pdf(data)


def test_page_tools_validate_their_argument():
    d = doc()
    assert dd.search_pages(d, "balance sheet borrowings")[0]["page"] == 5
    assert dd.read_page(d, "p4")["unit"] == "crore"
    with pytest.raises(ToolError):
        dd.read_page(d, 99)


def test_appears_in_ignores_commas_but_not_digits():
    text = "Revenue from operations 23 12,450.75"
    assert dd.appears_in(12450.75, text) and not dd.appears_in(2450.75, text)


# ------------------------------------------------------------------ agent
def test_without_llm_the_agent_reads_the_best_pages(tmp_path):
    ctx, _ = make_ctx(tmp_path, available=False)
    ctx.document = doc()
    out = DocumentAnalyst().run(ctx, "DEMOIND")
    assert set(out["documentPagesUsed"]) >= {4, 5}
    assert out["documentFigures"]["Revenue"] == 12450.75
    assert out["documentRatios"] == {"profitMargin": 10.0, "de": 0.28}
    assert out["documentRedFlags"] == ["Auditor gave a qualified opinion"]
    assert out["documentAboutCompany"] is True


def test_llm_chooses_pages_and_invented_figures_are_dropped(tmp_path):
    steps = [{"thought": "find the P&L", "action": "find_pages", "argument": "profit and loss"},
             {"thought": "read it", "action": "read_page", "argument": "4"},
             {"thought": "balance sheet", "action": "read_page", "argument": "5"}]
    findings = {"about_company": True, "summary": "Profitable, modest debt.",
                "key_points": ["Revenue grew 13%"], "red_flags": ["Qualified audit opinion"],
                "figures": {"period": "FY 2025-26", "unit": "Rs. in crore", "revenue": 12450.75,
                            "netProfit": 1999.0,            # not in the document
                            "eps": 24.91, "borrowings": 2800.0, "equity": 9875.2}}
    ctx, llm = make_ctx(tmp_path, {("DocumentAnalyst", "ToolStep"): steps,
                                   ("DocumentAnalyst", "DocumentFindings"): [findings]})
    ctx.document = doc()
    out = DocumentAnalyst().run(ctx, "DEMOIND")
    assert out["documentPagesUsed"] == [4, 5]
    assert "Net profit" not in out["documentFigures"]
    assert out["documentFigures"]["Revenue"] == 12450.75
    assert any(e["type"] == "decision" and "Net profit" in str(e["payload"])
               for e in ctx.tracer.events)
    assert "page 4" in llm.calls[-1][2]          # the LLM saw the page text it reports from


def test_no_document_is_a_tool_error(tmp_path):
    ctx, _ = make_ctx(tmp_path, available=False)
    with pytest.raises(ToolError):
        DocumentAnalyst().run(ctx, "DEMOIND")


# ------------------------------------------------------------------ in the team
REQ = AnalyzeRequest(ticker="DEMOIND", age=45, riskAppetite="Moderate",
                     timeHorizon="Long-term").model_dump()


def test_document_conflict_is_challenged_and_settled(monkeypatch):
    live = {**FUNDAMENTALS, "profitMargin": 18.0}       # document says 10.0%
    patch_data(monkeypatch, fundamentals=live, headlines=["Demo Industries posts results"])
    out = run_analysis(REQ, llm=FakeLLM(available=False), document=doc())
    types = [(e["from"], e["to"], e["type"]) for e in out["trace"]]
    assert ("Planner", "DocumentAnalyst", "task") in types
    assert ("DocumentAnalyst", "FundamentalsAnalyst", "challenge") in types
    assert ("FundamentalsAnalyst", "DocumentAnalyst", "reply") in types
    assert ("Planner", "team", "reconciliation") in types
    assert out["documentConflicts"] and "Profit margin" in out["documentConflicts"][0]
    assert "Document: Auditor gave a qualified opinion" in out["riskFactors"]
    assert out["confidence"] != "High"


def test_agreeing_document_skips_the_challenge(monkeypatch):
    live = {**FUNDAMENTALS, "profitMargin": 10.5, "de": 0.3}
    patch_data(monkeypatch, fundamentals=live, headlines=["Demo Industries posts results"])
    out = run_analysis(REQ, llm=FakeLLM(available=False), document=doc())
    assert not any(e["type"] == "challenge" for e in out["trace"])
    assert out["documentConflicts"] == [] and out["documentAvailable"] is True


def test_planner_cannot_plan_the_document_agent_without_a_document(monkeypatch):
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=["x"])
    plan = {"reasoning": "r", "focus": "f",
            "tasks": [{"agent": "MarketAnalyst", "instruction": "trend"},
                      {"agent": "DocumentAnalyst", "instruction": "read it"}]}
    out = run_analysis(REQ, llm=FakeLLM({("Planner", "Plan"): [plan]}))
    tasks = [e["to"] for e in out["trace"] if e["type"] == "task" and e["from"] == "Planner"]
    assert "DocumentAnalyst" not in tasks and out["documentAvailable"] is False


# ------------------------------------------------------------------ API
@pytest.fixture
def client(monkeypatch):
    import config
    monkeypatch.setattr(config, "REQUIRE_LOGIN", False)
    import app as app_module
    app_module.init_db()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


FORM = {"ticker": "DEMOIND", "age": "45", "portfolioValue": "500000",
        "riskAppetite": "Moderate", "timeHorizon": "Long-term", "experience": "Intermediate"}


def test_api_accepts_a_pdf_with_the_form(client, monkeypatch):
    patch_data(monkeypatch, fundamentals=FUNDAMENTALS, headlines=["x"])
    res = client.post("/api/analyze", content_type="multipart/form-data",
                      data={**FORM, "document": (io.BytesIO(REPORT), "report.pdf")})
    body = res.get_json()
    assert res.status_code == 200 and body["documentName"] == "report.pdf"


@pytest.mark.parametrize("name,data", [("report.docx", b"PK.."),
                                       ("scan.pdf", (FIXTURES / "scanned.pdf").read_bytes())])
def test_api_refuses_unusable_documents(client, name, data):
    res = client.post("/api/analyze", content_type="multipart/form-data",
                      data={**FORM, "document": (io.BytesIO(data), name)})
    assert res.status_code == 400
    assert res.get_json()["details"][0]["field"] == "document"


def test_company_is_matched_by_name_when_the_symbol_is_not_printed():
    d = {"name": "ar.pdf", "pages": ["Infosys Limited Integrated Annual Report 2025-26"]}
    assert dd.mentions_company(d, "INFY", "Infosys Limited")
    assert not dd.mentions_company(d, "TCS", "Tata Consultancy Services Limited")


def test_wrong_company_document_is_not_used(monkeypatch):
    other = {**FUNDAMENTALS, "name": "Tata Consultancy Services Limited"}
    patch_data(monkeypatch, fundamentals=other, headlines=["x"])
    req = AnalyzeRequest(ticker="TCS").model_dump()
    out = run_analysis(req, llm=FakeLLM(available=False), document=doc())
    assert out["documentAboutCompany"] is False
    assert "does not appear to be about" in out["documentConflicts"][0]
    assert "The uploaded document may be about a different company" in out["riskFactors"]
