# Contributing to Quantum Advisor

## Set up

```powershell
git clone https://github.com/sourav-singh-10/Quantum-Advisor.git
cd Quantum-Advisor
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
copy .env.example .env      # then fill in GEMINI_API_KEY (free from Google AI Studio)
python app.py               # http://localhost:5000
```

## Before you open a pull request

```powershell
pytest -q          # no network or keys needed
ruff check .       # lint, the same check CI runs
```

## How we work

- One change per branch, named by kind: `feat/...`, `fix/...`, `test/...`, `docs/...`, `ci/...`.
- Commit messages say what changed and why, in the form `type(scope): what it does`, for example
  `feat(agents): planner re-plans an analyst that failed`.
- Every pull request is reviewed by another member before it is merged, and the tests and lint
  must pass. The pull request template lists what the reviewer checks.
- If you change how an agent behaves, update `docs/design-document.md` in the same pull request,
  and the JSON Schemas in `schemas/` if the response changes (`tests/test_schemas.py` checks them).

## Evidence files

Files in `docs/traces/` and `docs/samples/` are captured from real runs with `scripts/capture_run.py`
and are never edited by hand. To add one, capture it from the live site, check that it says every
decision was made by the model, and commit it unchanged.

## Secrets

Never commit `.env`, API keys or `users.db`. Keys belong in `.env` locally and in Render's environment
settings for the deployment.
