# SKY Canonical Product Roadmap

> **Status:** active source of truth
> **Last updated:** 2026-08-17
> **Current software:** v2.29.x source installation; Ubuntu service units exist;
> signed `.deb`, Windows `.exe`, and Android `.apk` releases do not exist yet.
>
> This roadmap merges the delivered AI-anatomy, Agent-Reach, data/validation,
> teaching, workstation, and web-trader plans with the new production-install
> plan. Older roadmap files remain as detailed historical specifications; when
> priorities conflict, this file and `TODO.md` win.

---

## 1. Product promise

SKY should feel like installed production software, not a Git repository:

1. Install it using the normal method for the platform.
2. Open SKY from an icon or URL.
3. See whether the market, services, database, and alerts are healthy.
4. Monitor signals, evidence, risk, paper positions, and the journal.
5. Perform permitted human actions through the interface.
6. Receive safe updates without losing configuration or history.
7. Ask for later changes without manually editing source code.

The software goal does **not** change the trading-safety goal:

- SKY remains paper-first and advisory.
- No package contains an automatic exchange-order path.
- A model, mobile client, or desktop client cannot bypass the risk gate.
- Packaging success is not evidence of trading profitability.

---

## 2. One system, three installation experiences

### Chosen architecture

```text
                         HTTPS
 Windows .exe  ───────────┐
 Android .apk  ───────────┼──► Ubuntu SKY Hub
 Browser / installed PWA ─┘       ├─ Flask/Gunicorn application API
                                  ├─ scanner + paper monitor services
                                  ├─ SQLite + Parquet evidence store
                                  ├─ risk gate + audit log
                                  └─ backups + health supervision
```

**Ubuntu is the recommended always-on authority.** One database, one risk
gate, and one evidence book live there; the Hub also owns market collectors,
scanner, paper runner, and audit history.
Windows and Android are companion clients: they monitor and perform only the
human actions the authenticated API permits.

This avoids three independent engines producing three different answers. It
also keeps account data and long-running workers off a phone that may sleep,
lose connectivity, or be killed by the operating system.

### Supported deployment profiles

| Profile | Purpose | State |
|---|---|---|
| Source/developer | Current Python checkout and test workflow | ✅ available |
| Ubuntu Hub | 24/7 single-user production service | 🟡 systemd pieces exist; installer/security/backup UX pending |
| Browser/PWA | Same workstation, installable from a modern browser | 🔴 planned |
| Windows companion `.exe` | Native launcher/monitor connected to an Ubuntu Hub | 🔴 planned |
| Android companion `.apk` | Mobile monitoring, alerts, ritual, approval/journal flow | 🔴 planned |
| Windows all-in-one engine | Local engine for users with no Ubuntu host | ⏸ optional after the Hub and companion clients are stable |
| Android all-in-one engine | Engine/database running continuously on Android | ❌ rejected; unreliable background runtime and duplicated authority |

A local-only Ubuntu installation remains the safest default. Remote clients
are enabled only after authentication and TLS are configured.

---

## 3. Merged roadmap history

| Phases | Delivered capability | Detailed record | Status |
|---|---|---|---|
| P1–P6 | Signal engine, context, risk, learning, agents, immune system | `AI_ANATOMY_ROADMAP.md` | ✅ shipped |
| P7–P9 | Agent surface, source channels, typed MCP capabilities | `ROADMAP_AGENT_REACH_UPGRADE.md` | ✅ shipped |
| P10 | Owned normalized market history, derivatives, charts, streaming/store layers | `docs/DATA_INFRASTRUCTURE_ROADMAP.md` | ✅ shipped |
| P11 | Paper evidence and graduation loop | `BLUEPRINT.md`, `TODO.md` | 🔄 operational; real canonical evidence remains the work |
| P12 | Locked validation, scorecards, costs, provenance, source isolation, hard limits | `TODO.md`, validation audit documents | ✅ code shipped; real-host evidence remains |
| P13–P14 | Teaching and daily loop-health ritual | `CHANGELOG.md` | ✅ shipped |
| P15–P16 | Market sentiment colour and measured sentiment-conditioned outcomes | `CHANGELOG.md` | ✅ shipped |
| P17 | Clickable Trading Workstation and real-world read-only connections | `WEB_TRADER_ROADMAP.md`, `HANDOVER.md` | ✅ foundation shipped; listed workstation follow-ups remain |
| P18.1–P18.2 | Owner auth/roles/CSRF/audit, then the stable `/api/v1` client contract | `docs/HANDOVER_2026-08-17_P18_2.md` | ✅ shipped |
| P18.3 | Persisted background jobs + SSE | `docs/HANDOVER_2026-08-17_P18_3.md` | ✅ shipped |
| P18.4–P22 | PWA, then secure production distribution for Ubuntu, Windows, and Android | this document | 🔄 next product phase |

