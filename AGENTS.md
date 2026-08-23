# AGENTS.md

## Purpose

This file is the canonical instruction set for AI agents (Jules, Antigravity, AI Studio) that work on this repository. Jules, Antigravity, and other agentic tools should read this file first and follow the rules and conventions below.

> NOTE: Treat GitHub as the single source of truth. Agents should never treat their local or cloud copies as authoritative — make changes by creating branches and PRs that go through CI and human review.

---

## Project

Project: CTB
Repository: cloudshome/CTB
Repo ID: 1343744030

Short description: [REPLACE WITH A ONE‑SENTENCE DESCRIPTION OF WHAT CTB BUILDS]

Primary contacts / maintainers:
- Owner: cloudshome
- Maintainers: [list maintainers here]

---

## Mission

State the mission of the project here. Examples:
- Provide a secure, scalable backend for X
- Deliver an AI-assisted UI for Y

(Replace this section with the actual mission.)

---

## Architecture (high level)

Frontend: [tech stack]
Backend: [tech stack]
Database: [tech stack]
AI / ML: [tech stack]
Deployment: [k8s / cloud provider / serverless]

(Replace with specifics.)

---

## Agent Roles & Responsibilities

- Antigravity — Primary development environment (lead engineer):
  - Architecture, implementation, debugging, integration, refactors.
  - Run tests, use terminals, and coordinate agents when multiple agents are needed.
  - Do NOT make uncontrolled direct changes to `main` or production configuration.

- AI Studio — Research & prototype lab (R&D):
  - Rapid experiments with Gemini features, UI/UX prototypes, vision or structured output experiments.
  - Create prototypes in feature branches (e.g., `feature/ai-prototype/*`) and push to GitHub for review.
  - Do NOT be used as the permanent source of truth.

- Jules — Asynchronous engineering worker (CI tasks / small bounded jobs):
  - Tasks: write unit tests, run and triage failing tests, update docs, dependency upgrades, small bug fixes, PR suggestions.
  - Jules always follows the repository rules below and must create a PR for any code change.
  - Provide clear, bounded jobs (see Examples section).

- Humans (YOU) — Product owner & final decision maker:
  - Decide WHAT, WHY, PRIORITY, and approve merges to main.

- GitHub Actions / CI — Mechanical referee:
  - Run tests, lint, typechecks, security scans, build and report results.

---

## Rules (non-negotiable)

1. Never commit secrets (API keys, private certificates, passwords).
2. Never modify production configuration without explicit approval from maintainers.
3. Always run the full test suite locally (or via CI) before proposing a merge to `main`.
4. Never bypass tests or security checks.
5. Prefer small, focused changes (one logical change per PR).
6. Maintain backward compatibility unless the PR explicitly documents breaking changes with migration steps.
7. Update documentation and add tests for any behavior changes.
8. Do not commit directly to `main`. Use branches and PRs.
9. Label PRs with meaningful labels (e.g., `type:feature`, `type:fix`, `scope:api`).
10. If uncertain, open an Issue describing intent before making changes.

---

## Development (install / run / test)

Install:
```
# TODO: replace with actual project commands
# Example (node):
# npm install
```

Run:
```
# TODO: replace
# npm start
```

Test:
```
# TODO: replace
# npm test
```

Lint:
```
# TODO: replace
# npm run lint
```

Build:
```
# TODO: replace
# npm run build
```

(Replace these with the actual commands used by CTB.)

---

## Git workflow & Branch strategy

Primary branches:
- `main` — production-ready only. Merges only via PR, after CI and human review.
- `develop` — optional integration branch for ongoing development (team choice).

Feature branches naming:
- `feature/<short-description>`
- `fix/<short-description>`
- `experiment/<short-description>`
- `ai/<short-description>` (for AI Studio experiments)

Branch rules:
- Each branch targets `main` (or `develop` if in use) via PR.
- Keep PRs small and focused.
- Link PRs to issues when applicable.
- Use draft PRs for in-progress work.

---

## Before opening a PR (checklist for agents and humans)

- Run full test suite.
- Run linting and type checks.
- Confirm no secrets or sensitive data are being added.
- Include or update automated tests for changed behavior.
- Update documentation where applicable.
- Provide a clear PR description and testing instructions.

---

## Examples: Bounded Jules tasks (templates for Issues)

Template: Add unit tests for the authentication service
```
Title: Add unit tests for auth service
Description:
- Add unit tests covering login, logout, token refresh, and error cases.
Constraints:
- Do not change production behavior.
- Do not modify DB schema.
- Run the complete test suite.
- Create a PR against `main`.
```

Template: Triage and fix failing CI
```
Title: Triage failing CI on master (test-suite)
Description:
- Investigate CI failure (link to failing run).
- Propose minimal fix or revert causing commit.
- Run tests locally and in CI.
- Create PR with fix and include test logs.
```

---

## Examples: Antigravity tasks (planning and implementation)

Planning-only task (Antigravity):
```
Analyze repository and propose architecture changes for X feature.
Constraints: Do not modify production code. Provide:
1. Architecture proposal
2. Directory structure changes
3. Data flow diagrams
4. Migration plan (if schema changes)
```

Implementation task (Antigravity):
```
Implement the approved design from PR #NN.
Constraints:
- Create feature branch `feature/..`
- Add tests
- Run CI locally
- Create PR
```

---

## Automation / GitHub Actions

- Use CI to run: unit tests, integration tests, lint, typecheck, security scan, dependency checks, build.
- Jules can be invoked from Actions for scheduled tasks or failure triage, but Jules' PRs must follow the same rules.

---

## Security & Secrets

- Secrets must be stored in GitHub Secrets or the cloud provider's secret store.
- Never put secrets in code or plaintext files.
- Any credentials used by agents must be scoped and time-limited where possible.

---

## When an agent modifies code

1. Create a feature branch.
2. Run tests and linters.
3. Push branch and open a PR with a clear description and test evidence.
4. Tag maintainers for review.
5. Wait for human review and CI passing before merging.

Agents must include in PR description what commands they ran and test outputs.

---

## Contacts & escalation

If an agent proposes a change that affects security, production configuration, or data migrations, escalate to a human maintainer immediately and do not merge until reviewed and approved.

---

## Change log for this file

- 2026-08-23 — Initial AGENTS.md created by automation based on provided agent workflow guidance. Replace placeholders with repository-specific details.


