class PortfolioAgent:

    def analyze(self, u, m, s):

        price = m["currentPrice"]

        capital = 50000

        units = int(capital * 0.05 / price)

        return {
            "portfolioAdvice": [
                f"Buy {units} units",
            ]
        }