### Workstation items carried forward—not lost

The unfinished items from `WEB_TRADER_ROADMAP.md` are merged here:

- **W1 Evidence UX:** one guided evidence build with streaming progress and an
  honest projected gap.
- **W2 Chart UX:** live incremental updates, drawings, zones, replay, and
  multi-chart views.
- **W3 Trader development:** weekly review, equity/R charts, daily ritual,
  enforced journaling, and practice scoring.
- **W4 Reliability:** stale-data age, mobile compact layout, background jobs,
  and streamed command output.

They are prerequisites or companions to P18–P22, not a separate competing
roadmap.

---

## 4. New production roadmap

## P18 — Product boundary, security, and background jobs

**Goal:** make the existing workstation safe to use as an installed/remote
product before wrapping it in `.exe` or `.apk` files.

### P18.1 Authentication and authorization — ✅ shipped v2.29.2

- First-run owner creation with a securely hashed password.
- Roles:
  - `viewer`: read dashboards, evidence, health, and paper state;
  - `operator`: viewer plus explicitly permitted human paper actions;
  - no role grants live exchange execution because that capability is absent.
- Secure cookie sessions for browsers; revocable, scoped device tokens for
  companion clients.
- CSRF protection for browser mutations, login throttling, session expiry,
  logout-all-devices, and an audit row for every sensitive action.
- Existing local loopback mode remains simple; remote mode refuses to start
  without an owner account and an HTTPS-aware deployment configuration.

**Done when:** an unauthenticated user cannot read private state or mutate
anything; a viewer cannot approve/reject/close; an operator still cannot bypass
the risk gate; security tests cover every write endpoint.

### P18.2 Stable application API — ✅ shipped v2.30.0

> Delivered: one envelope, typed `ErrorCode` vocabulary, public
> `/api/v1/version` compatibility range (checked before auth), idempotency
> keys on the four human mutations, device registration/revocation, and a
> machine-readable `/api/v1/routes` catalog. Legacy `/api/*` still works.
> Contract: `docs/HANDOVER_2026-08-17_P18_2.md`.

- Versioned `/api/v1` contract for dashboard and companion clients.
- One response envelope and typed error codes; no client parses terminal text.
- Compatibility policy: clients can detect minimum/maximum server versions.
- Idempotency keys for human mutation requests so retries cannot duplicate an
  action.
- Device registration/revocation and a visible connected-device list.

**Done when:** web, Windows, and Android can use one documented contract and an
old client receives a clear upgrade message instead of corrupt behavior.

### P18.3 Background job manager and streaming — ✅ shipped (v2.31.0)

- Long jobs (backfill, backtest, simulator, scorecard, derivatives / cross
  collect, and the composite `evidence` Backfill→Backtest→Simulator→Scorecard)
  run behind a persisted queue with status, progress, cancel, and audit rows —
  no more blocking POST. `web/jobs.py`.
- Server-sent events for job progress (`GET /api/v1/jobs/<id>/events`); every
  frame is a full persisted snapshot so reconnect resumes from the last event.
- Only allow-listed jobs and validated arguments — always `python main.py
  <validated argv>`, never a shell string; validation shared with the Command
  Center.
- Duplicate clicks return the existing live job (`params_hash`), never a
  second run; a server restart marks orphaned runs `interrupted`, not lost.
- The W1 guided “Build my evidence” flow now has this layer to build on (a
  one-click composite job already exists in the Evidence tab).

**Done when:** closing a browser does not kill a job, duplicate clicks do not
start duplicate runs, and progress survives reconnect/restart. ✅ met
(`tests/test_jobs.py`, 23 tests).

> **Deferred (honest):** the *live health/candle* SSE stream (Priority 1 in
> `HANDOVER.md`) and the W1 projection UX are separate follow-ups, not P18.3.

### P18.4 Mobile-responsive PWA foundation

