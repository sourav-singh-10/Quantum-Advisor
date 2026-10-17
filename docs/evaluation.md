# Evaluation report

Run on 2026-10-17 10:46 UTC against `http://127.0.0.1:5000`. 18 analyses: 3 stocks x 3 profiles x 2 repeats. Every number below is computed by `scripts/evaluate.py` from the server's own responses (raw data: `evaluation.json`).

## Summary

| Measure | Result |
|---|---|
| Analyses completed | 18 of 18 |
| Agent decisions made by the model | 358 of 358 (100%); 0 used the rule fallback |
| Runs where the model was cut off (over 20% rule decisions) | 0 of 18; 1 attempt(s) were repeated after waiting |
| Same input, same recommendation (model runs only) | 9 of 9 stock-profile pairs (100%) |
| ... of which saw identical market data | 9 of 9 pairs |
| Repeats that flipped between BUY and SELL | 0 of 9 |
| Profiles got different position sizes (model runs only) | 0 of 6 stock runs (0%) |
| Profiles got different recommendations (model runs only) | 6 of 6 stock runs (100%) |
| Debate changed the strategist's first call (model runs) | 9 of 18 (50%) |
| Debates that needed more than one round (model runs) | 16 of 18 (89%) |
| Runs where an agent asked another for evidence (model runs) | 18 of 18 (32 follow-ups in total) |
| Runs with a re-plan after a failed or weak analyst (model runs) | 0 of 18 |
| Guardrail vetoes of an approved BUY (model runs) | 0 |
| Runs where data quality capped the confidence (model runs) | 10 of 18 |
| Instruction-like text removed from news or documents | 0 notices |
| Time per analysis (model runs) | median 70.0 s, slowest 179.1 s |

## Recommendations by profile

| Profile | BUY | HOLD | SELL | Median position |
|---|---|---|---|---|
| Cautious retiree | 0 | 0 | 6 | 0.0% |
| Balanced saver | 0 | 6 | 0 | 0.0% |
| Aggressive starter | 0 | 6 | 0 | 0.0% |

## Every run

