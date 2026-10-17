"""Tools for company documents (annual reports, quarterly results, balance sheets).

Pure functions over the PDF's text. The Document Analyst decides which pages to read and
what the figures mean; these tools only read, search and parse, so every number the agent
reports can be traced back to a page of the user's file.
"""
from __future__ import annotations

import io
import re

from tools.base import ToolError

MAX_PAGES = 400            # annual reports run to 300+ pages; beyond this we stop reading
MAX_BYTES = 15 * 1024 * 1024

# Each figure: label patterns, tried in order. Lines are matched case-insensitively.
LABELS = {
    "revenue": [r"revenue from operations", r"total revenue", r"total income from operations",
                r"net sales", r"total income"],
    "netProfit": [r"net profit for the (?:period|year|quarter)", r"profit for the (?:period|year|quarter)",
                  r"net profit after tax", r"profit after tax", r"net profit"],
    "eps": [r"basic (?:and diluted )?(?:eps|earnings per (?:equity )?share)",
            r"earnings per (?:equity )?share.{0,20}basic", r"\bbasic\b(?: \(₹\)| \(rs\.?\))?"],
    "borrowings": [r"total borrowings", r"borrowings"],
    "equity": [r"total equity attributable to", r"total equity", r"net worth",
               r"equity attributable to (?:the )?(?:equity )?(?:holders|shareholders|owners)"],
}
FIGURE_NAMES = {"revenue": "Revenue", "netProfit": "Net profit", "eps": "EPS (basic)",
                "borrowings": "Borrowings", "equity": "Total equity"}

# Wording that matters to an investor when it appears in an audit report or notes.
# Deliberately narrow: "going concern basis" and "contingent liabilities" appear in every
# healthy company's report and are not flags.
RED_FLAGS = {
    r"basis for qualified opinion|\bqualified opinion\b": "Auditor gave a qualified opinion",
    r"\badverse opinion\b": "Auditor gave an adverse opinion",
    r"disclaimer of opinion": "Auditor disclaimed an opinion",
    r"material uncertainty related to going concern|substantial doubt about .{0,30}going concern":
        "Doubt about the company continuing as a going concern",
    r"default(?:ed)? in (?:the )?repayment": "Default in repaying loans",
    r"wilful defaulter": "Named a wilful defaulter",
    r"\brestated\b": "Figures were restated",
}

_UNIT = re.compile(r"(?:₹|rs\.?|inr)\s*(?:in\s+)?(crores?|cr\.?|lakhs?|lacs?|millions?|billions?)\b"
                   r"|\(\s*(?:₹|rs\.?|inr)?\s*in\s+(crores?|lakhs?|lacs?|millions?|billions?)", re.I)
_TO_CRORE = {"crore": 1.0, "cr": 1.0, "lakh": 0.01, "lac": 0.01, "million": 0.1, "billion": 100.0}
_NUMBER = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?\)?")


# ------------------------------------------------------------------ reading
def load_pdf(data: bytes, name: str = "document.pdf") -> dict:
    """Extract the text of each page. Raises ToolError for files we cannot use."""
    if not data:
        raise ToolError("the file is empty")
    if len(data) > MAX_BYTES:
        raise ToolError(f"the file is larger than {MAX_BYTES // (1024 * 1024)} MB")
    if not data.lstrip()[:5].startswith(b"%PDF"):
        raise ToolError("this is not a PDF file")
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise ToolError("the PDF is password-protected") from exc
        total = len(reader.pages)
        pages = []
        for page in reader.pages[:MAX_PAGES]:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append("")
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"could not read the PDF ({type(exc).__name__})") from exc
    if sum(len(p.strip()) for p in pages) < 200:
        raise ToolError("the PDF has no readable text (it may be a scanned image)")
    pages, injections = remove_instructions(pages)
    return {"name": name, "pages": pages, "pageCount": total, "pagesRead": len(pages),
            "injections": injections}