- Web app manifest, icons, install prompt, safe service worker, and offline
  shell/status page.
- Responsive compact mode for daily ritual, alerts, risk, paper positions,
  approvals, and journal completion.
- Never cache private API payloads in a shared browser cache.
- Push-notification abstraction; Telegram/Discord remain supported fallbacks.

**Done when:** the workstation can be installed from Chrome/Edge on desktop and
Android and remains safe under lost connectivity.

---

## P19 — Ubuntu production installation

**Goal:** one supported command/package installs an always-on SKY Hub.

### Deliverables

1. **Signed Debian package/repository** for supported Ubuntu LTS versions.
2. Installer creates:
   - locked `sky` service user;
   - immutable app files under `/opt/sky`;
   - configuration under `/etc/sky`;
   - database/store/backups under `/var/lib/sky`;
   - logs under journald (no secrets in logs).
3. Harden and package the existing Gunicorn dashboard, scan timer, and paper
   monitor systemd units from `ops/systemd/`.
4. `sky setup` first-run wizard: local-only or remote mode, owner account,
   market profile, notification test, storage check, and final health verdict.
5. `sky status`, `sky logs`, `sky backup`, `sky restore`, `sky doctor`, and
   `sky uninstall` commands. Uninstall preserves user data unless separately
   and explicitly requested.
6. Reverse-proxy/TLS path using a supported configuration (Caddy or nginx),
   with loopback binding preserved behind the proxy.
7. Automatic daily SQLite-safe + Parquet/config backup, retention policy,
   restore drill, disk-space alert, and schema-migration rollback plan.

**Done when:** a clean supported Ubuntu VM installs, reboots, passes health,
serves HTTPS, runs scheduled scans/paper monitoring, backs up, restores onto a
second VM, upgrades, and rolls back without losing evidence.

---

## P20 — Windows `.exe` companion

**Goal:** a normal signed Windows installer and Start-menu application for
monitoring and human control of the Ubuntu Hub.

### Deliverables

- Lightweight native shell around the production web client (WebView2-based;
  packaging framework chosen and pinned during implementation).
- Installer `.exe`/MSIX, Start-menu entry, uninstall, application icon, and
  automatic update notification.
- First-run pairing by one-time code/QR from the Ubuntu Hub.
- Server URL validation, certificate verification, Windows Credential Manager
  storage for the revocable device token, and no secret in files/logs.
- System tray status for hub online/offline, data stale, risk gate, open paper
  positions, and alert count.
- Connection-loss banner and strictly idempotent retry behavior.
- Signed release plus SHA-256 checksum and published compatibility range.

**Done when:** a clean Windows 11 machine installs without Python/Git, pairs,
monitors all core surfaces, performs authorized paper actions, updates, and
uninstalls without touching Hub data.

### Deferred Windows all-in-one

A self-contained local Windows engine may be evaluated after P22. It must use
the same migration/backup/service semantics and cannot become a second
simultaneous authority for the same user. It is not required for the first
production release.

---

## P21 — Android `.apk`

**Goal:** a signed Android companion focused on monitoring, alerts, daily
ritual, paper approvals, and journaling.

### Deliverables

- Native Android shell using the same `/api/v1` contract; responsive web UI may
  be reused, but navigation, secure storage, and notifications are native.
- Pair using a short-lived QR/one-time code; store the scoped token in Android
  Keystore; biometric re-check for operator mutations when available.
- HTTPS only, certificate validation, configured-host allowlist, no arbitrary
  web navigation, file upload, or JavaScript bridge exposing device secrets.
- Push notifications deep-link to the exact signal/risk/paper record.
- Offline behavior is read-only cached shell + “last updated” timestamp. No
  approval is queued offline; the user must reconnect and see fresh risk state.
- Signed APK for direct install; Play Store/AAB is a later release-channel
  option. Include checksums, version compatibility, and revoke-device control.

**Done when:** a clean supported Android device installs, pairs, receives an
alert, displays fresh/stale state honestly, performs an authorized paper action
only while online, journals a trade, and can be remotely revoked.

---

## P22 — Release engineering and operations

**Goal:** make releases repeatable, inspectable, supportable, and reversible.

### Deliverables

- CI matrix: Python/unit/security/API contract; Ubuntu package install/upgrade/
  rollback; Windows package smoke test; Android build/lint/instrumented smoke.
