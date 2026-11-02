# CBT / SKY Project Inspection Report for AI

**Inspection snapshot:** 2026-11-03
**Repository:** `cloudshome/CBT`
**Branch / inspected revision:** `main` / `b889dce`
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

**[FACT]** At this snapshot, Git lists 2,398 tracked files, including 1,139 Python files, 923 Markdown files, 76 TSX files, and 74 TypeScript files. These counts describe the repository, not the amount of production-ready functionality. Ignore untracked/generated local dependencies, builds, databases, and release artifacts when mapping source.

## Runtime shape and important seams

- **Python FastAPI** is identified by the Node server and proxy configuration as the authoritative terminal intelligence API. `app.py` is the large composition root.
- **React/Vite + Nginx** serves the browser terminal. [`frontend/nginx.conf`](../frontend/nginx.conf) routes most intelligence endpoints to Python.
- **Node/Express** still serves routes and readiness/metrics behavior. [`src/server.ts`](../src/server.ts) labels its route set as legacy/direct-access and warns that behavior must stay in sync or migrate. This is a real duplication and ownership seam.
- **Caddy / Docker Compose** provide an intended multi-service deployment path with health checks, persistent data mounts, and HTTPS proxying. Configuration describes Python, Node, frontend, and Caddy as separate services.
- **Python CLI** is a separate operator surface; [`main.py`](../main.py) documents a broad command set.
- **SQLite** is used by multiple components. Python’s test harness isolates its configured databases; Node tests configure a separate test database in [`jest.config.js`](../jest.config.js).

**AI caution:** Do not infer the real deployed route map from one document. Compare `app.py`, `src/server.ts`, `frontend/vite.config.ts`, `frontend/nginx.conf`, and `deploy/Caddyfile` for the specific endpoint being changed.

## Demonstrated strengths

