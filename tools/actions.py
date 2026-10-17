"""What the committee's call means for this investor: do they already own the stock?

The committee decides BUY, HOLD or SELL on the stock. For someone who does not own it, SELL
means "do not buy" and HOLD means "not yet", so the app says that instead of a word that
assumes a position the investor does not have.
"""
from __future__ import annotations

FIT_LIMIT = 10      # same threshold the strategist uses for "sound stock, too risky for you"

LABELS = {
    True: {"BUY": "Add more", "HOLD": "Keep", "SELL": "Sell"},
    False: {"BUY": "Buy", "HOLD": "Wait", "SELL": "Avoid"},
}


def action_for(recommendation: str, holding: bool, suitability_gap: int = 0) -> dict:
    holding = bool(holding)
    too_risky = suitability_gap > FIT_LIMIT
    if holding:
        text = {"BUY": "Add to your position, within the size shown.",
                "HOLD": ("Keep what you have but do not add: it is riskier than your profile allows."
                         if too_risky else "Keep what you have and do not add for now."),
                "SELL": "The committee expects it to do poorly and would exit the position."}[recommendation]
    else:
        text = {"BUY": "Buy, within the size shown.",
                "HOLD": ("A reasonable stock, but riskier than your profile allows: do not buy."
                         if too_risky else "Do not buy yet: wait for a better entry or clearer news."),
                "SELL": "Do not buy: the committee expects it to do poorly."}[recommendation]
    return {"label": LABELS[holding][recommendation], "text": text, "holding": holding,
            "tooRiskyForYou": too_risky and recommendation != "SELL"}