- Reproducible versioned artifacts with SHA-256 checksums, SBOM, dependency and
  license inventory, vulnerability scan, and release notes.
- Code signing for Windows and Android; signed Debian repository metadata.
  Signing credentials live only in the release environment, never the repo.
- Stable/beta channels; no silent major migration. The operator sees changes
  and can postpone within a supported window.
- In-app System page: app/client/API versions, service state, last successful
  scan/paper poll/backup, data age, disk usage, connected devices, and update
  availability.
- Privacy-respecting diagnostics export with explicit secret redaction.
- Support bundle and documented incident paths: hub offline, stale data,
  database locked/corrupt, disk full, certificate expired, failed migration,
  lost phone, and rollback.

**Done when:** one tagged commit produces reviewable artifacts, a release can be
installed on clean targets, monitored, backed up, upgraded, rolled back, and
diagnosed without opening the source tree.

---

## 5. Build order and release gates

```text
DONE      P18.1 auth/roles (v2.29.2) → P18.2 versioned API (v2.30.0) → P18.3 jobs/SSE (v2.31.0)
NOW       W1 guided evidence UX (builds on the P18.3 job layer)
PARALLEL  W4 mobile/stale-state reliability
THEN      P18.4 PWA
THEN      P19 Ubuntu Hub package (first production release)
THEN      P20 Windows companion
THEN      P21 Android companion
FINISH    P22 signed multi-platform release/operations contract
ALWAYS    P11 real canonical paper evidence; never lower the graduation bar
```

Why Ubuntu first: Windows and Android need a stable, secure server contract to
connect to. Building wrappers first would produce attractive installers around
an unauthenticated development server and force all clients to be rewritten.

---

## 6. Production acceptance checklist

A release is not “production” merely because it launches.

| Area | Required evidence |
|---|---|
| Install | clean-machine install with no Git/Python knowledge |
| Startup | survives reboot and reports service health |
| Security | auth/role/CSRF/token/revocation tests; TLS for remote use |
| Safety | no live-order code; risk gate enforced server-side |
| Data | migrations, backup, restore, retention, disk-full handling |
| Network | reconnect, stale-state display, timeout, idempotent retries |
| Monitoring | service/data/job/backup/update status visible in the app |
| Upgrade | previous supported release upgrades without data loss |
| Rollback | failed release can return to prior version with compatible data |
| Packaging | signed artifact, checksum, SBOM, release notes |
| Trading truth | demo/research/paper/live provenance never mixed |

---

## 7. Files affected—and files deliberately unchanged today

### Roadmap/documentation integration

- `ROADMAP.md` — canonical merged roadmap (this file).
- `WEB_TRADER_ROADMAP.md` — detailed P17/workstation backlog; now subordinate.
- `AI_ANATOMY_ROADMAP.md` and `ROADMAP_AGENT_REACH_UPGRADE.md` — delivered
  historical phase specifications; now subordinate.
- `TODO.md` — executable next milestone.
- `ARCHITECTURE.md`, `BLUEPRINT.md`, `README.md`, `HANDOVER.md`, and
  `SESSION_STATE.md` — point to the same product direction.

### No speculative configuration or dependency

`.env.example`, `requirements.txt`, `config.py`, `main.py`, `mcp_server.py`,
and packaging ignore rules should change **only when their corresponding P18+
code lands**. We do not add fake future environment variables, Android/Windows
build dependencies, or configuration that the current program cannot read.

---

## 8. Decisions already made

1. **Ubuntu Hub first.** One always-on source of truth.
2. **Windows and Android begin as companion clients.** No duplicated trading
   brain or evidence store.
3. **PWA before native wrappers.** It proves mobile/responsive/auth/API behavior
   once; `.exe` and `.apk` package the proven contract.
4. **Remote access requires auth + HTTPS.** No public unauthenticated Flask.
5. **No live order execution in this roadmap.** Distribution does not bypass
   graduation or require exchange trading credentials.
6. **User data survives application updates/uninstall by default.** Deletion is
   a separate explicit operation.
7. **Stable releases are manually reviewable.** No unannounced strategy,
   threshold, or schema change.
8. **Needle remains parked.** It is unrelated to packaging unless a measured
   edge-device routing requirement later satisfies N1–N8 in
   `docs/NEEDLE_REVIEW.md`.