def remove_instructions(pages: list[str]) -> tuple[list[str], list[dict]]:
    """Drop lines written as instructions to an AI (prompt injection) and list them by page."""
    from tools.safety import clean_lines
    out, injections = [], []
    for i, text in enumerate(pages):
        clean, removed = clean_lines(text)
        out.append(clean)
        injections += [{"page": i + 1, "text": r} for r in removed]
    return out, injections


# ------------------------------------------------------------------ searching
def search_pages(doc: dict, query: str, limit: int = 5) -> list[dict]:
    """Rank pages by how often the query's words appear. Pages are numbered from 1."""
    terms = [t for t in re.findall(r"[a-z]{3,}", query.lower())
             if t not in {"the", "and", "for", "with", "page", "pages"}]
    if not terms:
        raise ToolError("give a few words to search for, e.g. 'revenue profit'")
    scored = []
    for i, text in enumerate(doc["pages"]):
        low = text.lower()
        score = sum(low.count(t) for t in terms)
        if "statement of profit and loss" in low or "balance sheet" in low:
            score += 3
        if score:
            hit = min((low.find(t) for t in terms if t in low), default=0)
            snippet = " ".join(text[max(0, hit - 60): hit + 140].split())
            scored.append({"page": i + 1, "score": score, "snippet": snippet})
    scored.sort(key=lambda r: -r["score"])
    if not scored:
        raise ToolError(f"no page mentions {', '.join(terms)}")
    return scored[:limit]


def read_page(doc: dict, page: int | str, max_chars: int = 3500) -> dict:
    try:
        n = int(str(page).strip().split()[0].strip("p."))
    except (ValueError, IndexError) as exc:
        raise ToolError("give a page number, e.g. 12") from exc
    if not 1 <= n <= len(doc["pages"]):
        raise ToolError(f"page {n} does not exist (the document has {len(doc['pages'])} pages)")
    text = doc["pages"][n - 1]
    return {"page": n, "text": text[:max_chars], "unit": detect_unit(text)}


# ------------------------------------------------------------------ parsing
def detect_unit(text: str) -> str | None:
    m = _UNIT.search(text)
    if not m:
        return None
    word = (m.group(1) or m.group(2)).lower().rstrip(".")
    for key in _TO_CRORE:
        if word.startswith(key):
            return key
    return None


def _to_number(token: str) -> float | None:
    neg = token.startswith("(") and token.endswith(")") or token.startswith("-")
    digits = token.strip("()-").replace(",", "")
    try:
        value = float(digits)
    except ValueError:
        return None
    return -value if neg else value


def _first_value(line: str, label_end: int, is_eps: bool) -> float | None:
    """First number after the label, skipping note references like 'Note 23'."""
    tokens = _NUMBER.findall(line[label_end:])
    values = [(_to_number(t), t) for t in tokens]
    values = [(v, t) for v, t in values if v is not None]
    for i, (v, t) in enumerate(values):
        looks_like_note = ("," not in t and "." not in t and abs(v) < 60 and i + 1 < len(values))
        if looks_like_note and not is_eps:
            continue
        if not is_eps and abs(v) < 1:
            continue
        return v
    return None


def _sum_borrowings(text: str, unit: str | None) -> dict | None:
    """Balance sheets list borrowings twice (non-current and current); add them up."""
    total, lines = 0.0, []
    for line in text.splitlines():
        m = re.search(r"\bborrowings\b", line, re.I)
        if m and not re.search(r"total borrowings", line, re.I):
            v = _first_value(line, m.end(), False)
            if v is not None:
                total += v
                lines.append(" ".join(line.split()))
    if len(lines) < 2:
        return None
    if unit:
        total = total * _TO_CRORE[unit]
    return {"value": round(total, 2), "unit": "₹ crore" if unit else "as printed",
            "line": " + ".join(lines)[:160]}


