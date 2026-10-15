"""Profile agent: turns form fields (and an optional free-text goal) into investor constraints."""
from __future__ import annotations

from agents.base import BaseAgent
from core.schemas import ProfileView
from tools.risk_rules import risk_capacity

HORIZON_YEARS = {"Short-term": 1, "Medium-term": 3, "Long-term": 7}


class ProfileAgent(BaseAgent):
    name = "ProfileAgent"
    system = ("You profile retail investors in India. Be conservative: never allow more than "
              "15% of a portfolio in one stock, and less for beginners or short horizons.")

    def run(self, ctx, request: dict) -> dict:
        capacity = risk_capacity(request)
        ctx.emit(self.name, "tool:risk_capacity", "tool_call", {"argument": "profile"})
        ctx.emit("tool:risk_capacity", self.name, "tool_result",
                 {"ok": True, "summary": f"capacity {capacity}/100"})

        def fallback():
            cap = 5 + capacity / 10            # 5% .. 15%
            return ProfileView(
                summary=f"{request['experience']} investor, {request['riskAppetite'].lower()} "
                        f"appetite, {request['timeHorizon'].lower()} horizon.",
                max_position_pct=round(cap, 1),
                horizon_years=HORIZON_YEARS[request["timeHorizon"]],
                constraints=[])

        prompt = (f"Investor: age {request['age']}, experience {request['experience']}, "
                  f"risk appetite {request['riskAppetite']}, horizon {request['timeHorizon']}, "
                  f"portfolio INR {request['portfolioValue']:,.0f}. Risk capacity score "
                  f"(computed) {capacity}/100.\nStated goal: {request.get('goal') or 'none'}\n"
                  "Return the investor summary, a max single-stock position %, horizon in years, "
                  "and any constraints the goal implies (e.g. needs the money in 2 years).")
        view, meta = self.decide(ctx, prompt, ProfileView, fallback)
        experience = request["experience"]
        return {
            "userType": f"{experience} Investor",
            "riskCapacityScore": capacity,
            "profileSummary": view.summary,
            "maxPositionPct": max(1.0, min(15.0, view.max_position_pct)),
            "horizonYears": view.horizon_years,
            "constraints": view.constraints,
            "_llm": meta,
        }
