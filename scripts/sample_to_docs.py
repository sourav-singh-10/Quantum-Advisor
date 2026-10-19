"""Put real captured samples into docs/io-definitions.md.

    python scripts/sample_to_docs.py --analysis docs/samples/normal_response.json \
                                     --portfolio docs/samples/portfolio_response.json

Each sample is shortened for reading (long strings and long lists are cut, the embedded trace
is dropped) and written between the <!-- sample:... --> markers in docs/io-definitions.md,
with a note naming the file and run it came from. The captured files themselves are never
changed. A sample whose decisions came from the rule fallback is refused, because the docs
must show what the model-driven system actually returns (pass --allow-rules to override).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "io-definitions.md"
MAX_STR, MAX_ITEMS = 160, 2


def shorten(value, depth: int = 0):
    """A readable copy: long strings and lists are cut and say so; nothing is invented."""
    if isinstance(value, str):
        return value if len(value) <= MAX_STR else value[:MAX_STR - 1].rstrip() + "…"
    if isinstance(value, list):
        kept = [shorten(v, depth + 1) for v in value[:MAX_ITEMS]]
        if len(value) > MAX_ITEMS:
            kept.append(f"… {len(value) - MAX_ITEMS} more")
        return kept
    if isinstance(value, dict):
        return {k: shorten(v, depth + 1) for k, v in value.items() if k != "trace"}
    return value


def check_genuine(sample: dict, name: str, allow_rules: bool) -> None:
    meta = sample.get("meta") or {}
    calls, failures = meta.get("llmCalls", 0), meta.get("llmFailures", 0)
    if not allow_rules and (not calls or failures):
        raise ValueError(f"{name}: {failures} of {calls} decisions used the rule fallback; capture it again "
                         "when the model is available, or pass --allow-rules")


def block(sample: dict, source: Path) -> str:
    meta = sample.get("meta") or {}
    rel = source.resolve().relative_to(ROOT).as_posix() if source.resolve().is_relative_to(ROOT) else source.name
    note = (f"Real output, shortened for reading from [`{rel}`](../{rel}) (run `{meta.get('runId', '?')}`, "
            f"{meta.get('llmCalls', 0) - meta.get('llmFailures', 0)} of {meta.get('llmCalls', 0)} decisions by the model). "
            f"Strings over {MAX_STR} characters and lists over {MAX_ITEMS} items are cut; the file itself is unedited.")
    body = json.dumps(shorten(sample), indent=2, ensure_ascii=False)
    return f"{note}\n\n```json\n{body}\n```"


def replace_between(text: str, key: str, content: str) -> str:
    pattern = re.compile(rf"(<!-- sample:{key} -->\n).*?(\n<!-- /sample:{key} -->)", re.S)
    if not pattern.search(text):
        raise ValueError(f"markers for '{key}' not found in {DOC.name}")
    return pattern.sub(lambda m: m.group(1) + content + m.group(2), text)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--analysis", type=Path, help="captured analysis response (capture_run.py)")
    ap.add_argument("--portfolio", type=Path, help="captured portfolio review (capture_run.py --portfolio)")
    ap.add_argument("--allow-rules", action="store_true", help="accept samples decided by the rule fallback")
    a = ap.parse_args(argv)
    if not (a.analysis or a.portfolio):
        ap.error("give --analysis and/or --portfolio")
    text = DOC.read_text(encoding="utf-8")
    try:
        for key, path in (("analysis-response", a.analysis), ("portfolio-response", a.portfolio)):
            if path:
                sample = json.loads(path.read_text(encoding="utf-8"))
                check_genuine(sample, path.name, a.allow_rules)
                text = replace_between(text, key, block(sample, path))
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    DOC.write_text(text, encoding="utf-8")
    print(f"updated {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