| # | Stock | Profile | Call | Shown as | First draft | Conf. | Position | Rounds | Follow-ups | Model / rules | Models | Seconds | Run |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | TCS | Cautious retiree | SELL | Avoid | HOLD | High | 0.0% | 2 | 1 | 17 / 0 | gemini-3.1-flash-lite x8, gemini-3.5-flash-lite x9 | 41.2 | `r_20261017_101340_9570a9` |
| 2 | TCS | Cautious retiree | SELL | Avoid | HOLD | High | 0.0% | 2 | 1 | 17 / 0 | gemini-3.1-flash-lite x8, gemini-3.5-flash-lite x9 | 48.8 | `r_20261017_101441_ec1ea8` |
| 3 | TCS | Balanced saver | HOLD | Wait | HOLD | High | 0.0% | 2 | 1 | 17 / 0 | gemini-3.1-flash-lite x8, gemini-3.5-flash-lite x9 | 68.6 | `r_20261017_101550_bc5194` |
| 4 | TCS | Balanced saver | HOLD | Wait | HOLD | High | 0.0% | 2 | 1 | 17 / 0 | gemini-3.1-flash-lite x8, gemini-3.5-flash-lite x9 | 107.4 | `r_20261017_101718_4d958a` |
| 5 | TCS | Aggressive starter | HOLD | Wait | HOLD | Moderate | 0.0% | 1 | 2 | 19 / 0 | gemini-3.1-flash-lite x9, gemini-3.5-flash-lite x10 | 67.2 | `r_20261017_101926_a32345` |
| 6 | TCS | Aggressive starter | HOLD | Wait | BUY | High | 0.0% | 2 | 2 | 20 / 0 | gemini-3.1-flash-lite x10, gemini-3.5-flash-lite x10 | 38.7 | `r_20261017_102324_e3ac2d` |
| 7 | HDFCBANK | Cautious retiree | SELL | Avoid | HOLD | Moderate | 0.0% | 2 | 2 | 20 / 0 | gemini-3.1-flash-lite x11, gemini-3.5-flash-lite x9 | 69.0 | `r_20261017_102423_6155f0` |
| 8 | HDFCBANK | Cautious retiree | SELL | Avoid | HOLD | Moderate | 0.0% | 2 | 2 | 20 / 0 | gemini-3.1-flash-lite x11, gemini-3.5-flash-lite x9 | 70.9 | `r_20261017_102552_aca20f` |
| 9 | HDFCBANK | Balanced saver | HOLD | Wait | HOLD | Moderate | 0.0% | 3 | 2 | 22 / 0 | gemini-3.1-flash-lite x12, gemini-3.5-flash-lite x10 | 179.1 | `r_20261017_102723_59891f` |
| 10 | HDFCBANK | Balanced saver | HOLD | Wait | HOLD | High | 0.0% | 1 | 2 | 19 / 0 | gemini-3.1-flash-lite x9, gemini-3.5-flash-lite x10 | 169.4 | `r_20261017_103042_741c1a` |
| 11 | HDFCBANK | Aggressive starter | HOLD | Wait | BUY | Moderate | 0.0% | 2 | 2 | 20 / 0 | gemini-3.1-flash-lite x10, gemini-3.5-flash-lite x10 | 74.7 | `r_20261017_103352_a7adda` |
| 12 | HDFCBANK | Aggressive starter | HOLD | Wait | HOLD | Moderate | 0.0% | 2 | 2 | 21 / 0 | gemini-3.1-flash-lite x10, gemini-3.5-flash-lite x11 | 61.9 | `r_20261017_103526_c74913` |
| 13 | ITC | Cautious retiree | SELL | Avoid | HOLD | Moderate | 0.0% | 3 | 2 | 22 / 0 | gemini-3.1-flash-lite x13, gemini-3.5-flash-lite x9 | 78.4 | `r_20261017_103648_cb913d` |
| 14 | ITC | Cautious retiree | SELL | Avoid | HOLD | Moderate | 0.0% | 3 | 2 | 22 / 0 | gemini-3.1-flash-lite x13, gemini-3.5-flash-lite x9 | 86.9 | `r_20261017_103827_ecfb1e` |
| 15 | ITC | Balanced saver | HOLD | Wait | HOLD | Moderate | 0.0% | 3 | 2 | 22 / 0 | gemini-3.1-flash-lite x12, gemini-3.5-flash-lite x10 | 79.0 | `r_20261017_104013_0df21a` |
| 16 | ITC | Balanced saver | HOLD | Wait | HOLD | Moderate | 0.0% | 2 | 2 | 21 / 0 | gemini-3.1-flash-lite x11, gemini-3.5-flash-lite x10 | 67.2 | `r_20261017_104152_01e046` |
| 17 | ITC | Aggressive starter | HOLD | Wait | BUY | High | 0.0% | 2 | 2 | 21 / 0 | gemini-3.1-flash-lite x11, gemini-3.5-flash-lite x10 | 83.6 | `r_20261017_104320_8fa5db` |
| 18 | ITC | Aggressive starter | HOLD | Wait | HOLD | Moderate | 0.0% | 2 | 2 | 21 / 0 | gemini-3.1-flash-lite x10, gemini-3.5-flash-lite x11 | 62.8 | `r_20261017_104503_f7582c` |

## How to read this

- *Model / rules* counts the agent decisions in each trace that carry an LLM call: answered by the model, or by the rule fallback after the model failed or was unavailable.
- A run with more than 20% rule decisions is marked *cut off*: the model stopped answering part-way, usually because of the free tier's per-minute quota. Consistency and personalisation are measured only on runs that were not cut off, so rules and model are never compared with each other.
- Repeats of the same stock and profile run back to back, so they normally see the same cached prices and news; *identical market data* counts the pairs where that held.
- *Shown as* is what the investor sees: Buy, Wait or Avoid when the stock is not in their holdings.
- Repeats use separate accounts, so the Planner's memory of an earlier run cannot carry over.
- Market data moves during the run; repeats spaced far apart may differ for that reason alone.
- This measures the system's behaviour, not investment performance. The app's *Track record* page checks past calls against the price four weeks later.
