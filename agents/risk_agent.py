
class RiskAgent:

    def analyze(self, user, market, fund):
        risk = 0
        factors = []

        rsi = market["rsi"]
        vol = market["volatility"]
        trend = market["trend"]

        # Volatility
        if vol > 3:
            risk += 20
            factors.append("High volatility")
        elif vol > 1:
            risk += 10
        else:
            risk += 5

        # RSI
        if rsi > 70:
            risk += 10
            factors.append("Overbought")
        elif rsi < 30:
            risk += 8
            factors.append("Oversold")
        else:
            risk += 4

        # Trend
        if trend == "Downtrend":
            risk += 10
            factors.append("Downtrend")
        elif trend == "Sideways":
            risk += 6
            factors.append("Sideways market")
        else:
            risk += 3

        risk = max(5, min(100, risk))

        # Scores from the current formula normally max out at 43.
        if risk < 20:
            level = "Low-Medium"
        elif risk < 32:
            level = "Medium"
        else:
            level = "High"

        return {
            "riskScore": risk,
            "riskLevel": level,
            "riskFactors": factors,
        }

    def review_strategy(self, strategy, risk):
        """Review whether a BUY recommendation conflicts with base risk."""
        recommendation = strategy.get("recommendation", "HOLD")
        risk_score = risk.get("riskScore", 0)

        needs_revision = (
            recommendation == "BUY" and risk_score >= 25
        )

        return {
            "needsRevision": needs_revision,
            "reason": (
                "BUY conflicts with elevated base risk."
                if needs_revision
                else "No risk-based revision required."
            ),
        }
