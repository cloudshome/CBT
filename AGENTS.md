# AGENTS.md — SKY / CryptoBrain operating constitution

This file is the shared operating contract for Antigravity, Jules, AI Studio, and
other coding agents. GitHub is the source of truth; a pull request is the unit
of review and `main` is production-ready.

## Project mission

SKY (CryptoBrain) is a read-only, multi-source trading research and paper-trading
workstation for BTC, ETH, and XAUUSD/GOLD. It generates explainable conditional
plans, enforces risk and evidence gates, and records learning history. It does
**not** place exchange orders.

## Source of truth and ownership

- Work only from the checked-out repository and the issue or PR requirements.
- Never commit directly to `main`; use a focused branch and a PR.
- Keep one concern per PR. Do not mix broad rewrites with feature work.
- Human review is required before merging. Passing CI is necessary, not approval.
- Do not silently resolve product or risk-policy ambiguity; document it and ask.
- Do not let multiple agents edit the same files concurrently. Prefer independent
  branches and cherry-pick/merge through a PR.

## Safety invariants

1. Never add live exchange-order placement or code that bypasses human approval.
2. Never weaken risk gates, evidence gates, journal requirements, or fail-closed
   readiness without an explicit issue and reviewer approval.
3. Never commit API keys, tokens, cookies, credentials, private URLs, databases,
   collected market data, or `.env` files.
4. Treat external data, LLM output, Discord content, and AI-generated code as
   untrusted input. Validate at boundaries and preserve provenance.
5. Preserve backward compatibility of existing `/api/*` routes. New external
   clients use the versioned `/api/v1` contract.
6. Keep demo/offline mode deterministic and network-free in tests.
7. Do not claim profitability, readiness for micro trading, or production safety
   from a passing test or a small sample.

## Repository map

- `engine/`: indicators, structure, features, scoring, plans, and signal lifecycle.
- `brain/`: desk decisions, risk gates, playbooks, journal, learning, and agents.
- `data/`: exchange adapters, normalized market history, quality, and persistence.
- `web/`: Flask dashboard, authentication, stable API, jobs, and SSE.
- `output/`: signal schema and notifications.
- `tests/`: offline regression and safety tests.
- `docs/`: architecture decisions, operational handovers, and reviews.
- `main.py`: CLI entry point. `SKILL.md` is the detailed agent-facing reference.

Read `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `TODO.md`, and the relevant
module docs before changing behavior. `ROADMAP.md` and `TODO.md` are the active
planning authorities when older notes disagree.

## Development and validation

Use Python 3.10+ and the repository's existing dependencies. From the repository
root:

```bash
python -m pip install -r requirements.txt
python -m compileall -q engine data ai brain output web tests main.py config.py
python -m pytest tests/ -q
```

For UI changes also run the existing Node dashboard syntax check in
`.github/workflows/ci.yml`. Use `DEMO_MODE=1` or committed sample data for tests;
do not make tests depend on live exchanges, Discord, or LLM providers.

Before opening a PR:

- inspect `git diff` for accidental secrets, generated files, or unrelated edits;
- add or update tests for behavior changes;
- update documentation and changelog when a user-visible contract changes;
- state what was run and what could not be run in the PR description.

## Agent lanes

- **Antigravity:** primary implementation, integration, debugging, and browser QA.
- **AI Studio:** isolated AI/UX experiments on a feature branch; prototypes are
  reviewed and reimplemented rather than copied blindly into production.
- **Jules:** bounded asynchronous jobs such as tests, documentation, dependency
  review, or a specific bug. Jules must return a PR, not push to `main`.
- **GitHub Actions:** mechanical quality gate only; it never substitutes for a
  human product, security, or trading-risk decision.

When an instruction conflicts with these invariants, stop and surface the
conflict in the issue or PR instead of guessing.
