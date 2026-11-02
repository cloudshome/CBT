# CBT / SKY Project Inspection Report for AI

**Inspection snapshot:** 2026-11-02  
**Repository:** `cloudshome/CBT`  
**Branch / inspected revision:** `main` / `fd26e9e`  
**Purpose:** Give future AI agents a reliable project map, identify demonstrated strengths and gaps, and define what is needed for CBT to be dependable real-world software.

> This is a repository inspection, not a full line-by-line code review, security audit, production deployment check, or trading-performance evaluation. Claims below are labeled by evidence type. Re-check the current code and configuration before acting; this report is a map, not authority over the code.

## Executive assessment

**[FACT]** CBT is a substantial, multi-language cryptocurrency market-intelligence and trading operations codebase. It has a Python quantitative engine and API, a React/TypeScript terminal, a Node/Express service, a Python CLI, SQLite persistence, deployment assets, and automated tests and CI.

**[INFERENCE]** It is already real software in the engineering sense: it has executable workflows, service boundaries, persistence, packaging/deployment, tests, and operational documentation. It is not merely a concept or UI mockup.

**[UNVERIFIED]** This inspection does not establish that the current checkout is running in production, that every documented feature is reachable, that data sources are reliable at operating scale, or that any strategy has positive live-market expectancy. Passing software tests cannot prove trading edge.

**Overall judgment:** Broad implementation and serious governance intent; product maturity and operational truth are less clear than the code volume suggests. The highest-value work is convergence, evidence, and reliability—not adding more strategy modules.

## What the project is

The stated product is a cryptocurrency market-intelligence, quantitative research, and risk-governed decision-support platform. Its intended flow is:

1. Ingest and quality-check market/research data.
2. Derive market state, structure, indicators, regimes, and scenarios.
3. Estimate outcomes and net expected value.
4. Apply deterministic risk and decision gates.
5. Present evidence and proposed decisions in a terminal or CLI.
6. Record paper/testnet outcomes and research evidence.

The project is intentionally risk-first and emphasizes point-in-time data, no-lookahead rules, provenance, immutable experiments, and human governance. These are sound design goals, but each must be verified at the relevant runtime boundary.

## Repository map

| Area | Role and orientation |
|---|---|
| [`app.py`](../app.py) | Main Python FastAPI application and WebSocket surface; imports and wires many quantitative, research, risk, execution, and integration modules. Start here for Python API/lifecycle routing. |
| [`core/`](../core) | Main Python domain implementation: market data, intelligence, risk, research, storage, execution, auth, and integrations. It is the largest and most consequential area. |
| [`main.py`](../main.py), [`cli/`](../cli) | Python command-line interface for scanning, analysis, operations, research, and paper workflows. |
| [`frontend/`](../frontend) | React + TypeScript web terminal, UI components, API clients, charting, and state/data providers. |
| [`src/`](../src) | Node/Express API and Prisma-backed service. `src/server.ts` explicitly calls this a legacy/direct-access or compatibility surface and identifies Python FastAPI as authoritative for the terminal API. |
| [`prisma/`](../prisma) | Node-side data schema and generated-client configuration. |
| [`tests/`](../tests) | Python tests, Node/Jest tests, and sub-suites for execution, research, and integrations. `tests/conftest.py` redirects Python databases to a temporary directory. |
| [`deploy/`](../deploy), [`Dockerfile`](../Dockerfile), [`Dockerfile.backend`](../Dockerfile.backend), [`docker-compose.yml`](../docker-compose.yml) | Container, proxy, installation, backup, maintenance, and operational support. |
| [`docs/`](.) | Architecture, research, certification, operations, handovers, audits, and project status. The amount of documentation is useful, but not all files are current or mutually consistent. |
| [`research/`](../research), [`ai/`](../ai), [`sky_agent/`](../sky_agent) | Research-support and agent-related modules; verify exact ownership and runtime use before assuming these are one cohesive subsystem. |
| [`electron/`](../electron), [`packaging/`](../packaging) | Desktop/mobile packaging and companion clients. Treat them as additional product surfaces requiring their own release and compatibility validation. |

**[FACT]** At this snapshot, Git lists 2,396 tracked files, including 1,139 Python files, 921 Markdown files, 76 TSX files, and 74 TypeScript files. These counts describe the repository, not the amount of production-ready functionality. Ignore untracked/generated local dependencies, builds, databases, and release artifacts when mapping source.

## Runtime shape and important seams

- **Python FastAPI** is identified by the Node server and proxy configuration as the authoritative terminal intelligence API. `app.py` is the large composition root.
- **React/Vite + Nginx** serves the browser terminal. [`frontend/nginx.conf`](../frontend/nginx.conf) routes most intelligence endpoints to Python.
- **Node/Express** still serves routes and readiness/metrics behavior. [`src/server.ts`](../src/server.ts) labels its route set as legacy/direct-access and warns that behavior must stay in sync or migrate. This is a real duplication and ownership seam.
- **Caddy / Docker Compose** provide an intended multi-service deployment path with health checks, persistent data mounts, and HTTPS proxying. Configuration describes Python, Node, frontend, and Caddy as separate services.
- **Python CLI** is a separate operator surface; [`main.py`](../main.py) documents a broad command set.
- **SQLite** is used by multiple components. Python’s test harness isolates its configured databases; Node tests configure a separate test database in [`jest.config.js`](../jest.config.js).

