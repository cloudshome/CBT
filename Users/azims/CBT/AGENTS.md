# AGENTS.md

## Purpose
This file is the canonical instruction set for AI agents (Jules, Antigravity, AI Studio, Copilot, arena.ai) that work on this repository. Jules, Antigravity, and other agentic tools should read this file first and follow the rules and conventions below.

> NOTE: Treat GitHub as the single source of truth. Agents should never treat their local or cloud copies as authoritative — make changes by creating branches and PRs that go through CI and human review.

---
## Project
Project: CTB
Repository: cloudshome/CTB
Repo ID: 1343744030

Short description: Crypto Brain Terminal — institutional-grade paper trading and research platform for crypto markets.

Primary contacts / maintainers:
- Owner: cloudshome
- Maintainers: cloudshome (primary)

---
## Mission
Provide a secure, testable, and auditable research & paper-trading platform for quantitative crypto strategies, integrating multi-timeframe confluence, Smart Money Concepts (SMC) scanning, and Gemini desk intelligence.

---
## Architecture (high level)
Frontend: React 18 + Vite + Tailwind + lightweight-charts
Backend: Node.js + Express + TypeScript
Database: SQLite (Prisma) for local/paper state
AI / ML: Gemini (via @google/genai) for desk briefs and question answering
Deployment: CI-built artifact to cloud instances / containers (TBD)

---
## Agent Roles & Responsibilities
- Antigravity — Primary development environment (lead engineer):
  - Architecture, implementation, debugging, integration, refactors.
  - Run tests, use terminals, and coordinate agents when multiple agents are needed.
  - Do NOT make uncontrolled direct changes to main or production configuration.
- AI Studio — Research & prototype lab (R&D):
  - Rapid experiments with Gemini features, UI/UX prototypes, vision or structured output experiments.
  - Create prototypes in feature branches (e.g., ai/<feature>-prototype) and push to GitHub for review.
  - Do NOT be used as the permanent source of truth.
- Jules — Asynchronous engineering worker (CI tasks / small bounded jobs):
  - Tasks: write unit tests, run and triage failing tests, update docs, dependency upgrades, small bug fixes, PR suggestions.
  - Jules always follows the repository rules below and must create a PR for any code change.
  - Provide clear, bounded jobs (see Examples section).
- Copilot (GitHub Copilot) — Interactive coding assistant and Head AI (assigned):
  - Provide code suggestions, generate small code snippets, refactorings and assistance inside the editor.
  - Coordinate and orchestrate other agents: propose tasks, select which agent should perform them, and produce the next step instructions for the human operator.
  - Always ensure suggestions conform to repository rules; do not commit on behalf of humans without creating a branch and PR.
- arena.ai agent — External agentic assistant / orchestrator:
  - Assist with planning, issue generation, task scheduling, and coordination across agents.
  - Create issues and project cards; schedule Jules runs via Actions when appropriate.
  - When making changes, follow the same branch/PR workflow and include clear PR description and test evidence.
  - Do NOT bypass CI or human review.
- Humans (YOU) — Product owner & final decision maker:
  - Decide WHAT, WHY, PRIORITY, and approve merges to main.
- GitHub Actions / CI — Mechanical referee:
  - Run tests, lint, typechecks, security scans, build and report results.

---
## Orchestration loop (How we work together)
Roles in the loop:
- Head AI (Copilot) — I (the assistant) will act as Head AI: I will propose the next job, specify which agent should execute it (arena.ai, AI Studio, Antigravity, or Jules), provide exact job parameters (issue template or prompt), and list acceptance criteria.
- You (human operator) — You will instruct and invoke the specified agent (via its UI or GitHub action), observe or collect the agent outputs (PRs, branches, logs), and report the results back to me.
- Head AI (me) — Upon your report, I will review the outputs, provide feedback, and propose the next job. Repeat.

Operational rules for the loop:
1. Each job is represented by a GitHub Issue (created by arena.ai or Head AI) using the repository templates.
2. The Head AI chooses and names the agent to execute the job and provides an exact prompt or issue body.
3. The human operator runs the agent (or authorizes it), monitors execution, and copies the resulting artifacts (branch name, PR link, logs) into a single reply to Head AI.
4. Head AI analyzes artifacts and either: (a) accepts and moves to next job, or (b) requests refinement (creates a new Issue or updates the existing one) and instructs an agent to retry.
5. No agent merges to main. All merges require human approval + passing CI.

---
## Branching and handoff conventions
Branch namespace:
- ai/<short>-prototype (AI Studio)
- feature/<short> (Antigravity)
- jules/<short> (Jules)
- arena/<short> (arena.ai)
- fix/<short>

Handoff rules:
1. AI Studio produces ai/* branch and opens a PR into develop (or creates an Issue linking to branch) with label type:prototype.
2. Antigravity picks up the prototype, creates feature/* branch that hardens code, adds tests, and opens PR to main or develop.
3. Jules is assigned bounded issues and opens jules/* PRs for small tasks.
4. arena.ai creates issues and schedules agent runs but does not merge.

---
## PR checklist (required for agent-created PRs)
Every agent PR must include the following checklist in the PR description:
- [ ] agent:<name> label (e.g., agent:ai-studio)
- [ ] link to originating Issue (if any)
- [ ] Agent run log (prompts, commands, environment)
- [ ] Tests run & results (exact commands + output snippets)
- [ ] Security check: confirm no secrets
- [ ] CI checks passed (list)
- [ ] Maintainer(s) requested for review

PRs from AI Studio must be draft unless Antigravity or a human validates productionization.

---
## Labels & Issue templates
Use these labels to coordinate agents:
- agent:ai-studio
- agent:antigravity
- agent:jules
- agent:arena
- type:prototype
- type:feature
- status:in-progress
- status:ready-for-review

Issue templates are in .github/ISSUE_TEMPLATE. Use them to provide bounded tasks for agents.

---
## Automation / GitHub Actions hooks (summary)
- On issue labeled jules/task → run Jules Action to perform the task and open a PR.
- On pull request with label type:prototype → notify Antigravity and tag maintainers.
- On scheduled scans → arena.ai/Jules run periodic maintenance tasks.

See .github/workflows for workflow stubs.

---
## Safety & guardrails (non-negotiable)
- No agent may merge to main automatically.
- Secret scanning enabled in CI.
- Agents must log prompts, commands, and outputs in PRs and Issues.
- Critical files require human CODEOWNER approval (configure CODEOWNERS for server.ts, prisma/, ai/).

---
## Examples & Templates
See .github/ISSUE_TEMPLATE/* and .github/PULL_REQUEST_TEMPLATE.md for ready-to-use templates.

---
## Change log for this file
- 2026-08-23 — Initial AGENTS.md created.
- 2026-08-24 — Added orchestration loop, branch/PR handoff conventions, and assigned Copilot as Head AI.