def extract_figures(pages: list[tuple[int, str]]) -> dict:
    """Rule-based extraction: {figure: {value, unit, page, line}} for figures it can find.

    ``pages`` is a list of (page number, text). Money figures are converted to crore when
    the page states its unit; EPS stays in rupees.
    """
    found: dict = {}
    for key, patterns in LABELS.items():
        is_eps = key == "eps"
        for pattern in patterns:
            rx = re.compile(pattern, re.I)
            for page_no, text in pages:
                unit = detect_unit(text)
                for line in text.splitlines():
                    m = rx.search(line)
                    if not m:
                        continue
                    value = _first_value(line, m.end(), is_eps)
                    if value is None:
                        continue
                    if not is_eps and unit:
                        value = round(value * _TO_CRORE[unit], 2)
                    found[key] = {"value": value, "unit": "₹" if is_eps else ("₹ crore" if unit else "as printed"),
                                  "page": page_no, "line": " ".join(line.split())[:160]}
                    break
                if key in found:
                    break
            if key in found:
                break
    if "borrowings" in found and "total borrowings" not in found["borrowings"]["line"].lower():
        page_no = found["borrowings"]["page"]
        text = dict(pages).get(page_no, "")
        summed = _sum_borrowings(text, detect_unit(text))
        if summed:
            found["borrowings"] = {**summed, "page": page_no}
    return found


def scan_red_flags(doc: dict) -> list[dict]:
    flags, seen = [], set()
    for i, text in enumerate(doc["pages"]):
        low = text.lower()
        for pattern, label in RED_FLAGS.items():
            if label not in seen and re.search(pattern, low):
                seen.add(label)
                flags.append({"flag": label, "page": i + 1})
    return flags


def appears_in(value: float, text: str) -> bool:
    """True when ``value`` is printed somewhere in ``text`` (ignoring commas/brackets).

    Used to reject figures an LLM reports that are not actually in the document.
    """
    digits = text.replace(",", "")
    candidates = {f"{abs(value):.2f}", f"{abs(value):.1f}", f"{abs(value):g}"}
    if float(value).is_integer():
        candidates.add(str(int(abs(value))))
    return any(re.search(rf"(?<![\d.]){re.escape(c)}(?![\d])", digits) for c in candidates)


def mentions_company(doc: dict, ticker: str, name: str | None = None) -> bool:
    """True if the document names the company (by NSE symbol or by its name)."""
    text = " ".join(doc["pages"][:15] + [doc.get("name", "")]).lower()
    if re.search(rf"\b{re.escape(ticker.lower())}\b", text):
        return True
    if name:
        words = [w for w in re.findall(r"[a-z&]+", name.lower())
                 if w not in {"limited", "ltd", "the", "company", "corporation", "inc"}]
        core = " ".join(words[:2])
        if core and core in " ".join(text.split()):
            return True
    return False


# ------------------------------------------------------------------ cross-check
def derived_ratios(figs: dict) -> dict:
    """Profit margin and debt/equity computed from document figures, when possible."""
    val = lambda k: (figs.get(k) or {}).get("value")
    out = {}
    if val("revenue") and val("netProfit") is not None and val("revenue") > 0:
        out["profitMargin"] = round(val("netProfit") / val("revenue") * 100, 2)
    if val("equity") and val("borrowings") is not None and val("equity") > 0:
        out["de"] = round(val("borrowings") / val("equity"), 2)
    return out


def compare_with_live(derived: dict, live: dict) -> list[dict]:
    """Differences between the document and the live data big enough to matter."""
    issues = []
    if derived.get("profitMargin") is not None and live.get("profitMargin") is not None:
        d, l = derived["profitMargin"], live["profitMargin"]
        if abs(d - l) > 3:
            issues.append({"metric": "profitMargin", "document": d, "live": l,
                           "text": f"Profit margin is {d:.1f}% in the document but {l:.1f}% "
                                   "in the live data"})
    if derived.get("de") is not None and live.get("de") is not None:
        d, l = derived["de"], live["de"]
        if abs(d - l) > 0.25 and abs(d - l) > 0.3 * max(d, l):
            issues.append({"metric": "de", "document": d, "live": l,
                           "text": f"Debt/equity is {d:.2f} in the document but {l:.2f} in the "
                                   "live data"})
    return issues
