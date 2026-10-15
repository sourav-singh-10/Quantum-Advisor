class UserAgent:

    def analyze(self, d):

        age        = d.get("age", 30)
        experience = d.get("experience", "Beginner")
        risk_ap    = d.get("riskAppetite", "Moderate")
        horizon    = d.get("timeHorizon", "Medium-term")

        score = 50

        # Age factor
        if age < 30:
            score += 20
        elif age < 40:
            score += 10
        elif age > 60:
            score -= 20

        # Experience factor
        if experience == "Experienced":
            score += 15
        elif experience == "Intermediate":
            score += 5
        else:
            score -= 5

        # Risk appetite
        if risk_ap == "Aggressive":
            score += 10
        elif risk_ap == "Conservative":
            score -= 10

        # Time horizon
        if horizon == "Long-term":
            score += 15
        elif horizon == "Short-term":
            score -= 10

        score = max(0, min(100, score))

        if experience == "Experienced":
            user_type = "Experienced Investor"
        elif experience == "Intermediate":
            user_type = "Intermediate Investor"
        else:
            user_type = "Beginner Investor"

        return {
            "userType":          user_type,
            "riskCapacityScore": score,
        }