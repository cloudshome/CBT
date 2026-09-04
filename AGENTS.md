# AGENTS.md — Repository Index for AI Agents

> **This file is an index.** The canonical, authoritative agent operating manual
> for this project lives at **`Users/azims/CBT/AGENTS.md`** ("SKY — Permanent
> Agent Operating Manual") and MUST be read before making any change.

---

## Quick facts

- **Repo:** `cloudshome/CTB` — **Project root:** `Users/azims/CBT/`
- **Product:** SKY / Crypto Brain Terminal (CBT) — institutional-grade
  quantitative market-intelligence, paper-trading, research and governance platform.
- **Stack:** Python FastAPI (authoritative terminal API) · Node/Express + Prisma/SQLite
  (readiness/metrics/legacy) · React 18 + Vite + Tailwind PWA · Docker Compose + Caddy.
- **Source of truth:** GitHub. Never treat local/cloud copies as authoritative —
  use branches + PRs through CI and human review.

## Minimum rules (full detail in the canonical AGENTS.md)

1. Never commit secrets; never modify production config without approval.
2. Run the full test suite locally/CI before proposing a merge to `main`:
   `pytest` (Python), `npm test` (Jest), `npm run lint`, `ruff check core/ tests/`.
3. One logical change per PR; branched from `main` (`feature/<x>`, `fix/<x>`, `experiment/<x>`).
4. Do not commit directly to `main`. Label PRs (`type:feature`, `type:fix`, `scope:api`, …).
5. When uncertain, open an Issue describing intent first.

## Key docs (in `Users/azims/CBT/`)

- `AGENTS.md` — **the operating manual** (governance, change classification, spec kit)
- `ARCHITECTURE.md` — system architecture
- `ROADMAP.md` — future milestones (Phase 2 live execution → Phase 5 scaling)
- `SECURITY.md` — security policy, secrets handling, reporting
- `TODO.md` — master task board / phase tracker
- `SKY_STATUS.md` — hand-off status ledger
- `docs/` — research protocol, constitution, Kronos architecture, API reference
- `.specify/memory/constitution.md` — system constitution (causal firewalls, risk primacy)

## CI

`.github/workflows/ci.yml` runs Ruff + Pytest + ESLint + Jest + Docker compose
validation + full build on every push/PR to `main` (and `feature/**`, `fix/**`).