**AI caution:** Do not infer the real deployed route map from one document. Compare `app.py`, `src/server.ts`, `frontend/vite.config.ts`, `frontend/nginx.conf`, and `deploy/Caddyfile` for the specific endpoint being changed.

## Demonstrated strengths

1. **Risk and research governance are explicit.** [`docs/SKY_CONSTITUTION.md`](SKY_CONSTITUTION.md) states risk primacy, causal cutoffs, dataset provenance, experiment immutability, and credential isolation. These principles are more disciplined than a typical indicator dashboard.
2. **There are real engineering surfaces.** The repo contains API services, CLI, UI, persistence, containerization, service health checks, backup/restore tooling, and desktop/mobile packaging.
3. **Automated quality gates cover multiple stacks.** [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs Python lint/format and tests, Node lint/Jest, a frontend build, Docker Compose validation, and an overall build. This is useful integration coverage at the pipeline level.
4. **Test data isolation is designed in.** [`tests/conftest.py`](../tests/conftest.py) configures temporary Python database paths before core database imports; this is a strong safeguard for tests.
5. **The code separates important concerns into modules.** There are distinct areas for data quality, causal checks, risk, scenario/EV work, research lineage, execution, reconciliation, and UI/API clients.
6. **Operational concerns are not ignored.** [`RUNBOOK.md`](../RUNBOOK.md), Compose files, Dockerfiles, and deployment scripts cover startup, health, backup, maintenance, and incident response.
7. **The project’s epistemic posture is directionally sound.** It explicitly distinguishes software correctness from evidence of trading performance and emphasizes paper/research validation before capital exposure.

These are architectural and repository-level strengths. They do not prove every control works under all failure modes or that the system is ready for unattended production.

## Weaknesses and maturity risks

### 1. No single, current product/runtime truth

**[FACT]** The repo has many overlapping architecture, status, handover, certification, and AI-orientation documents. For example, [`docs/AI_KNOWLEDGE_BRIEF.md`](AI_KNOWLEDGE_BRIEF.md) calls itself the single source of truth but contains a Windows-specific path and an older version/certification snapshot; [`SKY_STATUS.md`](../SKY_STATUS.md) is dated 2026-10-19 and contains broad operational/certification claims. The current inspected revision is later than that status document.

**Impact:** An AI agent or operator can follow a stale route map, version, operating mode, test count, or certification claim.

### 2. Backend ownership is split

**[FACT]** Python FastAPI is described as authoritative, while Node/Express retains parallel routes and Prisma/SQLite responsibilities. The Node application itself warns that these are legacy/direct-access routes that need parity or migration.

**Impact:** Duplicate business logic, mismatched auth/risk behavior, inconsistent persistence, and routing drift are likely maintenance hazards. A clearly bounded compatibility adapter is safer than two apparently authoritative implementations.

### 3. Breadth is ahead of demonstrated product focus

**[FACT]** There are many strategy/research/execution modules, UI workstations, and milestone documents. The documented product ranges from decision support and paper trading to testnet/autonomous execution capabilities.

**[INFERENCE]** The number of features and concepts increases integration and operational burden. It is not yet obvious which small set of user journeys is the supported, maintained product.

**Impact:** More surface area creates more failure modes, while users and AI agents have trouble knowing which workflows are stable and production-supported.

### 4. Documentation makes claims that require current reconciliation

**[FACT]** Some docs describe the system as paper/simulation-only or say live execution is permanently disabled, while the current Python app imports live execution routes/connectors and the repository contains testnet and execution code. This report does not determine whether live orders can be enabled in the current runtime.

**Impact:** A safety-critical mode boundary must be established from code, configuration, deployment, and tests—not copied from an older handover or AI brief.

Other README material includes detailed capabilities and performance-posture examples. Such examples should be labeled as illustrative unless tied to a reproducible runtime result and an immutable evidence artifact.

### 5. Test isolation setup can hide initialization failures

**[FACT]** `tests/conftest.py` wraps several subsystem schema setups and the outer initialization in broad `except Exception: pass` handlers.

**Impact:** A test run can proceed with subsystems silently uninitialized, weakening the meaning of green results. Isolation itself is good; setup failures should be surfaced or reported explicitly.

### 6. Security/dependency scanning is advisory in CI

**[FACT]** In [`.github/workflows/security.yml`](../.github/workflows/security.yml), CodeQL is configured with `continue-on-error`, while `npm audit` and `pip-audit` failures are converted to warnings with `|| echo`.

**Impact:** The workflow provides visibility but does not currently enforce a blocking security/dependency release gate. This is a process observation, not a vulnerability finding.

### 7. CI success is not a production or research qualification

**[FACT]** CI checks builds, lint, and tests. The configuration does not, by itself, demonstrate sustained operation against real exchange feeds, restore from a production backup, or prove positive out-of-sample results.

**Impact:** Clearly separate “build/test pass,” “operationally qualified,” “paper/testnet qualified,” and “research evidence qualified.” Avoid treating one as proof of another.

### 8. Production state and service boundaries need runtime evidence

**[UNVERIFIED]** This inspection did not start the stack, exercise every route, review current production telemetry, execute backup/restore, or inspect live database contents. Compose files describe an intended deployable architecture, not proof it is currently healthy or safely configured.

## What would make CBT dependable real software

“Real software” means a narrow, reliable product with clear contracts and support boundaries—not simply more modules or a larger feature list.

### Priority 0 — Define the product contract and safety boundary

- Publish one current statement of supported modes: research, simulation, paper, testnet, and (if applicable) live.
- Define exactly which APIs and services are authoritative, including data ownership, auth, risk decisions, and persistence.
- Make unsupported or dangerous modes impossible to enable accidentally; require explicit, auditable operator authorization for any mode transition.
- Replace conflicting status claims with generated or verifiable release evidence.

### Priority 1 — Converge the user-facing backend

- Choose one owner for each domain/API. Keep the second backend only where it has a documented, bounded purpose.
- Maintain a route matrix with method, path, owner, auth, request/response schema, persistence side effect, and tests.
- Add contract tests for the proxy and both backend surfaces; remove duplicated policy decisions rather than merely documenting parity.

### Priority 2 — Prove data and research integrity on real inputs

- Make data source, market type, event/publish/ingest/availability timestamps, coverage, quality, and freshness inspectable.
- Use immutable dataset and experiment identities; reproduce a research result from a pinned data manifest and code revision.
- Run shadow/paper evaluation against real, timestamped market data with realistic fees, slippage, outages, and fill assumptions.
- Publish out-of-sample evidence with sample sizes and uncertainty; do not describe software tests as proof of alpha.

### Priority 3 — Make operations recoverable and observable

- Test a clean install, upgrade, restart, migration, backup, and restore on a disposable environment.
- Specify service-level health/readiness semantics, alerts, retention, disk limits, and incident owners.
- Verify graceful behavior for stale feeds, exchange/API outages, clock skew, partial fills, database locks, and interrupted shutdowns.
- Keep secrets out of images, logs, local AI context, and research processes; verify deployment boundaries rather than relying only on policy text.

### Priority 4 — Make quality gates trustworthy

- Remove silent test-fixture setup failures; make required schema/setup failures fail with actionable context.
- Separate unit, integration, route-contract, UI, and end-to-end gates; report what each gate actually proves.
- Promote required security/dependency checks to explicit policy gates, with documented exception/expiry handling.
- Tie release claims to a pinned commit, reproducible command, and machine-readable result.

### Priority 5 — Reduce cognitive and maintenance load

- Select a small supported product path and mark experimental modules as experimental.
- Consolidate stale handovers and milestone status into an index with dates, ownership, and supersession links.
- Keep one AI onboarding document current with the service map, commands, safety invariants, tests, and change ownership.
- Track API/schema compatibility and migration policy across Python, Node, frontend, and companion clients.

## Suggested AI working procedure

Before changing code:

1. Read [`AGENTS.md`](../AGENTS.md), then this report and the feature’s current specification/status document.
2. Check `git status`, branch, and recent commits. Treat only tracked source as canonical; distinguish generated and local runtime data.
3. Trace the behavior from UI/CLI caller → API/proxy → domain service → persistence/external provider → tests.
4. Verify the supported operating mode and safety boundary for any risk, exchange, order, credential, or execution change.
5. Add or update a test that reproduces the intended behavior. Never use a green test as evidence of market edge.
6. Update the closest authoritative docs and label unverified claims.
7. Run the smallest relevant tests/build, inspect the diff, and report exactly what ran and what remains unverified.

## Evidence and verification status

- **[FACT]** Working tree was clean at inspection; branch `main`; inspected HEAD `fd26e9e`.
- **[FACT]** The repository contains Python/TypeScript automated test suites and multi-stack CI configuration.
- **[UNVERIFIED]** No project test suite, build, deployment, API smoke test, security scan, data-quality audit, or strategy validation was run as part of this documentation inspection.
- **[UNVERIFIED]** Live service status, active exchange credentials, actual production configuration, current real-data coverage, and strategy profitability.

## Primary references

- [Project README](../README.md)
- [Project operating manual](../AGENTS.md)
- [System constitution](SKY_CONSTITUTION.md)
- [Project topology](PROJECT_TOPOLOGY_AND_MODULAR_TREE.md)
- [AI knowledge brief (historical; reconcile before relying on claims)](AI_KNOWLEDGE_BRIEF.md)
- [Current project status (dated 2026-10-19; verify against current checkout)](../SKY_STATUS.md)
- [Operations runbook](../RUNBOOK.md)
- [CI workflow](../.github/workflows/ci.yml)
- [Security scanning workflow](../.github/workflows/security.yml)
- [Python application](../app.py)
- [Node service](../src/server.ts)
- [Python test isolation](../tests/conftest.py)
