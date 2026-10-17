"""Kinds of company an investor can ask to avoid, and a check for whether a stock is one.

The check flags; it never changes the recommendation. The decision stays the investor's.
"""
from __future__ import annotations

# label -> (words found in the sector, industry or company name; NSE symbols known to fit)
AVOID_OPTIONS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "Tobacco": (("tobacco", "cigarette"), ("ITC", "GODFRYPHLP", "VSTIND")),
    "Alcohol": (("brewer", "distill", "spirits", "liquor", "wine"), ("UBL", "UNITDSPR", "RADICO", "GLOBUSSPR")),
    "Gambling and betting": (("gambling", "casino", "betting"), ("DELTACORP", "NAZARA")),
    "Defence and weapons": (("defense", "defence", "aerospace", "weapon", "ammunition"),
                            ("HAL", "BEL", "BDL", "MAZDOCK", "COCHINSHIP", "SOLARINDS", "DATAPATTNS")),
    "Coal, oil and gas": (("oil & gas", "oil and gas", "coal", "petroleum", "thermal coal"),
                          ("ONGC", "OIL", "COALINDIA", "BPCL", "IOC", "HINDPETRO", "GAIL", "PETRONET", "RELIANCE")),
}


def avoid_matches(avoid: list[str] | None, ticker: str, sector: str | None = None,
                  name: str | None = None) -> list[str]:
    """Plain-language notes for each avoided kind of company this stock belongs to."""
    notes = []
    text = " ".join(x for x in (sector, name) if x).lower()
    for label in avoid or []:
        words, symbols = AVOID_OPTIONS.get(label, ((), ()))
        hit_word = next((w for w in words if w in text), None)
        if ticker.upper() in symbols or hit_word:
            why = f"its business includes {hit_word}" if hit_word else "of what it sells or does"
            notes.append(f"You asked to avoid {label.lower()}. {ticker} is flagged because {why}.")
    return notes