1. **Risk and research governance are explicit.** [`docs/SKY_CONSTITUTION.md`](SKY_CONSTITUTION.md) states risk primacy, causal cutoffs, dataset provenance, experiment immutability, and credential isolation. [`docs/PRODUCT_CONTRACT.md`](PRODUCT_CONTRACT.md) now defines operating modes and names Python FastAPI as the authoritative backend. These principles are more disciplined than a typical indicator dashboard.
2. **There are real engineering surfaces.** The repo contains API services, CLI, UI, persistence, containerization, service health checks, backup/restore tooling, and desktop/mobile packaging.
3. **Automated quality gates cover multiple stacks.** [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs Python lint/format and tests, Node lint/Jest, a frontend build, Docker Compose validation, and an overall build. This is useful integration coverage at the pipeline level.
4. **Test data isolation is designed in.** [`tests/conftest.py`](../tests/conftest.py) configures temporary Python database paths before core database imports; this is a strong safeguard for tests.
5. **The code separates important concerns into modules.** There are distinct areas for data quality, causal checks, risk, scenario/EV work, research lineage, execution, reconciliation, and UI/API clients.
6. **Operational concerns are not ignored.** [`RUNBOOK.md`](../RUNBOOK.md), Compose files, Dockerfiles, and deployment scripts cover startup, health, backup, maintenance, and incident response.
7. **The project’s epistemic posture is directionally sound.** It explicitly distinguishes software correctness from evidence of trading performance and emphasizes paper/research validation before capital exposure.

These are architectural and repository-level strengths. They do not prove every control works under all failure modes or that the system is ready for unattended production.

## Weaknesses and maturity risks

### 1. Product contract exists; its alignment is not yet complete

**[FACT]** [`docs/PRODUCT_CONTRACT.md`](PRODUCT_CONTRACT.md), added on 2026-11-02, now declares operating modes and service ownership. Some related status and topology details still differ from executable configuration: for example, the contract labels Node/Express as port 3001, while [`src/server.ts`](../src/server.ts) and [`docker-compose.yml`](../docker-compose.yml) configure port 3000. [`SKY_STATUS.md`](../SKY_STATUS.md) also reports alignment at `fd26e9e`, while this inspection is at `b889dce`.

**Impact:** The new contract is a useful authority, but it must be reconciled with runtime config and remaining status/handover documents before agents or operators can safely treat every detail as current.

### 2. Backend ownership is declared but implementation still has legacy overlap

**[FACT]** Python FastAPI is now explicitly named authoritative in the product contract, and Node/Express is designated legacy compatibility. However, [`src/server.ts`](../src/server.ts) still mounts direct Express route handlers for candles, scan, paper, desk, institutional, and terminal APIs; it is not solely a proxy facade.

**Impact:** The ownership decision is clearer, but duplicate route behavior and policy remain possible until legacy handlers are retired, converted to bounded forwarding, or covered by explicit compatibility contracts.

### 3. Breadth is ahead of demonstrated product focus

**[FACT]** There are many strategy/research/execution modules, UI workstations, and milestone documents. The documented product ranges from decision support and paper trading to testnet/autonomous execution capabilities.

**[INFERENCE]** The number of features and concepts increases integration and operational burden. It is not yet obvious which small set of user journeys is the supported, maintained product.

**Impact:** More surface area creates more failure modes, while users and AI agents have trouble knowing which workflows are stable and production-supported.

### 4. Safety modes are documented; runtime enforcement still needs proof

**[FACT]** The product contract now explicitly documents `RESEARCH`, `SIMULATION`, `PAPER`, `TESTNET`, and locked-by-default `LIVE_RESTRICTED` modes. The application imports live execution routes and connectors. This inspection did not trace every order path, environment flag, clearance token, deployment secret, and failure path to prove the contract is enforced end to end.

**Impact:** Mode documentation is an improvement, not evidence that a forbidden transition is impossible. Validate the safety boundary from code, configuration, deployment, and tests before relying on it.

README material also includes detailed capabilities and performance-posture examples. Treat examples as illustrative unless tied to a reproducible runtime result and immutable evidence.

### 5. Core test-sandbox schema setup now fails loudly; cleanup still has best-effort catches

**[FACT]** Since the earlier snapshot, `tests/conftest.py` now logs and raises when base or subsystem schema initialization fails, rather than silently continuing. Broad catches remain around best-effort position reset and teardown cleanup.

**Impact:** The earlier schema-initialization concern is substantially addressed. Keep required setup fail-fast; make sure any remaining swallowed exceptions are limited to cleanup that cannot invalidate test isolation.

### 6. Dependency audit is blocking for critical findings, not all severities

**[FACT]** In [`.github/workflows/security.yml`](../.github/workflows/security.yml), `npm audit` and `pip-audit` now run as blocking checks at the critical threshold. CodeQL remains non-blocking (`continue-on-error`).

**Impact:** CI now blocks critical dependency findings, but high-severity dependency findings do not block these npm audit steps, and CodeQL availability/results are advisory. This is a process observation, not a vulnerability finding.

### 7. CI success is not a production or research qualification

**[FACT]** CI checks builds, lint, and tests. The configuration does not, by itself, demonstrate sustained operation against real exchange feeds, restore from a production backup, or prove positive out-of-sample results.

**Impact:** Clearly separate “build/test pass,” “operationally qualified,” “paper/testnet qualified,” and “research evidence qualified.” Avoid treating one as proof of another.

### 8. Production state and service boundaries need runtime evidence

**[UNVERIFIED]** This inspection did not start the stack, exercise every route, review current production telemetry, execute backup/restore, or inspect live database contents. Compose files describe an intended deployable architecture, not proof it is currently healthy or safely configured.

## What would make CBT dependable real software

“Real software” means a narrow, reliable product with clear contracts and support boundaries—not simply more modules or a larger feature list.

### Priority 0 — Define the product contract and safety boundary

- Keep [`docs/PRODUCT_CONTRACT.md`](PRODUCT_CONTRACT.md) authoritative and reconcile its ports, routes, status claims, and operating-mode descriptions against executable config and tests.
- Define and enforce which APIs and services own data, auth, risk decisions, and persistence.
- Make unsupported or dangerous modes impossible to enable accidentally; require explicit, auditable operator authorization for any mode transition.
- Replace conflicting status claims with generated or verifiable release evidence.

### Priority 1 — Converge the user-facing backend

- Complete the migration to the declared Python API ownership; keep Node only for explicitly bounded compatibility/dev needs.
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

- Preserve the now fail-fast schema initialization; review remaining swallowed teardown/reset exceptions and keep them limited to nonessential cleanup.
- Separate unit, integration, route-contract, UI, and end-to-end gates; report what each gate actually proves.
- Decide and document whether high-severity dependency findings and CodeQL results should block releases; retain an explicit exception/expiry process.
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

- **[FACT]** Before this report refresh, the working tree was clean; branch `main`; inspected HEAD `b889dce`.
- **[FACT]** The repository contains Python/TypeScript automated test suites and multi-stack CI configuration.
- **[FACT]** `.venv/bin/python scripts/verify_m18_certification.py` completed successfully: it initially detected modified certified-surface files, reran the 149 M18 tests, and reported the certification re-validated.
- **[FACT]** `.venv/bin/python -m pytest tests/test_milestone18_sor_and_slicing.py tests/test_milestone18_boss_adversarial.py tests/test_milestone18_final_certification.py tests/execution/test_milestone35_r_independent_audit.py -q` completed with 158 passed.
- **[UNVERIFIED]** No full project test suite, build, deployment, API smoke test, security scan, data-quality audit, or strategy validation was run as part of this inspection.
- **[UNVERIFIED]** Live service status, active exchange credentials, actual production configuration, current real-data coverage, and strategy profitability.

## Primary references

- [Project README](../README.md)
- [Project operating manual](../AGENTS.md)
- [System constitution](SKY_CONSTITUTION.md)
- [Project topology](PROJECT_TOPOLOGY_AND_MODULAR_TREE.md)
- [AI knowledge brief (cross-check against the product contract and runtime)](AI_KNOWLEDGE_BRIEF.md)
- [Project status (verify commit and operational claims against current checkout)](../SKY_STATUS.md)
- [Operations runbook](../RUNBOOK.md)
- [CI workflow](../.github/workflows/ci.yml)
- [Security scanning workflow](../.github/workflows/security.yml)
- [Python application](../app.py)
- [Node service](../src/server.ts)
- [Python test isolation](../tests/conftest.py)
