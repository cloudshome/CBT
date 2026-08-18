**Last updated:** 2026-08-18 (**v2.38.0 — P22.1 release-operations foundation** on `arena/01a014b8-sky`). `ops/release.py` + `packaging/build_release.py` (SHA-256 manifest, SPDX SBOM/license inventory, stable/beta), `hub diagnostics` (redacted private support bundle), an admin-activation release/package/security CI spec, and `docs/RELEASE_OPERATIONS.md`. Direct Debian build/runtime bootstrap defects fixed. No signed/native artifact claimed. Next code is **P22.2 real Windows/Android projects + trusted signing/physical-target drills**. P11 paper grind stays parallel.

**Previous:** 2026-08-18 (**v2.35.0 — P19 + home-PC first-night guide** on `arena/01a013b2-sky`). `docs/HOME_HUB_FIRST_NIGHT.md` / `hub first-night` / `ops/first_night.sh`. `ops/hub.py` + `python main.py hub setup/status/logs/backup/restore/doctor/uninstall`, FHS `/opt/sky` `/etc/sky` `/var/lib/sky`, hardened `ops/systemd/sky-*` units, Caddy/nginx TLS examples, unsigned Debian packaging (`packaging/`). SQLite-safe backups, redacted secrets, uninstall keeps data unless `--purge`. No threshold moved, no order path. Contract: `docs/HANDOVER_2026-08-18_P19.md`. Next code is **P20 Windows companion** after a real Hub host is stable; P11 paper grind stays parallel.

> **If you are the next session and the user forgot to tell you:** P19 is the Hub *mechanics* (layout, CLI, units, backup). A signed apt repo and a clean-VM install/reboot/restore drill were **not** done in this sandbox — do not claim they were. Do not start P20 wrappers around an unauthenticated laptop Flask. Continue `P11` real-paper grind.

> **If you are the next session and the user forgot to tell you:** read `docs/CHATGPT_6IDEA_TRIAGE_2026-08-18.md` first (after `SESSION_STATE.md`). It contains the `6-idea -> Take/Park/Reject` map and the `*03 evidence engine` gap list so you do not re-install LMRing/OpenDataLoader/AirLLM or add new families/tools. Continue `P19 -> P11 real-paper grind`; `P18.4` is already done.

> **Flagged honestly:** the “stream” is server-side polling of the same REST
> candle source `/api/chart` already uses, not a WebSocket — swapping in
> `data/ws_client.py` later changes no client code, since the SSE contract stays
> the same. In `DEMO_MODE` the sample candles never change, so the stream
> correctly degrades to `waiting` → `stale`. No real browser exists in this
> sandbox, so the UI was proven with the node/jsdom harness, the Flask test
> client and `curl` against a running dev server. Drawings are browser-local.

> **Fixed a live-on-`main` defect:** `web/app.py`'s `HTML` is a plain (non-raw)
> Python string, so the P18.3/W1 job-log line's `'\n'` became a real newline
> inside a JS string literal — a `SyntaxError` that disabled the **entire**
> dashboard script in any real browser. Both JS harnesses and the CI step read
> the file text, never the evaluated template, so nothing caught it. Fixed, and
> a new test (`test_served_script_is_valid_javascript`) plus an extended CI step
> now parse exactly what Flask serves.

**Previous:** 2026-08-17 (**v2.30.0 / P18.2 — the stable `/api/v1`
contract** on `arena/01a00eac-sky`). The workstation now publishes one
documented API that the browser and the future Windows/Android companions can
all speak: a single response envelope, a closed vocabulary of typed error
codes, a public compatibility range checked *before* authentication, and
idempotency keys so a retried human decision cannot double-apply. `/api/v1` is
a **contract over existing behaviour** — every delegating route calls the same
handler the dashboard calls, so it adds no capability, moves no threshold and
introduces no exchange-order path. Security is inherited from the P18.1 gate
rather than re-implemented, and every P18.1 invariant is re-asserted against
the new surface (an operator still cannot bypass the risk gate). Legacy
`/api/*` is untouched. Suite: **982 passed / 1 skipped** (3 pre-existing
environmental failures: no `mcp` package, no network). Next code is **P18.3**
persisted jobs + SSE — long jobs still run inside one blocking POST. Contract:
`docs/HANDOVER_2026-08-17_P18_2.md`.

> **Flagged honestly:** no real companion client exists yet, so the contract is
> proven against `curl`, the Flask test client and the node/jsdom harness — not
> against a real Windows or Android app, and not by a human looking at a
> browser (none is installable in this sandbox). `min == max == 1` today, so
> the upgrade paths are exercised with synthetic version headers.

**Previous:** 2026-08-17 (**v2.29.2 production-roadmap checkpoint** on
`arena/01a00df1-sky`). [`ROADMAP.md`](ROADMAP.md) is now the canonical merged
P1–P22 roadmap. Delivered AI anatomy, Agent-Reach, data/validation, teaching,
sentiment, and Trading Workstation work is preserved; P18–P22 adds the ordered
production path: secure auth/roles → `/api/v1` → persisted jobs/SSE → PWA →
Ubuntu Hub package → Windows `.exe` companion → Android `.apk` companion →
signed release operations. Current software remains source-installed; no
`.deb`, `.exe`, or `.apk` is claimed. Next code is P18.1. One Ubuntu Hub owns
DB/workers/risk/audit; clients never become duplicate engines. Packaging never
adds live exchange execution or changes graduation.

**Previous:** 2026-08-16 (**P14** on the fixed Arena session branch
`arena/01a00a75-sky`). The repository was at **v2.27.0**: the 10-minute daily
ritual and the one loop-health number are the product surface for operating
the paper→graduation loop.

> **This build (v2.27.0 / P14 — operate the loop).** The user's project
> review said success is operating the paper→graduation loop, not another
> cook. `loop_health()` composes `desk_status()` + `readiness_strip()` +
> `paper_progress()` (canonical live book; simulator excluded) into one
> number: real paper n, net expectancy, per-setup progress, is the
> graduation bar moving. `python main.py daily` (alias `loop-health`) is
> the 10-minute ritual: readiness → loop → gate → journal prompt. The
> same payload is `GET /api/loop-health`, MCP `loop_health` /
> `cryptobrain_loop`, `agent ask "how is the loop?"`, and the dashboard
> LOOP HEALTH card. P13 web follow-up shipped with it: KEY LEVELS card +
> POSITION MANAGER on LIVE SIGNAL / pending / coach; coach JS joins
> `five_levels`. No threshold moved. No order placed. Micro-live still
> blocked. `moon/` leftover images stay untracked.

**Previous:** 2026-08-16 (**P12.16 + P12.17 + P12.18** on the fixed Arena
session branch `arena/01a009c0-sky`). The repository is at **v2.25.0**: the
source boundary now reaches the **open** book (P12.16), the risk gate no longer
crashes on weeks that span a month boundary (P12.17), and every hard risk limit
now judges P&L **net of costs** (P12.18).

> **Third build this session (v2.25.0 / P12.18 — the net anchor at the hard
> limits).** P12.8 set the doctrine "a measurement only matters where something
> acts on it" and fixed the two *expectancy* sites; it missed the *P&L* sites.
> `closed_pnl()` (daily/weekly limits), `drawdown()` (the ladder) and
> `brain/metrics.py` (equity, expectancy, PF, win rate, streaks) all judged
> **gross** `rr_achieved`. This bites hardest on the live book because
> `close_paper_trade()` writes `rr_achieved` only — **every live paper row has
> `rr_net IS NULL`** — so costs existed purely as a compute-on-read step the
> limits never took.
>
> **Measured** with the repo's own cost model: 8 × −0.4R reads −0.80% gross and
> the gate stays **open**, but the book is −1.09% net, past the 1.0% daily
> limit (**fails open**); 16 × −0.4R likewise breaches the weekly limit unseen;
> 32 × −0.5R reads `4.00% / normal` instead of `5.18% / reduce_risk`; and a
> 6W/8L book reports **+0.071R (an edge)** when it is **−0.076R (a loser)**.
>
> **Fix.** `data.costs.net_r_of_row()` is the single definition of a row's net
> R — stored `rr_net` wins, else computed from the row's own levels, symbol and
> holding time, else 0.0 — placed beside the cost model so the risk gate,
> scorecard and analytics cannot drift apart. Every hard limit and the
> scorecard read it; `_net_outcome()` delegates to it; a **win is now a net
> win**. `closed_pnl()` additionally reports `gross_r_sum`/`gross_pct`/`cost_r`
> and the CLI prints the drag beside the net figure.
>
> **Unchanged.** No threshold moved — only the number compared against them.
> A cost-free book (`rr_net == rr_achieved`) behaves exactly as before, pinned
> by a control in every test group. Four pre-existing tests that pinned gross
> arithmetic while testing source isolation / date arithmetic were made
> explicitly cost-free rather than relaxed, so a future change in fee
> assumptions cannot silently rewrite what they mean.
>
> **Verification.** `tests/test_net_limits.py` (14 regressions); harness
> `ops/probes/p12_18_netlimits_probe.py` (A–F, exit 0); the P12.14–P12.17
> probes still exit 0; full suite **797 passed / 1 skipped**. Contract:
> `docs/HANDOVER_2026-08-16_P12_18.md`.

> **Second build this session (v2.24.1 / P12.17 — week-boundary risk-gate
> crash).** After P12.16 was pushed, continued review found that
> `_week_start_utc()` computed Monday as
> `start.replace(day=start.day - start.weekday())`. `datetime.replace()` cannot
> cross a month boundary, so every week beginning in the previous month raised
> `ValueError: day is out of range for month` — **38 days of 2026**, including
> 1 January. The weekly loss limit is a hard B6 control, so the entire gate
> raised instead of answering: `daily_weekly()`, `evaluate()` and
> `status_text()` all threw; `main.py approve` propagated the error at the
> human; the paper runner failed closed but recorded the reason "day is out of
> range for month" rather than a risk reason; and `check_risk_system()` — the
> diagnostic whose job is to notice a broken risk system — had **no** `except`
> and took `run_health_check()` down with it. A gate that raises is neither
> open nor closed; the outcome became an accident of exception handling.
>
> **Fix.** `timedelta` arithmetic, exhaustively verified over every date from
> 2024 through 2029 (6,576 datetimes: always the correct Monday, never a
> crash). Defence in depth: `check_risk_system()` now returns `CRITICAL` with
> the underlying error when the gate cannot be evaluated, so this class of
> failure can never be silent again. Losses falling in the previous-month part
> of the current week still count toward the weekly limit (pinned by
> regression). No threshold moved. `tests/test_week_boundary.py` (19
> regressions); harness `ops/probes/p12_17_weekstart_probe.py`; contract
> `docs/HANDOVER_2026-08-16_P12_17.md`.

**Branch:** `arena/01a01407-sky` (fixed session branch)
**HEAD commit:** verify with `git rev-parse HEAD` (P20 checkpoint after commit)
**Upstream:** `main` at `269cc7f` (P19 v2.35.0 #55). This session ships P20.
**Previous implementation branch:** `arena/01a013b2-sky` (P19 checkpoint)
**Version:** 2.36.0
**Python:** 3.11 — P20 tests green (`tests/test_windows_companion.py` + hub/handoff)

> **Current state.** P12.1–P12.18, P13 and P14 are shipped. Operate the loop
> with `python main.py daily`. The next work in sequence remains operational,
> not a speculative trading feature: on the real-data host, rerun canonical
> learning, import and validate the separate Dukascopy XAU history, archive
> the read-only `xau-evidence --json` dossier, and continue the canonical live
> paper book. This clean checkout has no real store/database, so it must not
> manufacture either result. The graduation bar
> remains closed; XAU remains research-only; micro-live remains blocked until
> the unchanged graduation gate is READY and the user separately approves it.
> **P14 (v2.27.0, this session)** shipped the 10-minute daily ritual and the
> one loop-health number across CLI / HTTP / MCP / ask / dashboard, plus the
> P13 web follow-up (KEY LEVELS + POSITION MANAGER). No threshold moved.

> **This session (`arena/01a009c0-sky`): v2.24.0 / P12.16 open-book source
> isolation.** PR #39 had merged and every ordered next action is real-host
> operational work this checkout cannot honestly perform, so the session opened
> as a safety review and produced `docs/HANDOVER_2026-08-16_P12_16.md` plus the
> reproduction `ops/probes/p12_16_openbook_probe.py`; the fix was then built
> against that contract.
>
> **The gap.** P12.11–P12.15 walked the source boundary through every surface
> reading *decided* paper trades, but the **open** book was never isolated:
> `open_exposure()` and `active_paper_trades()` selected
> `status IN ('WAITING_ENTRY','OPEN')` with no `sim_key` filter and no
> `source_key` filter. Measured on `731119d`: one open `dukascopy:spot:bid`
> BTCUSDT row made `portfolio_veto()` refuse a real live trade for "correlated
> exposure (1 open)" against a **flat** live bucket — this fails **closed**,
> the mirror of P12.15; two research rows read `n_open=2 /
> planned_risk_pct=1.0`, exhausting `CRYPTO_BUCKET_MAX_TRADES` and
> `MAX_CRYPTO_EXPOSURE_RISK_PCT`; simulator samples (inserted `status='OPEN'`
> and closed in the same pass) left orphans after any interrupted run that held
> live risk slots permanently; the paper runner polled research and simulator
> rows as live work, pricing them off the *canonical live* candle client and
> able to open/close/journal them onto the live book; and a desk carrying 1
> live position reported 6 across the CLI, `agent ask`, the briefing, the
> watchdog agent and the dashboard.
>
> **Fix.** `SignalDB.live_open_rows()` is now the single definition of the live
> open book — active (`WAITING_ENTRY`/`OPEN`), `sim_key IS NULL`,
> canonical-live (`COALESCE(source_key,'')=''`, legacy NULL rows kept) — the
> open-side twin of P12.15's `live_book_rows()`. `_open_book_clause()` supplies
> the same predicate as a literal fragment for the `open_exposure()` UNION.
> `open_exposure()`, `active_paper_trades()`, the watchdog agent and the
> desk/briefing counts all read it; `paper_trade_stats()` keeps its broad
> inventory totals and adds `live_open`.
>
> **Demonstration.** The probe's six cases (A–F) all behave as specified: the
> research position no longer blocks (`allowed=True, n_open=0`), research rows
> consume no bucket capacity, simulator orphans hold no slots, the runner polls
> only scan #30 of three active rows, reported exposure reads 1 of 6, and the
> canonical-only control book (including legacy NULL rows) still fills the
> bucket at 2 and still vetoes the duplicate direction.
>
> **Unchanged.** Every threshold and cap (`CRYPTO_BUCKET_MAX_TRADES`,
> `MAX_CRYPTO_EXPOSURE_RISK_PCT`, loss limits, drawdown ladder, graduation
> bar), the decided-book surfaces from P12.11–P12.15, the approved-scan half of
> `open_exposure()`, the broad paper inventory and journal reports, the
> source-key algebra, XAU research-only status, and the no-order-placement
> contract.
>
> **Verification.** `tests/test_openbook_isolation.py` (14 new regressions);
> full suite **764 passed, 1 skipped**; the P12.14 and P12.15 probes still exit
> 0; compileall and `pip check` pass. Contract:
> `docs/HANDOVER_2026-08-16_P12_16.md`.

**Previous:** 2026-08-16 (**v2.23.2 /
P12.14 — graduation discipline isolation**. The 90% compliance criterion no
longer counts simulator journals, research-book journals, or blank
`followed_rules` answers, and missing journals now fail closed. Session began
as a review after PR #36 closed; the finding was then built.)

**Previous:** 2026-08-16 (**v2.23.1 / P12.13 —
graduation source isolation**. The global permission path now admits canonical
live evidence only; research books can neither unlock nor block micro-live.
Also reconciled merged PR/CI state and closed stale TODO-7 instructions.)
> **Implementation session (`arena/01a0096b-sky`): v2.23.3 / P12.15 live-book
> source isolation.** PR #37 (P12.14) had merged, so that session opened as a safety
> review and produced `docs/HANDOVER_2026-08-16_P12_15.md` plus the
> reproduction `ops/probes/p12_15_livebook_probe.py`; the fix was then built
> against that contract and merged as PR #38.
>
> **The gap.** P12.13/P12.14 isolated the graduation gate to the canonical
> live book, but every live *risk control* still read
> `decided_paper_rows(exclude_sim=True)` with **no provenance filter** — the
> P12.11 source boundary never reached the daily/weekly loss limits
> (`closed_pnl`), the drawdown ladder (`drawdown`), the Kelly advisory, the
> MC ruin/equity reads, MAE/MFE review, or the business scorecard. Measured
> on `fdfc9f4`: 5 real canonical losses today (−1.25%, past the student 1.0%
> daily limit) plus 6 research wins read `+7R / not blocked` — the loss
> limit failed **open**; a 24-loss canonical streak (6.0% dd, `reduce_risk`)
> interleaved with research wins read `0.25% / normal`; 8 research-only
> losses **blocked** a live desk that had not traded at all; and the Kelly
> advisory turned out to be silently dead on any populated book —
> `kelly_from_progress()` expects `paper_progress()` aggregates but was fed
> raw trade rows, so `KeyError('wins')` fell into a blanket `except` and the
> dashboard Kelly card has never rendered with data.
>
> **Fix.** `SignalDB.live_book_rows()` is now the single definition of the
> live paper book — decided (`TP_HIT`/`STOP_LOSS`), non-simulator
> (`sim_key IS NULL`), canonical-live (`COALESCE(source_key,'')=''`, legacy
> NULL rows kept) — delegating to `decided_paper_rows(...)` so the P12.11
> `_source_clause` algebra is reused. All eight live-control call sites read
> it. `engine.hidden_alpha.kelly_from_rows()` replaces the broken Kelly
> calls: it accepts trade rows, judges NET of costs where `rr_net` exists
> (P12.8), classifies win/loss by net sign, stands aside at 0.0% on a book
> with no net winners, and emits the keys the surfaces read.
>
> **Demonstration.** The probe's six cases (A–F) all behave as specified:
> the masked daily limit now blocks, the masked drawdown reads
> `6.0% / reduce_risk`, the research-only book moves nothing, Kelly reads
> `n_trades=20, kelly_size=1.0` (clamped 0.5) on a 12W/8L canonical book
> while ignoring 30 research wins, legacy NULL rows still count, and the
> canonical-only control book is byte-identical.
>
> **Unchanged.** Every threshold and cap (loss limits, ladder rungs,
> `KELLY_MAX_RISK_PCT`, the graduation bar), `decided_paper_rows()` for
> explicit callers, the scorecard research surfaces (`source_key`,
> `by_source`), `kelly_from_progress()` for genuine aggregates, P12.11–14
> behaviour, XAU research-only status, and the no-order-placement contract.
>
> **Verification.** `tests/test_livebook_isolation.py` (12 new regressions);
> full suite **748 passed, 1 skipped** (108s); compileall, `pip check`, and
> the v2.23.3 wheel gate pass; the probe harness exits 0 with all six cases
> behaving as specified.

> **This follow-up (v2.23.4 / P12.15 execution-metric isolation).** Review
> found that `business_metrics()["execution"]` still called the broad
> `violation_rate()` journal report even though the scorecard's trade/equity
> rows were canonical-live-only. `brain.journal.live_execution_stats()` now
> reads decided, non-simulator, canonical-live paper trades; it preserves the
> old journaled-entry keys, exposes eligible/journaled/missing/compliant/source,
> and `format_metrics()` prints missing live journals. The broad journal report
> and graduation discipline remain unchanged. Two regressions cover research/
> simulator isolation and missing-journal visibility; full suite is **750
> passed / 1 skipped**. Contract: `docs/HANDOVER_2026-08-16_P12_15_1.md`.
>
> **Previous session (`arena/01a008d1-sky`): v2.23.2 / P12.14 graduation
> discipline isolation.** PR #36 (P12.13) closed, so the session opened as a
> safety review and produced `docs/HANDOVER_2026-08-16_P12_14.md` plus the
> reproduction `ops/probes/p12_14_discipline_probe.py`; the fix was then built
> against that contract.
>
> **The gap.** P12.13 isolated graduation *performance* evidence by source, but
> every graduation surface still computed compliance as
> `1 - violation_rate(db)`, and `journal_stats()` reads every `journal_entries`
> row with no join to `paper_trades` and no provenance filter. Measured on
> `60b61e5`: 20 simulator journals with **zero** real canonical trades read
> `1.0` PASS; 19 clean `dukascopy:spot:bid` journals outvoted the one real
> canonical trade that broke the rules (`0.95` PASS instead of `0.0`);
> `followed_rules=None` read as 100% compliance; and 30 decided real trades
> with one journaled read `1.0` — missing journals failed **open**.
>
> **Fix.** `brain.journal.graduation_discipline(db)` (over
> `SignalDB.discipline_rows()`) is now the single discipline computation:
> decided (`TP_HIT`/`STOP_LOSS`), `sim_key IS NULL`, canonical-live
> (`COALESCE(source_key,'')=''`, legacy NULL rows included); journaled only
> when `followed_rules` is 0 or 1; `compliance = compliant / eligible` with
> `None` on an empty book. It reports eligible / journaled / missing_journals /
> violations / compliant / compliance / source. `graduation_status()` takes it
> as authoritative and echoes it as `graduation["discipline"]`; the CLI
> simulator gate, `agent ask`, `graduation_report()` and `desk_status()`
> (CLI desk, `/api/desk`, dashboard desk card, MCP) all read that one payload,
> and the desk/gate text shows the population behind the number.
>
> **Demonstration.** On a seeded mixed book the pooled report says 99.1%
> compliance (108 entries, 1 violation) while graduation now says **80.0%**
> (8/10 eligible, 1 missing journal, 1 violation) — a book that previously
> passed the 90% criterion correctly fails it.
>
> **Unchanged.** The 90% threshold, all performance criteria, P12.11 source-key
> algebra, the general journal report (`violation_rate()` still feeds
> `/api/risk`, `/api/learning`, `business_metrics()` and the journal CLI), XAU
> research-only status, and the no-order-placement contract.
>
> **Verification.** `tests/test_graduation_discipline.py` (10 new regressions,
> incl. surface parity across all four graduation paths) plus an updated
> `test_graduation_report_shape`; full suite **736 passed, 1 skipped** (126s);
> compileall, `pip check`, and the v2.23.2 wheel gate pass; the probe harness
> exits 0 with all five cases behaving as specified.
>
> **Shipped.** Pushed to `origin/arena/01a008d1-sky` and opened as **PR #37**
> (`P12.14: isolate graduation discipline (v2.23.2)`, base `main`). Both root
> CI jobs passed on the pushed head — *Offline test suite* and *Wheel gate* —
> and the PR was **merged into `main` as `fdfc9f4`** on 2026-08-16.
>
> **Previous session (`arena/01a008b9-sky`): v2.23.1 / P12.13 graduation
> source isolation.** Review found a safety gap left after P12.11:
> calibration, the live confidence hook, and `setup_proven()` were isolated by
> source, but `data.simulator.paper_progress()` still pooled every source into
> the global graduation report used by CLI, agent, desk/API/dashboard and MCP.
> A strong research book could help unlock micro-live; a weak one could block
> the canonical live book.
>
> **Fix.** `paper_progress()` now filters both decided tables to
> `COALESCE(source_key, '') = ''`: canonical Binance spot only, with legacy
> NULL rows intentionally preserved. Every progress row declares that source.
> `grind_verdict()` and `graduation_status()` independently fail closed when a
> caller provides explicit non-canonical progress, even when every sample and
> performance criterion passes. Research remains inspectable through existing
> source-filtered scorecards. No threshold changed; this is strictly tighter.
>
> **Repository reconciliation.** `origin/main` and the session branch began
> identical at `5345e9e`; PR #35 is merged. Root CI already includes the wheel
> gate, and GitHub run `31907327643` passed both jobs on that SHA, so TODO-7 and
> its obsolete nested workflow copy were closed. Branch protection remains
> unverified because the integration receives HTTP 403; TODO-8 stays open.
>
> **Verification.** Rebuilt `.venv`; focused simulator/provenance tests **41
> passed**; full suite **726 passed, 1 skipped** in 94.44s; compileall and
> `pip check` pass; v2.23.1 wheel builds with no duplicate entries. This
> checkout has no real store/database, so no real evidence claim was made and
> the graduation/micro-live gates remain closed.
>
> **Previous engineering session (`arena/01a006ec-sky`): v2.23.0 — P12.12
> PAXG-vs-XAU promotion-evidence dossier.**
>
> **What shipped.** `data/gold_basis.py` reads
> `binance/spot/PAXGUSDT` and `dukascopy/spot/XAUUSD` as independent canonical
> series and exact-inner-joins candle-open timestamps. It does not resample,
> interpolate, forward-fill, synthesize calendar observations, or pool either
> history into calibration. The basis is
> `(PAXGUSDT_close - XAUUSD_close) / XAUUSD_close`, so it explicitly includes
> USDT-vs-USD quote basis. It reports overlap coverage, basis distributions,
> median/MAD, price/return correlations, tracking error, and a reproducibility
> fingerprint.
>
> **Provenance and seals.** XAU rows must unambiguously declare one one-sided
> `bid` or `ask` price type; absent or mixed provenance fails closed. Seal
> inspection is read-only: it verifies the expected XAU symbol/timeframe,
> envelope fingerprint, exact unchanged criteria, all train/validation/
> sealed-OOS/recent windows, and surfaces history/reseal counts. It never
> creates or reseals evidence.
>
> **Operator surface.** `python main.py xau-evidence --tf 15m` produces the
> dossier; `docs/XAU_PROMOTION_EVIDENCE.md` defines the real-host procedure.
> Repository-root-relative defaults make invocation location-independent.
> There is no approve/promote option. Every output hard-reports
> `RESEARCH_ONLY`, `human_approval=OPEN`, `xau_tradeable=false`, and
> `micro_live_unlocked=false`; passing evidence can only set
> `eligible_for_human_review=true`.
>
> **Verification.** Focused P12.12/validation/handoff: **54 passed** in 8.32s.
> Full suite after installing the optional MCP extra: **723 passed, 1 skipped**
> in 111.96s. Compileall and `pip check` pass; the v2.23.0 wheel gate reports
> no duplicate entries.
> The clean checkout CLI exits 1 with zero matched rows, seal `MISSING`, and all
> decision gates closed. All basis fixtures are synthetic and prove mechanics
> only; this checkout has no real store/database and cannot claim real basis,
> sealed-OOS, promotion, or trading evidence.
>
> **Previous session (`arena/01a006ca-sky`): v2.22.0 — P12.11 source
> provenance.** Rebuilt `.venv`, ran the inherited suite → **681 pass / 1 skip**
> (the P12.10 baseline), then built source-separated saved keys.
>
> **The problem.** Every decided row was filed under `plan_type` or
> `plan_type::regime` and nothing else — the price series that produced it was
> invisible to the learning loop. A row graded on Binance BTCUSDT spot and a
> row graded on a bid-only Dukascopy XAUUSD import landed in the **same**
> calibration entry, so a research backtest on a venue we do not trade could
> move the multiplier applied to live signals. The only protection was a human
> remembering not to type `--save`. Measured: the live entry alone is
> `E +0.46R → net +0.29R` at `×1.07`; pooling a `+3.58R` bid-only gold book
> into that key inflated it.
>
> - **`data/provenance.py`** — the source-key algebra.
>   `exchange:market[:price_type]`, with the canonical live series (Binance
>   spot, two-sided) deliberately the **empty string**. That single choice is
>   what makes P12.11 additive: every pre-existing key is byte-identical, and
>   every legacy NULL-provenance row reads as the canonical series — which is
>   what all pre-P12.11 history actually is, not a guess.
> - **Persistence** — `exchange`/`market`/`price_type`/`source_key` on
>   `backtest_results` + `paper_trades`, `source_key` on `calibration`, all by
>   idempotent migration. `StoreClient` stamps the frame; the simulator and
>   `backtest --save` propagate it.
> - **`profile_key(plan_type, regime, source_key)`** appends `@source` for
>   non-canonical series only → `Buy Pullback::TREND_UP@dukascopy:spot:bid`.
> - **Live isolation** — `engine/calibration_hook.apply_calibration()`
>   resolves canonical keys only and never falls back across sources, so a
>   research entry's **boost and its filter** are both unreachable live.
> - **`setup_proven()`** counts evidence on one series (default live); a
>   one-sided (bid/ask-only) series is `research_only` and never `proven` —
>   its printed price is not an executable round trip.
> - **Reporting** — scorecard `by_source` split + `sources` inventory (warns
>   when a book pools series), `--source-key` / `?source_key=` / MCP
>   `source_key` (server **1.10.0**), and `learn` lists the stored series.
> - **Safety direction — strictly additive, strictly tighter.** It can only
>   withdraw trust from a research series, never grant it. Crypto output,
>   legacy keys and the graduation bar are unchanged; no existing test was
>   modified.
> - **Unblocked:** `--save` on a Dukascopy XAU backtest is now permitted.
> - **Docs:** `docs/SOURCE_PROVENANCE.md`; blocker #3 closed in
>   `docs/DUKASCOPY_XAU_ADAPTER.md`.
> - **Versions:** `config.py` / `pyproject.toml` **2.21.0 → 2.22.0**;
>   wheel gate green.
> - **Tests:** +23 in `tests/test_provenance.py` → **704 pass / 1 skip**.

> **Prior session (`arena/01a0069a-sky`): v2.21.0 — P12.10 XAU bid/ask cost model.**
> **Verified first:** rebuilt `.venv`, ran the inherited suite → **671 pass /
> 1 skip** (the P12.9 baseline). Then built the next item.
>
> **The problem.** `calculate_trade_cost()` used a default `CostModel()` with
> `market="perp"`, taker fees (0.05%/side) and funding — appropriate for crypto
> perps but not for spot gold. A bid-only XAUUSD backtest was costed with
> crypto assumptions. The existing `SPREADS["XAUUSD"]` entry existed but was
> never auto-selected. This was blocker #2 of the three recorded against the
> Dukascopy XAU research book.
>
> - **`cost_model_for_symbol()`** — symbol-based cost model resolver. When no
>   explicit `CostModel` is passed, gold instruments (XAU*/GOLD*) get a
>   spot-market model with zero funding, `DEFAULT_GOLD_COMMISSION_PCT = 0.005%`
>   per side ECN commission, and spread as the primary cost.
> - **`is_gold_symbol()`** / **`GOLD_SYMBOL_PREFIXES`** — prefix-based gold
>   detection.
> - **`DEFAULT_GOLD_COMMISSION_PCT`** — 0.005% per side (~$5 per $100k notional).
> - **Auto-detection** — `calculate_trade_cost()` now calls
>   `cost_model_for_symbol(symbol)` when `cost_model` is None, so every XAUUSD
>   call automatically uses gold-specific costs. An explicit `CostModel`
>   argument still overrides auto-detection.
> - **Safety direction — it can only make costs more accurate for gold.**
>   Opt-in by symbol prefix (XAU/GOLD); BTCUSDT, ETHUSDT, PAXGUSDT keep the
>   crypto-perp default unchanged. An explicit `CostModel` always wins over
>   auto-detection. Crypto numbers are byte-identical.
> - **Docs:** `docs/DUKASCOPY_XAU_ADAPTER.md` blocker #2 closed.
> - **Versions:** `config.py` / `pyproject.toml` **2.20.0 → 2.21.0**;
>   wheel gate green.
> - **Tests:** +10 in `tests/test_costs.py` → **681 pass / 1 skip**.

> **Prior session (`arena/01a004b0-sky`): v2.19.0 — optional Dukascopy XAU adapter.**
> - `dukascopy-node` remains an external, version-pinned CSV producer. SKY
>   does not install, vendor, or execute it at runtime.
> - `backfill --from-csv --csv-source dukascopy --price-type bid|ask` accepts
>   its documented epoch-ms OHLC CSV through the existing SHA/sanity/dedupe/gap
>   boundary and stores a separate `dukascopy/spot/XAUUSD` series.
> - Canonical candles now carry `price_type`; old Parquet partitions are
>   additively coerced, rollups preserve the side, and mixed bid/ask imports
>   into one series fail closed.
> - `backtest` / `simulator` store mode now accept `--exchange`, matching
>   validate/scorecard/quality.
> - Existing Binance BTC/ETH and live XAU→PAXG behavior is unchanged. Saving
>   Dukascopy grades into calibration remains prohibited until market-calendar,
>   gold spread/cost, and learning-key provenance work is complete.
> - Guide: `docs/DUKASCOPY_XAU_ADAPTER.md`.
>
> **Earlier this session: P12.8.1 — expectancy-anchor class audit.**
> - **Sweep:** all executable expectancy comparisons against zero or a bar are
>   inventoried in `docs/EXPECTANCY_ANCHOR_AUDIT_2026-08-15.md`.
> - **Remaining path fixed:** `data.simulator.grind_verdict()` now recomputes
>   the micro-live sample proof from counts + `E_net`; a stale `proven=True`
>   cannot override a cost-flipped book, and the gap says `positive net
>   expectancy` rather than the contradictory `all targets met`.
> - **Zero is data:** `paper_progress()` uses `None`-only net→gross fallback;
>   exact-zero net expectancy/wins/R no longer inherit positive gross values.
> - **Surface aligned:** simulator grind output displays labelled `E_NET`.
> - **Operational blocker:** this checkout has neither `data/store/**` nor
>   `data/cryptobrain.db`, so the requested real `backtest --save` + `learn`
>   was not faked with demo data. Commands are recorded in the audit.
> - **Version/tests:** 2.18.0 → **2.18.1**; **633 pass / 1 skip**.

> **Prior session (`arena/01a00490-sky`): P12.8 — the net anchor.**
> P12.6 made every *measurement* net of costs. P12.8 closes the gap it left:
> the two places that **act** on a measurement still read the **gross**
> number, so the desk measured honestly and then decided on the wrong figure.
> - **`data/strategy_score.multiplier_from_score()`** anchored its sign on
>   `E_gross`. Measured: a setup at `E_gross = +0.055R` / `E_net = −0.118R`
>   got multiplier **×1.008** — the engine *raised* confidence on a setup that
>   loses money. Now anchored on `expectancy_net` (gross only as fallback when
>   costs are unknown) → **×0.982**, dampened.
> - **`brain/calibrator.build_profile()`** passes the net anchor; the
>   `CALIBRATE_FILTER` negative filter judges net too.
> - **`brain/risk_gate.setup_proven()`** (A6/B10) now requires positive
>   expectancy **net of costs**; sample floors unchanged. The block message
>   names the failing condition instead of only reprinting sample counts.
> - **`data/database.setup_stats()`** returns `backtest_expectancy_net` /
>   `paper_expectancy_net` (`None` → caller falls back to gross, never guesses);
>   `setup_proven` reports `proven_on: "net" | "gross"`.
> - **Strictly tighter, never looser** — it can only dampen a multiplier or
>   withdraw a "proven". The graduation bar is untouched.
> - **Tests:** +11 in `tests/test_net_anchor.py` (incl. a monotonicity property:
>   the net anchor can never raise a multiplier). Suite **620 → 631 / 1 skip**.
> - **Versions:** `config.py` / `pyproject.toml` **2.17.0 → 2.18.0**.

> **Prior session (`arena/01a0046d-sky`): P12.7 — Monte Carlo risk-of-ruin table.**
> The scorecard says whether the live book is profitable net of costs;
> P12.7 answers *how much size it can survive*. It resamples the decided
> paper-trade outcomes **NET of costs** (filling missing `rr_net` via
> `data.costs.calculate_trade_cost`) and sweeps position size to expose
> expected maximum drawdown, ruin probability, longest losing streak and
> time-to-recovery.
> - **`brain/analytics.py` → `monte_carlo_ruin_table()`** — one computation
>   (invariant #10). Returns `table[]` per risk-% plus a `historical`
>   block from the actual net sequence.
> - **CLI:** `python main.py monte [--risk-pcts ...] [--ruin-threshold 50]
>   [--samples N] [--seed N] [--json]`; `python main.py risk` points to it.
> - **HTTP:** `GET /api/monte`; `monte` key embedded in `GET /api/risk`.
> - **MCP:** root `mcp_server.py` risk tool embeds `ruin_table`;
>   `ai/mcp_server.py` exposes `cryptobrain_monte` and adds `ruin_table`
>   to `cryptobrain_risk`.
> - **Dashboard:** Risk gate card renders the Monte Carlo sweep table.
> - **Versions:** `config.py` / `pyproject.toml` **2.16.0 → 2.17.0**;
>   root MCP server **1.8.0 → 1.9.0**.
> - **Tests:** +7 in `tests/test_monte_carlo.py`; suite **613 → 620 pass
>   / 1 skip**.

> **Prior session (`arena/01a00446-sky`, P12.5): Strategy Score on the calibrator.**
> `data/strategy_score.py` scores each calibration key 0–100 as
> `E_R × sample-quality × regime-fit × execution` (weighted geometric
> mean, NET of costs), where sample-quality is P12.4's
> `backtest_quality_score()` in full; the calibrator multiplier is now a
> trust dial (`mult = clamp(1 + E_gross × gain × trust, …)`,
> `trust = clamp(score/50, 0.6, 1.5)`). Surfaces: `learn` CLI,
> `/api/learning`, dashboard Calibration card. Version 2.15.0 → 2.16.0.
> Costs are now integrated into every performance measurement across the desk:
> `E_net = E_gross − fees − slip − funding`, where every term is expressed
> in **R units per trade**.
>
> `data/costs.py` implements `CostModel` and `calculate_trade_cost()`:
> - **Fees + spread lead the cost calculation**: at the measured BTC median
>   stop distance (0.823% of entry), standard taker round-trip fee (0.05%/side =
>   0.10% total) costs **0.1215R** per trade (~35% of gross expectancy), and
>   at typical 1.8h holds **fees are ~45× funding**.
> - **Funding as-of-T**: direction-aware funding looked up from stored
>   derivatives series (`data/derivatives.py`) as of signal timestamp $T$
>   (long pays positive funding, short receives positive funding credit;
>   spot has 0 funding).
> - **Grader & Database Net R**: `GradedPlan` and `backtest_results` /
>   `paper_trades` DB tables gained `rr_net`, `fee_r`, `slip_r`, `funding_r`,
>   `cost_r` via additive migrations in `data/database.py`.
> - **Scorecard Net Metrics & Conditioned Splits**: `data/scorecard.py`
>   computes both gross and net metrics (`expectancy_net`, `win_rate_net`,
>   `pf_net`, `total_r_net`, `max_drawdown_r_net`, `sharpe_net`, `sortino_net`,
>   `calmar_net`, `cost_r`, `fee_r`, `slip_r`, `funding_r`), and conditioned
>   splits by funding regime and CVD order flow (`--conditioned`).
> - **Net Bar Enforcement**: `meets_bar()` in `data/validation.py` and
>   `build_scorecard()` evaluate performance against the restated **NET**
>   bar: $E_{\text{net}} \ge +0.50\text{R}$, $WR_{\text{net}} > 55\%$, $PF_{\text{net}} \ge 1.5$.
> - **Surfaces**: CLI `python main.py scorecard [--no-costs] [--maker] [--conditioned]`,
>   HTTP `GET /api/scorecard`, MCP `scorecard` tool (v1.6.0), and dashboard
>   learning card displaying net expectancy and cost drag breakdown.
> Version **2.12.0 → 2.13.0**. Suite **552 → 567 pass / 1 skip** (+15).

> **Prior session (`arena/01a00034-sky`, merged as PR #22): P12.3.2 — real market data.**
> The first real market data entered the project: Binance spot BTCUSDT 1m,
> 2025-01-01 → 2026-04-30, 696,960 bars, from Binance's official public archive
> (`data.binance.vision`), sha256-pinned and verified on import (`c4ad6029…b934b7`).
> Transported offline via `backfill --from-csv`, rolled up to 15m/1h/4h/1d by P10.3
> rollups. P11, P12.1, and P12.3 re-run on real data: primary 1h horizon loses
> money in every window (train −0.452R, oos −0.101R); 24h horizon is +0.400R gross
> (≈ +0.28R net, below the net bar); Breakout Buy confirmed as prune candidate (−0.630R);
> graduation gate stays honestly closed (+0.348R / 36.8% WR / PF 1.55).
> Version **2.11.1 → 2.12.0**. Suite **539 → 552 pass / 1 skip** (+13).

> **Prior session (`arena/019fffe5-sky`, merged as PR #21): P12.3 — the boxed strategy scorecard.**
> `data/scorecard.py` turns outcomes the grader already decided into **one block**:
> expectancy, win rate, PF, total R, max drawdown, streaks, Sharpe/Sortino/Calmar
> and holding time, split by **long/short**, **regime**, **session** and **setup**.
> Three surfaces read the identical report (invariant #10): CLI, HTTP, and read-only MCP.
> Holding time is captured at grading time: `GradedPlan.holding_bars` / `holding_hours`.
> P12.3.1 unified same-bar tie-break (conservative stop-first).
> Version **2.10.0 → 2.11.1**. Suite **492 → 539 pass / 1 skip** (+47).

> **Prior session (`arena/019ffb14-sky`, merged as PR #20): P12.2 — lookahead validation.**
> Added `data.validation.scan_lookahead()` and `python main.py validate lookahead`:
> deterministic stdlib-AST scan that fails closed on explicit future-peeking `shift(-n)`
> calls. Version **2.9.0 → 2.10.0**. Suite **488 → 492 pass / 1 skip**.

> **Prior session (`arena/019ffad5-sky`, merged as PR #18): P10.8–P10.12.**
> P10 data infrastructure fully delivered: Lightweight Charts candlestick/volume pane,
> FUTURES/FLOW market-tab cards, WebSocket tier with reconnect/backoff, store-backed
> backtester (`run_backtest_on_store`), feature store (`data/feature_store.py`).

---

## Project

**CryptoBrain / SKY** — multi-source, multi-indicator, conditional-signal
trading engine for BTC, ETH, and XAUUSD/GOLD with a strict human-approval
gate. **Read-only by design** — the engine *cannot* place a real exchange
order; the human approves, the paper-runner executes, the engine proposes.
The full proposition, sources, and progression ladder are in
[`BLUEPRINT.md`](./BLUEPRINT.md). The history of the two-upstream merge
is in [`MERGE_NOTES.md`](./MERGE_NOTES.md). The professional trading
plan (18 phases, 15-item rulebook) is in
[`PROFESSIONAL_PLAN_DECISIONS.md`](./PROFESSIONAL_PLAN_DECISIONS.md).

---

## The aim (never changes)

**Become a fully independent, consistently profitable trader.**
Independence has two halves: **decision independence** (our own engine
+ risk gate + approval loop — ✅ done, P1–P9) and **data independence**
(our own stored market history — ✅ P10.1–P10.12 shipped, with real BTC
market data imported and verified; research-validation tooling — ✅
P12.1–P12.15 shipped, plus the P12.15 execution-metric follow-up). The next executable work is the real-host XAU evidence
run plus continued canonical paper proof. **Micro-live remains blocked** until the
unchanged graduation report says READY and the user explicitly approves it.
Every phase below is ordered by how directly it moves those two lines.

---

## Current phase

**P21 Android companion contract — shipped v2.37.0.** `ops/android_companion.py`
(Keystore token contract, biometric re-check policy, online-only mutations,
deep links), `companion … --platform android` + `hub pair --platform android`,
unsigned APK recipe only. P20 Windows and P19 Hub contracts remain shipped.
Next product code is **P22 signed release engineering**.
P11 real-paper grind remains parallel. P12.1–P12.18 tooling is shipped.

**P12 (SKY Quant Validation Engine) — P12.1–P12.15 shipped, including the P12.15 execution-metric follow-up.**
P10 (data infrastructure) is fully shipped (P10.1–P10.12, PR #18); P11 grind
re-run on real BTC data and the graduation gate is honestly closed (+0.348R
gross, negative net on 1h/4h primary). Freqtrade rejected (F1–F8);
Backtrader rejected (BT1–BT8). The Dukascopy XAU research book now has
calendar-aware gap detection (P12.9), a gold-specific cost model (P12.10),
source-keyed calibration (P12.11), a read-only PAXG-vs-XAU basis/seal dossier
(P12.12), canonical-only graduation (P12.13/P12.14), and canonical-only live
risk controls (P12.15). Tooling blockers are closed, but **promotion evidence
is not**: this checkout has no real basis measurement or XAU seal, approval is
open, and XAU remains non-tradeable. Open items: real-host evidence, the P11
paper gate, and TODO-8; micro-live is blocked. TODO-7 is complete.

| Phase | Theme | Status | Notes |
|---|---|---|---|
| P1 | RAG Library | ✅ Complete | `brain/library.py`, `brain/ask.py` |
| P2 | LLM Reasoning | ✅ Complete | `brain/brief.py`, `ai/llm_brain.py` |
| P3 | Autonomous Hands | ✅ Complete | `brain/agents.py`, `agent_runs` table |
| P4 | MCP Nervous System | ✅ Complete | `mcp_server.py` (zero-dep stdio JSON-RPC 2.0) |
| P5 | Immune System | ✅ Complete | `brain/immune.py` |
| P6 | Hidden Alpha & Variance | ✅ Complete | `engine/hidden_alpha.py`, `engine/execution.py`, `engine/correlation.py`, `brain/analytics.py` |
| P7 | Agent Surface (SKILL + CLI) | ✅ Complete | `SKILL.md`, `python main.py doctor`, `python main.py skill` |
| P8 | Source Channels (router) | ✅ Complete | `brain/channels.py` + `/api/channels` + dashboard "Channels" panel |
| **P9** | **Capability Endpoints** | **✅ Complete** | MCP 13 tools (incl. `desk_status`, `readiness`); readiness strip on all surfaces; root CI runs offline suite + wheel gate (TODO-7 complete) |
| **P11** | **Paper-book proof** | 🔄 In progress | First grind shipped (38,439 decided; all four primary setups ≥100/20; compliance 100%); first real-data grind shipped (+8,300 bt / +494 paper). Gate honestly closed. |
| **P10** | **Data infrastructure + market terminal** | ✅ Complete | **P10.1–P10.12 shipped** (PR #18): store, backfill, gaps/rollups, derivatives, quality pillar, Bybit, cross-exchange, Lightweight Charts, futures/flow cards, WS tier, store-backtester, feature store. [`docs/DATA_INFRASTRUCTURE_ROADMAP.md`](docs/DATA_INFRASTRUCTURE_ROADMAP.md) |
| **P12** | **Quant Validation Engine** | ✅ Complete | **P12.1–P12.15 shipped** — locked/sealed validation, lookahead guard, scorecard, real-data path, fees-first `E_net`, effective sample size, quality/strategy scores, Monte Carlo survivability, net decision anchor, calendars, XAU costs, source-separated saved keys, read-only XAU promotion evidence, canonical-only global graduation, simulator-free graduation discipline, and canonical-only live risk controls (loss limits, drawdown ladder, Kelly, MC, business metrics). Tooling completion does not promote XAU: run P12.12 on the real-data host, retain human review, and keep micro-live locked until the unchanged global bar says READY plus explicit approval. |

Full phase matrix: [`AI_ANATOMY_ROADMAP.md`](./AI_ANATOMY_ROADMAP.md).
Full P7/P8/P9 plan with risk + rollback: [`ROADMAP_AGENT_REACH_UPGRADE.md`](./ROADMAP_AGENT_REACH_UPGRADE.md).

---

## Completed work

### Session 2026-08-16 (this branch `arena/01a008d1-sky`): v2.23.2 / P12.14 — graduation discipline isolation

Started as a post-PR-#36 safety review, then built the fix it found.

- `data/database.py`: `SignalDB.discipline_rows()` — decided, `sim_key IS NULL`,
  single-source paper trades LEFT JOINed to `journal_entries` (canonical `""`
  by default, legacy NULL provenance included).
- `brain/journal.py`: `graduation_discipline()` — eligible / journaled /
  missing_journals / violations / compliant / compliance / source, with
  `compliance = compliant / eligible` and `None` on an empty book;
  `describe_discipline()` for human surfaces. `violation_rate()` unchanged.
- `data/simulator.py`: `graduation_status(..., discipline=...)` treats the
  payload as authoritative, echoes it as `graduation["discipline"]`, and
  `format_graduation()` prints the population behind the criterion.
- Surfaces rewired to that one computation: `main.py` simulator gate
  (+`discipline` in `--json`), `brain/agent.py` `ask` / `graduation_report()` /
  `desk_status()`, `format_desk_status()` discipline line, dashboard desk card
  **Discipline** row (`/api/desk`, MCP inherit it).
- `tests/test_graduation_discipline.py`: 10 regressions — simulator journals,
  research journals, `followed_rules=None`, missing journals, undecided trades,
  legacy NULL rows, honest-book control, no primary-family restriction,
  four-surface parity, and stale-`compliance` override.
- `ops/probes/p12_14_discipline_probe.py`: pooled-vs-isolated harness, exit
  non-zero if any case fails open. Contract/report:
  `docs/HANDOVER_2026-08-16_P12_14.md`.
- Version `2.23.1 → 2.23.2`. Verification: **736 pass / 1 skip**; compileall,
  `pip check`, v2.23.2 wheel gate pass. Pushed; **PR #37** open with green CI.

**Files changed:** `data/database.py`, `brain/journal.py`, `data/simulator.py`,
`brain/agent.py`, `main.py`, `web/app.py`, `config.py`, `pyproject.toml`,
`tests/test_graduation_discipline.py`, `tests/test_agent.py`,
`ops/probes/p12_14_discipline_probe.py`,
`docs/HANDOVER_2026-08-16_P12_14.md`, `ARCHITECTURE.md`, `CHANGELOG.md`,
`TODO.md`, `SESSION_STATE.md`.

### Session 2026-08-16 (branch `arena/01a008b9-sky`): v2.23.1 / P12.13 — graduation source isolation

Inherited merged P12.12 at `5345e9e`; branch and `origin/main` were identical.
Review found one remaining P12.11 source leak in the permission path and fixed
it without changing the graduation bar or adding execution capability.

- `data/simulator.py`: `paper_progress()` now reads only canonical live
  outcomes from both books (`COALESCE(source_key, '') = ''`), preserving legacy
  NULL rows. Progress carries explicit provenance.
- `grind_verdict()` / `graduation_status()` veto explicit non-canonical
  progress even when the quantitative bar passes; human and JSON output expose
  the evidence source.
- `tests/test_provenance.py`: +3 regressions prove positive/negative research
  books cannot move canonical progress, legacy rows remain visible, and a
  perfect bid-only research book cannot graduate.
- Repository-state correction: PR #35 recorded merged, TODO-7 recorded done,
  root CI's two passing jobs verified, obsolete nested workflow copy removed;
  TODO-8 remains unverified due GitHub API HTTP 403.
- Version `2.23.0 → 2.23.1`; docs/roadmaps/source contract reconciled.
- Verification: focused **41 pass**; full **726 pass / 1 skip**; compileall,
  `pip check`, and wheel duplicate-entry gate pass.

**Files changed:** `data/simulator.py`, `tests/test_provenance.py`, `config.py`,
`pyproject.toml`, `README.md`, `ARCHITECTURE.md`, `AI_ANATOMY_ROADMAP.md`,
`TODO.md`, `CHANGELOG.md`, `docs/SOURCE_PROVENANCE.md`,
`docs/HUMAN_ACTIONS.md`, `docs/INFRASTRUCTURE_LAYERS.md`, removal of obsolete
`docs/.github/workflows/ci.yml`, and this handoff.

### Session 2026-08-16 (this branch `arena/01a006ec-sky`): P12.12 — read-only PAXG-vs-XAU promotion evidence

Inherited baseline: P12.11 at `f34540e`. Built the next permissible evidence
step without order placement, calibration pooling, seal mutation, or promotion.
Tests **704 → 723 pass / 1 skip** (+19 net). Version **2.22.0 → 2.23.0**.

- Added `data/gold_basis.py`: separate canonical reads, exact-timestamp inner
  alignment, basis/coverage/tracking statistics, and SHA-256 reproducibility
  fingerprint. No resampling, interpolation, forward fill, or calendar
  synthesis.
- Enforced one-sided Dukascopy provenance: exactly one of `bid`/`ask`; missing,
  two-sided, or mixed price types fail closed.
- Added read-only inspection of `dukascopy_spot_XAUUSD_<tf>` envelopes:
  expected source metadata, payload fingerprint, exact unchanged criteria, all
  four validation windows, and reseal history are exposed. Nothing can create
  or reseal evidence.
- Added `python main.py xau-evidence` with repository-root-relative defaults,
  human and JSON reports, minimum-overlap controls, and no approval switch.
- Added `docs/XAU_PROMOTION_EVIDENCE.md`; updated operator, architecture,
  roadmap, README, changelog, TODO, and this handoff.
- Safety output is invariant: `RESEARCH_ONLY`, approval `OPEN`, XAU not
  tradeable, micro-live locked. Passing evidence means human-review eligibility
  only.
- Focused verification: 54 pass. Full suite: 723 pass / 1 skip. Clean-checkout
  CLI exits 1 because no real store/seal exists; no evidence was manufactured.

**Files changed:** `data/gold_basis.py` (new), `tests/test_gold_basis.py` (new),
`docs/XAU_PROMOTION_EVIDENCE.md` (new), `main.py`, `config.py`,
`pyproject.toml`, `README.md`, `docs/DUKASCOPY_XAU_ADAPTER.md`,
`ARCHITECTURE.md`, `AI_ANATOMY_ROADMAP.md`, `TODO.md`, `CHANGELOG.md`, and
`SESSION_STATE.md`.

### Session 2026-08-16 (branch `arena/01a006ca-sky`): P12.11 — source provenance in saved keys

Branched from `main` @ `85bcfd7d` (P12.10 merged). Inherited suite re-verified at
**681 pass / 1 skip** before any change. 0 regressions.
Tests **681 → 704 pass / 1 skip** (+23). Version **2.21.0 → 2.22.0**.
(`config.py` and `pyproject.toml` bumped in step; wheel gate green.)

**Why:** a graded row's calibration key carried `plan_type` and `regime` but
not the price series that produced it, so a bid-only Dukascopy XAUUSD research
backtest pooled into the same entry as the live Binance book and could raise
the confidence multiplier applied to live signals. `--save` was prohibited for
that adapter purely because a human might forget.

**What shipped:** `data/provenance.py` (source-key algebra, canonical live
series = `""`); provenance columns on `backtest_results` / `paper_trades` /
`calibration` by idempotent migration; `profile_key()` gains a source
dimension appended only for non-canonical series; the live calibration hook
resolves canonical keys only (boost *and* filter isolated); `setup_proven()`
counts one series and never proves a one-sided one; scorecard `by_source`
split + `sources` inventory + `--source-key` / `?source_key=` / MCP
`source_key` (server 1.10.0); `learn` lists stored series.

**Result:** measured on a seeded book, the live entry stays `E +0.46R → net
+0.29R` / `×1.07` whether or not a `+3.58R` research book is present — it is
now a separate key. Dukascopy `--save` is unblocked.
Docs: [`docs/SOURCE_PROVENANCE.md`](docs/SOURCE_PROVENANCE.md).

**Files changed:** `data/provenance.py` (new), `tests/test_provenance.py`
(new), `docs/SOURCE_PROVENANCE.md` (new), `data/database.py`,
`data/scorecard.py`, `data/backtester.py`, `data/simulator.py`,
`data/store.py`, `brain/calibrator.py`, `brain/risk_gate.py`,
`engine/calibration_hook.py`, `main.py`, `web/app.py`, `mcp_server.py`,
`docs/DUKASCOPY_XAU_ADAPTER.md`, `config.py`, `pyproject.toml`,
`CHANGELOG.md`, `SESSION_STATE.md`, `TODO.md`.

**Known issues / not done:** this checkout still has neither `data/store/**`
nor `data/cryptobrain.db`, so the P12.11 behaviour was verified against a
seeded temporary database rather than the real book — the calibration profile
on the host holding real data must be recomputed with `learn` to pick up
source keys (existing rows migrate as canonical, so the live profile does not
change). Parallel bid/ask storage and an as-of spread model remain a later
schema milestone.

### Session 2026-08-15 (branch `arena/01a0069a-sky`): P12.10 — XAU bid/ask cost model

Branched from `main` @ `d9410b90` (P12.9 merged). Inherited suite re-verified at
**671 pass / 1 skip** before any change. 0 regressions.
Tests **671 → 681 pass / 1 skip** (+10). Version **2.20.0 → 2.21.0**.
(`config.py` and `pyproject.toml` bumped in step; wheel gate green.)

**Why:** `calculate_trade_cost()` used a default `CostModel()` with
`market="perp"`, taker fees (0.05%/side) and funding — appropriate for crypto
perps but not for spot gold. A bid-only XAUUSD backtest was costed with crypto
assumptions, giving a misleading cost picture. This was blocker #2 of three
against the v2.19.0 Dukascopy XAU research book.

**What shipped:**
- `data/costs.py` — new `cost_model_for_symbol()` resolver auto-selects a
  spot-market model for gold instruments (symbols starting with `XAU` or `GOLD`):
  no funding, `DEFAULT_GOLD_COMMISSION_PCT = 0.005%` per side ECN commission,
  spread as the primary cost via the existing `SPREADS["XAUUSD"]` entry.
- `is_gold_symbol()` / `GOLD_SYMBOL_PREFIXES` — prefix-based detection.
- `calculate_trade_cost()` — when `cost_model` is None, calls
  `cost_model_for_symbol(symbol)` so every XAUUSD call auto-uses gold costs.
  An explicit `CostModel` argument still overrides auto-detection.
- `docs/DUKASCOPY_XAU_ADAPTER.md` — blocker #2 marked closed.

**Invariant kept:** Opt-in by symbol prefix, never by guess. BTCUSDT, ETHUSDT,
PAXGUSDT keep the crypto-perp default unchanged. An explicit `CostModel` always
wins over auto-detection. Crypto numbers are byte-identical.

**Files changed:** `data/costs.py`, `tests/test_costs.py`, `config.py`,
`pyproject.toml`, `CHANGELOG.md`, `TODO.md`, `SESSION_STATE.md`,
`docs/DUKASCOPY_XAU_ADAPTER.md`.

### Session 2026-08-15 (this branch `arena/01a00521-sky`): P12.9 — market calendars

Branched from `arena/01a004b0-sky` @ `94a6de0`. Inherited suite re-verified at
**636 pass / 1 skip** before any change. 0 regressions.
Tests **636 → 671 pass / 1 skip** (+35). Version **2.19.0 → 2.20.0**.
(`config.py` and `pyproject.toml` bumped in step; wheel gate green.)

**Why:** every quality check assumed a 24/7 market, so "the venue was shut" and
"our collection broke" were the same event. A complete week of spot gold holds
~53h of scheduled closure, which the crypto-first logic read as a 30%+ gap
fraction and a dead feed — quarantining a *healthy* series. This was blocker #1
of three against the v2.19.0 Dukascopy XAU research book.

**What shipped:**
- `data/calendar.py` (new) — `MarketCalendar` protocol; `crypto-24x7` and
  `xau-otc` (Sun 18:00 ET open, Fri 17:00 ET close, 17:00–18:00 ET daily break,
  1 Jan / 25 Dec closed), DST-aware via stdlib `zoneinfo`; `expected_bars`,
  `open_bars_between`, `closed_bar_count`, `split_by_session`, `calendar_for`,
  `get_calendar`, `describe`.
- `data/gaps.py` — `detect_gaps(frame, tf, calendar=None)` skips spans that are
  entirely scheduled closure and counts only owed OPENs in partial ones.
- `data/quality.py` — `checks_on_frame(..., calendar=None)` measures `expected`
  and `age_mult` in trading bars, adds `calendar` / `market_open` /
  `closed_bars`; `series_health` / `series_item` resolve the calendar from the
  series identity; `verdict_for` reports `market closed — clean`.
- `data/backfill.py` — CSV import report carries `calendar` and
  `closed_session_bars`; `gaps_found` no longer counts the gold weekend.
- `main.py` — new `calendar` subcommand (`--symbol --tf --exchange --market
  --calendar --at --series --root --json`); the `backfill --from-csv` output
  prints the calendar and a calendar-aware `gaps_remaining`.
- `docs/MARKET_CALENDAR.md` (new); blocker #1 closed in
  `docs/DUKASCOPY_XAU_ADAPTER.md`.

**Invariant kept:** it can only remove false alarms. Opt-in by venue (unknown
venues, unknown symbols and Binance `PAXGUSDT` all keep 24/7 rules), crypto
outputs byte-identical, and in-session holes / stale-during-session / corrupt
OHLC all still quarantine. The graduation bar is untouched.

**Files changed:** `data/calendar.py` (new), `data/gaps.py`, `data/quality.py`,
`data/backfill.py`, `main.py`, `tests/test_calendar.py` (new), `config.py`,
`pyproject.toml`, `ARCHITECTURE.md`, `docs/MARKET_CALENDAR.md` (new),
`docs/DUKASCOPY_XAU_ADAPTER.md`, `CHANGELOG.md`, `SESSION_STATE.md`, `TODO.md`.

### Session 2026-08-15 (this branch `arena/01a00490-sky`): P12.8 — the net anchor

Branched from `main` @ `2dd49a6`. 0 regressions.
Tests **620 → 631 pass / 1 skip** (+11). Version **2.17.0 → 2.18.0**.

**The gap this closed.** P12.6 made every measurement net of costs, and the
desk has been reporting `E_net` honestly ever since. But the two places that
*act* on a measurement were never migrated, so the project measured with one
number and decided with another:

| site | read | consequence |
|---|---|---|
| `multiplier_from_score()` | `E_gross` | `+0.055R` gross / `−0.118R` net → **×1.008 boost** on a losing setup |
| `setup_proven()` (A6/B10) | `backtest_expectancy`, `paper_expectancy` (gross) | a cost-flipped setup could be called **proven** |

**What shipped:**
- `data/strategy_score.py` — `multiplier_from_score(..., expectancy_net=None)`;
  the sign anchor is the net number when known, gross only as fallback.
  The cost-flipped case now yields **×0.982** instead of ×1.008.
- `brain/calibrator.py` — `build_profile()` passes `expectancy_net`; the
  `CALIBRATE_FILTER` negative-expectancy filter judges net too; `describe()`
  states which anchor is in use.
- `brain/risk_gate.py` — `setup_proven()` requires positive **net** expectancy
  where available, returns `proven_on: "net" | "gross"`, and the gate's block
  message names the failing condition (expectancy vs. sample floors).
- `data/database.py` — `setup_stats()` returns `backtest_expectancy_net` /
  `paper_expectancy_net` from the stored `rr_net` column; `None` when absent.
- `tests/test_net_anchor.py` (new) — 11 tests, including a monotonicity
  property: the net anchor can only lower a multiplier, never raise one.

**Invariant kept:** strictly tighter, never looser. No change to the
graduation bar, the sample floors, or any read-only guarantee.

**Files changed:** `data/strategy_score.py`, `brain/calibrator.py`,
`brain/risk_gate.py`, `data/database.py`, `tests/test_net_anchor.py` (new),
`config.py`, `pyproject.toml`, `CHANGELOG.md`, `SESSION_STATE.md`, `TODO.md`.

### Session 2026-08-15 (branch `arena/01a0046d-sky`): P12.7 — Monte Carlo risk-of-ruin table

Branched from `main` @ `5384a84`. 0 regressions.
Tests **613 → 620 pass / 1 skip** (+7). Version **2.16.0 → 2.17.0**.
(`config.py` and `pyproject.toml` bumped in step.)

**What shipped:**
- `brain/analytics.py` → `monte_carlo_ruin_table()` — resamples the NET
  realised paper book (costs included; missing `rr_net` is computed via
  `data.costs.calculate_trade_cost`). For each swept risk %/trade it
  returns expected max drawdown, ruin probability, prob final equity below
  start, terminal median/p5/p95, median longest losing streak and
  median/mean time-to-recovery (trades). A `historical` block records the
  actual sequence's longest loss streak, median/max TTR and max drawdown.
- `main.py` — new `monte` subcommand prints the boxed table (human or
  `--json`); `python main.py risk` points the user to it.
- `web/app.py` — `GET /api/monte` + `monte` key embedded in `GET /api/risk`;
  dashboard Risk card renders the sweep table and historical metrics.
- `mcp_server.py` — root `risk` tool embeds `ruin_table`.
- `ai/mcp_server.py` — new `cryptobrain_monte` tool; `cryptobrain_risk`
  also returns `ruin_table`.
- `tests/test_mcp_server.py` — `TOOL_NAMES` updated for the new tool.
- `tests/test_monte_carlo.py` (new) — 7 tests covering empty book,
  structure, drawdown scaling with size, seed determinism, historical
  streak, sim-sample exclusion, direct `rows=` input.
- Versions: `config.py` / `pyproject.toml` **2.16.0 → 2.17.0**; root MCP
  server **1.8.0 → 1.9.0**.

**Files changed:** `brain/analytics.py`, `main.py`, `web/app.py`,
`mcp_server.py`, `ai/mcp_server.py`, `tests/test_mcp_server.py`,
`tests/test_monte_carlo.py` (new), `config.py`, `pyproject.toml`,
`CHANGELOG.md`, `TODO.md`, `SESSION_STATE.md`.

### Session 2026-08-15 (this branch `arena/01a00446-sky`): P12.5 — Strategy Score on the calibrator

Branched from `main` @ `fd4aa51` (PR #25 merged). 0 regressions.
Tests **598 → 613 pass / 1 skip** (+15). Version **2.15.0 → 2.16.0**.

**What shipped:**
- `data/strategy_score.py` — strategy score 0–100 per calibration key as
  `E_R × sample-quality × regime-fit × execution` (weighted geometric
  mean, NET of costs; sample-quality = P12.4's
  `backtest_quality_score()` in full).
- `brain/calibrator.py` — trust dial multiplier from score; profile entries
  gain `strategy_score`, `strategy_band`, `strategy_components`,
  `expectancy_net`.
- Surfaces: `learn` CLI, `GET /api/learning`, dashboard Calibration card.
- Tests: 15 new (`tests/test_strategy_score.py`).

### Session 2026-08-15 (this branch `arena/01a00431-sky`): P12.4 — Backtest Quality Score 0–100

Branched from `main` @ `e07fa43` (PR #24 merged). 0 regressions.
Tests **573 → 598 pass / 1 skip** (+25). Version **2.14.0 → 2.15.0**.
MCP `SERVER_VERSION` **1.7.0 → 1.8.0**.

**What shipped:**
- `data/quality_score.py` (new module) — pure `backtest_quality_score(rows, …)`:
  edge (E_net vs bar, shape-discounted), curve robustness (top-5
  concentration / max-DD ÷ |total R| / chronological segments), sample
  confidence (N_eff vs min_decided + CI95 significance), and the BT5
  parameter-plateau test that caps an isolated-peak edge at 50. Empty
  books degrade to `quality: None` with a reason.
- `run_quality_sweep()` + `python main.py quality` — store-only plateau
  sweep re-grading `min_confidence ± 5` (clamped [40, 90], deduplicated,
  base point guaranteed; `grade_fn` injectable for offline tests).
- `data/scorecard.py` — `build_scorecard(..., quality=True)` embeds the
  block; `scorecard_from_db` / `scorecard_from_store` forward the flag;
  `print_scorecard` prints it.
- `main.py` — `scorecard --quality`; new `quality` subcommand.
- `web/app.py` — `/api/scorecard?quality=1`; dashboard `STRATEGY SCORECARD`
  card renders the quality block.
- `mcp_server.py` — `scorecard` tool `quality` argument; v1.8.0.
- Tests: 25 new (`tests/test_quality_score.py`).

**Measured on the demo store (sample CSV, 500 × 15m bars, spot):**
- `scorecard --source store --quality` → **25.9/100 fragile** (edge 0,
  robustness 38, sample 50, plateau n/a) — a losing book scores like a
  losing book.
- `quality` → **23.3/100 fragile**, plateau 0.0 (0/3 conf points
  positive), `plateau_cap: True` — the isolated-peak guard is live.

**Files changed:** `data/quality_score.py` (new), `data/scorecard.py`,
`main.py`, `web/app.py`, `mcp_server.py`, `tests/test_quality_score.py`
(new), `pyproject.toml`, `CHANGELOG.md`, `TODO.md`, `README.md`,
`docs/DATA_INFRASTRUCTURE_ROADMAP.md`, `docs/HANDOVER_2026-08-15_P12_4.md`
(new), `SESSION_STATE.md`.

### Session 2026-08-15 (this branch `arena/01a003f9-sky`): P12.6 — fees-first `E_net` & conditioned expectancy

Branched from `main` @ `58ed864` (PR #22 merged). 0 regressions.
Tests **552 → 567 pass / 1 skip** (+15). Version **2.12.0 → 2.13.0**.
MCP `SERVER_VERSION` **1.5.0 → 1.6.0**.

**What shipped:**
- `data/costs.py` (new module) — `CostModel` and `calculate_trade_cost()`,
  `get_funding_rate_as_of_t()`. Models taker/maker/spot fees, spreads,
  slippage, and direction-aware funding in R units scaled to stop distance.
- `data/backtester.py` — `GradedPlan` and `_evaluate()` attach `rr_net`,
  `fee_r`, `slip_r`, `funding_r`, `cost_r`. `_aggregate()` computes gross
  and net metrics.
- `data/database.py` — `_migrate()` adds `rr_net`, `fee_r`, `slip_r`,
  `funding_r`, `cost_r` to `backtest_results` and `paper_trades`.
  `save_backtest_rows()` persists all net metrics.
- `data/scorecard.py` — `trade_stats()` and `build_scorecard()` calculate
  gross and net performance (`expectancy_net`, `win_rate_net`, `pf_net`,
  `total_r_net`, `max_drawdown_r_net`, `sharpe_net`, `sortino_net`,
  `calmar_net`, `cost_r`, `fee_r`, `slip_r`, `funding_r`).
  `conditioned_splits()` supports funding regime and CVD order-flow splits.
  `print_scorecard()` prints the boxed gross-vs-net comparison and cost drag.
- `data/validation.py` & `data/simulator.py` — `meets_bar()` and
  `graduation_status()` evaluate against the restated **NET** bar.
- `main.py` — `python main.py scorecard [--no-costs] [--maker] [--conditioned] [--json]`.
- `web/app.py` & `mcp_server.py` — `/api/scorecard` and MCP `scorecard` tool
  exposing net metrics, cost drag, and conditioned splits.

**Measured cost impact on real BTCUSDT 15m data:**
- Expectancy: **+0.001R gross → −0.369R net** (cost drag −0.370R: fee 0.262R, slip 0.105R, funding 0.004R).
- `Sell Pullback` (+0.974R net, PF 3.99 net) and `FVG Retest Sell` (+1.161R net, PF 6.43 net) survive net.
- `Breakout Buy` (−0.904R net, PF 0.225 net) confirmed as heavy drag.

---

## Remaining work (prioritised)

0. **P22 signed release engineering** — CI install/smoke matrix (Ubuntu pkg,
   Windows pkg, Android build), code signing (Windows + Android + signed Debian
   repo), reproducible SHA-256 artifacts, SBOM + dependency/license inventory,
   stable/beta channels, in-app System page, privacy-respecting diagnostics
   export, documented incident/support/rollback paths. Do not claim signed
   artifacts until produced on a real build host.
1. **Run P12.12 on the real-data host** — rerun `learn` to adopt source keys,
   build/retain the locked Dukascopy XAU validation evidence, then archive
   `python main.py xau-evidence --json`. Do not reseal from the audit command.
2. **TODO-11 (P11)** — continue the paper-book grind/live-data proof;
   the unchanged graduation bar remains closed.
3. **Micro-live at trivial size — BLOCKED** until the graduation report says
   READY and the user explicitly approves it. Slippage, partial fills, and
   latency become measurable only after both gates open.
4. **TODO-8** — a repo admin verifies/protects `main` (require PR and both CI
   jobs). The integration cannot read or change protection: HTTP 403.
5. **TODO-9 / TODO-10** — Dify then LibreChat (parked).

---

## Known problems / caveats

1. **D1–D5 are answered.** See `ROADMAP_AGENT_REACH_UPGRADE.md` §4.
2. **Arena's GitHub integration: one PR per chat session.** Do the work,
   then open **one** PR as the closing step.
3. **`mcp>=1.0` is listed in `requirements.txt` but not required**
   for the zero-dep `mcp_server.py`.
4. **Immune system reports `CRITICAL` in `DEMO_MODE=1`** because the
   committed sample data is stale by design. Expected offline.
5. **TODO-7 is complete.** Root `.github/workflows/ci.yml` runs the offline
   suite and wheel gate; the active jobs have passed on `main` (run
   `31907327643` was the recorded P12.12 verification). The obsolete nested
   workflow copy was removed.
6. **`CHANGELOG.md` is current** through v2.23.4, including the P12.15
   execution-metric follow-up.
7. **Real market data is imported offline**: Binance spot BTCUSDT 1m
   (696,960 bars, sha256-pinned `c4ad6029…b934b7`). The store is
   gitignored; re-import with `backfill --from-csv` if starting in a clean sandbox.
8. **Costs are now integrated via P12.6**: `E_net = E_gross − fees − slip − funding`.
   The graduation bar is enforced NET of costs.
9. **Sample counts are now overlap-corrected (P12.3.3)**: the scorecard
   reports `N_eff = N / overlap` and widened CI/SE. The `min_decided`
   floor still reads raw N (flagged via `n_eff_below_min_decided`) — the
   floor revisit is the next decision, not this one.
10. **P12.4 quality scores what P12.6/P12.3.3 made real**: the plateau
    sweep (`python main.py quality`) re-grades the stored series at
    `min_confidence ± 5` — on a clean sandbox with no store it returns a
    clear error, never a score. The `scorecard --quality` block shows
    "plateau n/a" without that re-grade sweep.
11. **P12.5 scores what the calibrator already gates**: only keys with
    `n >= min_n` (default 100) get a strategy score — below the gate there
    is no entry at all, exactly as before. The score is a report on what
    passed the gate, never a gate-bypass. It is computed from the key's
    decided rows via the scorecard's row adapters; the multiplier keeps
    the gross-expectancy sign anchor and is only *modulated* by the score
    (trust floor 0.6) — a deliberate middle ground between the old formula
    and a hard score-only gate.
12. **Freqtrade was reviewed and rejected (F1–F8)** (`docs/FREQTRADE_REVIEW.md`).
13. **Backtrader was reviewed and rejected (BT1–BT8)** (`docs/BACKTRADER_REVIEW.md`).
14. **`config.VERSION` was stale after P12.4** (2.14.0 instead of 2.15.0) —
    fixed to **2.17.0** in this session; `config.py` and `pyproject.toml` are
    now in step.
15. **P12.8 changed decisions, not measurements.** The scorecard, quality
    score and strategy score were already net-correct; only the calibrator
    multiplier and the proven gate were reading gross. If a setup's
    multiplier or `proven` flag looks *worse* than in a pre-2.18.0 run, that
    is the fix working — the earlier value was measuring the wrong number.
    Where `rr_net` is absent (old rows, costs disabled) behaviour falls back
    to gross exactly as before, so historical books do not silently change
    meaning; `proven_on` says which anchor was used.
16. **P12.7 is a report, not a gate-bypass**: the Monte Carlo ruin table
    reads the decided paper book NET of costs and surfaces survivability
    estimates. It does not approve trades, loosen the graduation bar, or
    replace the risk gate.
17. **Dukascopy XAU: adapter blockers and audit tooling are closed; promotion
    is not.** P12.9 closed the market calendar, P12.10 the XAU bid/ask cost
    model, P12.11 calibration-key provenance, and P12.12 the read-only basis /
    seal dossier. `backtest --save` is permitted because its rows land in
    `…@dukascopy:spot:bid` keys and cannot recalibrate the live proxy. The
    real-data host must still produce the PAXG-vs-XAU measurement and passing
    sealed-OOS evidence, followed by explicit human approval. Separable,
    inspectable evidence is the precondition for judgement, not the judgement.
18. **A calendar can only remove false alarms, never hide a hole.** It is
    opt-in by venue: anything not explicitly `dukascopy` + an XAU symbol keeps
    the 24/7 crypto calendar, including Binance `PAXGUSDT`, which really does
    trade 24/7. If a gold series ever *should* be quarantined, it still is —
    stale-during-session, in-session holes and corrupt OHLC are unaffected.
19. **Early/partial closes are deliberately unmodelled.** Only 1 Jan and
    25 Dec are holidays. An unmodelled early close shows up as a real gap
    (visible, safe); an over-broad holiday list would silently swallow one.
20. **The canonical source key is the empty string — do not "tidy" this.**
    `binance/spot/two-sided` → `""` is what keeps P12.11 additive: every
    pre-existing calibration key stays byte-identical and every legacy
    NULL-provenance row reads as the live series (which is what it is).
    Writing it as `"binance:spot"` would silently re-key the entire stored
    profile and orphan the desk's history.
21. **P12.11 isolates the filter as well as the boost.** A research entry
    marked `filtered` must not block a live signal either — a series we do
    not trade gets no vote in both directions. Both are covered by tests.
22. **P12.12 exact-time alignment is intentionally sparse.** Never resample,
    interpolate, forward-fill, or calendar-synthesize PAXG/XAU observations to
    improve overlap. Low overlap is evidence quality information and fails
    closed below `--min-overlap`.
23. **PAXG-vs-XAU basis is not pure gold dislocation.** PAXGUSDT versus XAUUSD
    includes the USDT/USD quote basis. Keep that caveat on every interpretation
    and never pool either series into calibration.
24. **Seal inspection is not seal creation.** P12.12 validates source metadata,
    exact locked criteria, envelope integrity, four windows, and reseal history
    without writing any seal. A resealed history remains visible for human
    scrutiny even when the latest payload passes.
25. **This checkout has no real basis evidence.** Synthetic fixtures prove
    mechanics only. The clean-checkout failure is the correct fail-closed
    result and must not be reported as real-host validation.
26. **Global graduation is canonical-live-only (P12.13).** Do not remove the
    `COALESCE(source_key, '') = ''` filters from `paper_progress()` or treat
    its output as a pooled research report. Use the source-filtered scorecard
    for research. Legacy NULL keys remain canonical by deliberate contract.

---

## Next recommended action

1. **Keep the passed-through triage:** `docs/CHATGPT_6IDEA_TRIAGE_2026-08-18.md` (6 ideas -> Take/Park/Reject) remains the durable decision for LMRing/OpenDataLoader/AirLLM/harness — `P18.4` already satisfied it as `P12.19` after `P19`.
2. **`P18.4 is done — verify it:*** `web/static/manifest.json` (installable), `web/static/sw.js` (shell-only, never `/api/*`/SSE), `/offline.html` precached, offline banner + mutation guard + compact `640px` in `web/app.py`. Install on Chrome/Edge desktop + Android, toggle Offline in DevTools → reload → `Mutations disabled` banner + offline page.
3. **Code `P19 Ubuntu Hub package` next** — `ROADMAP.md:5` + `TODO.md`: one `sky` service user, `/opt/sky` + `/etc/sky` + `/var/lib/sky`, hardened `gunicorn/scan/paper` units, `sky setup/status/logs/backup/restore/doctor`, TLS proxy. This is where `*02 #1/#2` (backup/init) land. `P18.4` delivery shell is done.
4. **Operate the loop while P19 is built:** `python main.py daily` (loop-health), `python main.py paper --watch`, weekly `python main.py scorecard --conditioned --source store` net + `python main.py validate --source store --tf 15m` on the real-data host. Grow canonical `binance/spot/BTCUSDT 15m` paper `n` toward `100-200` decided net — that is the only graduation evidence.
5. **On the real-data host (parallel, not blocking P19):** rerun `learn` so existing canonical rows pick up source keys (live profile unchanged, demo/synthetic never substituted); acquire/version-pin Dukascopy XAU m1 `bid` or `ask` per `docs/DUKASCOPY_XAU_ADAPTER.md`; run locked `train/val/sealed-OOS/recent` under expected XAU seal key; archive `python main.py xau-evidence --tf 15m --json` per `docs/XAU_PROMOTION_EVIDENCE.md` (overlap/provenance/fingerprint/windows/envelope/reseal). Do not create/reseal from the audit.
6. **Do not** install `LMRing / OpenDataLoader / AirLLM / torch / 70B models`, pool `binance/spot` with `dukascopy/spot/XAUUSD`, loosen `+0.50R/55%/PF1.5 + compliance100%`, add new strategy families, or build live-order code. `*04/*06/*01` are external labs after `P19` + `graduation==READY`; `*03 L2/L4/L5` is `P12.19` after `P19`.
7. Repo admin verifies/completes `TODO-8` (`docs/HUMAN_ACTIONS.md`); `TODO-7` already done.

**Suggested next-session prompt:**

> Continue SKY from SESSION_STATE.md. Fetch and diff origin/main first and
> confirm P12.15 / PR #38 is merged. P12.1–P12.15 are shipped; do not rewrite
> the locked protocol, source-key algebra, canonical-only graduation and live
> risk filters, calendars, gold costs, or `data/gold_basis.py`. Preserve
> separate `binance/spot/PAXGUSDT` and `dukascopy/spot/XAUUSD` histories and
> exact-time-only alignment. On the real-data host, rerun `learn`, run the
> documented P12.12 validation/evidence procedure, and archive
> `xau-evidence --json`; never substitute synthetic fixtures, pool calibration,
> or create/reseal evidence from the audit command. Treat a passing dossier as
> eligible for human review only. Continue canonical paper proof, keep XAU
> non-tradeable, and keep micro-live blocked until the unchanged graduation bar
> says READY and the user separately gives explicit approval. Do not adopt
> Freqtrade or Backtrader, loosen any gate, or build order placement.

---

## Last successful test command

```bash
cd /home/user/SKY
DEMO_MODE=1 python -m pytest tests/test_windows_companion.py tests/test_hub.py tests/test_handoff_memory.py -q
# 1125 passed, 1 skipped  (v2.38.0 P22.1 full suite; +10 release/privacy regressions)

cd /home/user/SKY
DEMO_MODE=1 .venv/bin/python -m pytest tests/ -q
# prior baseline 1063 passed, 1 skipped  (v2.34.0 P18.4) + P20 + P21 tests

# PWA installability + safety
DEMO_MODE=1 .venv/bin/python -m pytest tests/test_pwa.py tests/test_dashboard_js.py -q
# 19 passed (10 PWA + 9 dashboard JS)

# P12.14 discipline harness (exits non-zero if any case fails open)
.venv/bin/python ops/probes/p12_14_discipline_probe.py

# P12.15 live-book harness (exits non-zero if any control pools research)
.venv/bin/python ops/probes/p12_15_livebook_probe.py

# P12.15 execution-metric follow-up
DEMO_MODE=1 .venv/bin/python -m pytest tests/test_livebook_isolation.py tests/test_journal_metrics.py -q
```

PAXG-vs-XAU evidence (P12.12):
```bash
DEMO_MODE=1 .venv/bin/python -m pytest tests/test_gold_basis.py tests/test_validation.py tests/test_handoff_memory.py -q
# 54 passed
python main.py xau-evidence --tf 15m --json
# RESEARCH_ONLY; 0 rows; seal MISSING; approval OPEN; exit 1
```

Source provenance (P12.11):
```bash
DEMO_MODE=1 .venv/bin/python -m pytest tests/test_provenance.py -q
# 23 passed
```

XAU cost model (P12.10):
```bash
DEMO_MODE=1 .venv/bin/python -m pytest tests/test_costs.py -q
# 22 passed  (12 original P12.6 + 10 new P12.10 gold tests)
```

Wheel gate:
```bash
DEMO_MODE=1 .venv/bin/python ci/wheel_gate.py
# builds cryptobrain-2.23.4-py3-none-any.whl ; no duplicate entries
```

Market calendar (P12.9):
```bash
python main.py calendar                                   # is spot gold open?
python main.py calendar --at 1783684800000 --json         # a specific instant
python main.py calendar --symbol XAUUSD --tf 1h --series  # stored-series health
python main.py calendar --exchange binance --market perp --symbol BTCUSDT
```

Monte Carlo risk-of-ruin table (P12.7):
```bash
python main.py monte                          # boxed human table
python main.py monte --json --samples 5000    # machine-readable
python main.py monte --risk-pcts 0.5,1,2      # custom sweep
curl -s localhost:8080/api/monte              # HTTP
curl -s localhost:8080/api/risk               # includes monte block
```

Calibration with the P12.5 strategy score:
```bash
python main.py learn                          # profile + strategy score per key
python main.py learn --json                   # full profile incl. strategy_components
curl -s localhost:8080/api/learning           # HTTP (dashboard Calibration card reads it)
```

Readiness strip:
```bash
DEMO_MODE=1 python main.py doctor --strip          # CLI text
DEMO_MODE=1 python main.py doctor --strip --json   # CLI JSON
curl -s localhost:8080/api/readiness               # HTTP
# MCP: tools/call {"name": "readiness", "arguments": {}}
```

Scorecard with costs (P12.6) + quality (P12.4):
```bash
python main.py scorecard --source store --market spot --symbol BTCUSDT --tf 15m --bars 1000
python main.py scorecard --source store --market spot --symbol BTCUSDT --tf 15m --bars 500 --conditioned
python main.py scorecard --source db --quality        # embed the quality block (no plateau)
python main.py quality --symbol BTCUSDT --tf 15m --bars 500   # full plateau sweep (store-only)
```

## Last implementation commit

```
P18.4 PWA foundation — installable, offline-safe shell (v2.34.0) — this session arena/01a0135d-sky
07e8a50 docs: pass ChatGPT 6-idea triage to next session (P18.4 stays next)
97725e7 W2 complete: live chart streaming + drawing tools (v2.33.0) (#53) — merged
P12.15 follow-up: live execution-metric source isolation (v2.23.4) — PR #39 — merged
```

This branch `arena/01a0135d-sky` is ahead of `origin/main` at `97725e7`.
Use `git rev-parse HEAD` for the tip (now v2.34.0).

---

## Start-of-session recipe (paste this when starting a new session)

```
You are continuing development of the existing SKY project at
github.com/Azimshawon/SKY, on your Arena session branch.

First, inspect the GitHub repository before making changes:
- git fetch origin, and diff your branch against origin/main —
  parallel sessions merge while you work; reconcile before building.

Read in this order:
1. SESSION_STATE.md         (current state, current TODO, last commit)
2. docs/CHATGPT_6IDEA_TRIAGE_2026-08-18.md  (6-idea Take/Park/Reject — durable even if user forgets)
3. TODO.md                  (prioritised remaining work)
4. HANDOVER.md              (next-session start here — P18.4 PWA)
5. ARCHITECTURE.md          (module map + invariants)
6. CHANGELOG.md             (what shipped, when)
7. README.md                (user-facing overview)
8. ROADMAP_AGENT_REACH_UPGRADE.md  (the P7/P8/P9 plan + D1–D5 decisions)
9. docs/FREQTRADE_REVIEW.md        (F1–F8 — do not install a bot)
10. docs/BACKTRADER_REVIEW.md       (BT1–BT8 — do not add a second grader)

Then inspect the relevant source files and tests.

Your job is to continue from the exact state left by the previous
session, starting with the top-priority item in TODO.md.

Rules:
- Do NOT recreate or redesign completed components.
- Do NOT assume anything that is not present in the repository.
- Preserve existing architecture unless there is a demonstrated
  reason to change it.
- Before modifying code, explain briefly what you found and what
  the next implementation step is.
- Implement the next highest-priority task from TODO.md (which after this triage is P18.4 PWA — do not start LMRing/OpenDataLoader/AirLLM instead).
- Run the relevant tests after implementation.
- Fix failures before considering the task complete.
- Maintain test count at ≥ 748 pass / 1 skip.
- Update SESSION_STATE.md with completed/current/remaining/known/
  next action. Full-document reconciliation, not append-only.
- Update CHANGELOG.md.
- Commit and push.

If the task is too large for the remaining session, split it into a
safe checkpoint rather than leaving the repository in an undocumented
state.

Before ending the session, open ONE pull request from this branch to
main (Arena allows one PR per chat session). Do not merge it yourself.

Triage carry-over rule (this session `arena/01a0135d-sky`):
If the user does not mention the 6-idea review, you still have `docs/CHATGPT_6IDEA_TRIAGE_2026-08-18.md` — treat its `Take/Park/Reject` as already decided. Do NOT ask the user to re-explain *01-*06, and do NOT re-triage from scratch. Just point to the file and continue `P18.4`.
```

## End-of-session checklist (run before closing this session)

**Current build session `arena/01a0135d-sky` (2026-08-18) — ChatGPT 6-idea triage + P18.4 PWA:**

1. [x] Read all 6 ChatGPT ideas (`*01` LMRing + `*02` 10-item desk + `*03` 5-layer evidence engine + `*04` OpenDataLoader PDF + `*05` harness/CLAUDE.md + `*06` AirLLM) against `ROADMAP.md` P18-P22, `P10-P12`, `HANDOVER.md`, `TODO.md`, `config.py`, `engine/*`, `brain/*`, `data/*`.
2. [x] Write `docs/CHATGPT_6IDEA_TRIAGE_2026-08-18.md` — 6-row `Take/Park/Reject` + `§8` decision + `§9` `P18.4->P19->P11` actions + `§10` guardrails. No `requirements.txt`/`config.py`/`env` change, no threshold moved, advisory only.
3. [x] Patch `SESSION_STATE.md` + `HANDOVER.md` to durable-pass the triage (reads as #2 even if user forgets).
4. [x] Build **P18.4 PWA** — `manifest.json` + 4 icons, `sw.js` shell-only `sky-shell-v2.34.0` (never `/api/*`/SSE), `offline.html` precached, `web/app.py` banners + compact `640px` + `Service-Worker-Allowed: /` + public `/sw.js`/`/manifest.json`/`/offline*` before auth, `config`+`pyproject` `2.33.0→2.34.0`, `tests/test_pwa.py` 10 tests.
5. [x] Verify: `node --check` on served `HTML` + `tests/test_pwa.py` 10 pass + `tests/test_dashboard_js.py` 9 pass + full suite **1063 passed / 1 skipped** + `ci/wheel_gate.py` no duplicate entries.
6. [x] Reconcile durable docs: `CHANGELOG.md` 2.34.0, `TODO.md` P18.4→✅, `ROADMAP.md` P18.4→✅, `HANDOVER.md` Next=P19, `SESSION_STATE.md` Next=P19, handover `docs/HANDOVER_2026-08-18_P18_4.md`.
7. [ ] Commit + push to `origin/arena/01a0135d-sky` and open one PR to `main` (Arena allows one per session).
8. [ ] Next code is **P19 Ubuntu Hub package** — `sky setup/backup/restore`, hardened systemd, TLS.

**Previous reconciliation session `arena/01a0099b-sky` (2026-08-16):**

1. [x] Fetch `origin` and confirm PR #38 is merged; keep work on the fixed session branch.
2. [x] Review P12.1–P12.15 and find the remaining pooled business execution metric.
3. [x] Build `live_execution_stats()` and wire only `business_metrics()` to it; preserve broad journal/graduation contracts.
4. [x] Add two source-isolation/missing-journal regressions and bump v2.23.3 → v2.23.4.
5. [x] Reconcile the durable docs and run the full suite: **750 passed / 1 skipped**.
6. [x] Verify clean-checkout XAU evidence still fails closed with zero rows and no seal.
7. [ ] Real-data host: rerun `learn`, run the locked XAU validation, and archive `xau-evidence --json` without synthetic substitutions.
8. [ ] Continue canonical live paper proof and journal every decided real trade.
9. [ ] Repo admin verifies TODO-8; do not unlock micro-live or build order placement.

**Session `arena/01a008d1-sky` (2026-08-16) — review + P12.14 build:**

1. [x] Review P12.13's remaining surface; find and reproduce the discipline gap.
2. [x] Write the contract (`docs/HANDOVER_2026-08-16_P12_14.md`) + probe harness.
3. [x] Build `graduation_discipline()` / `SignalDB.discipline_rows()`.
4. [x] Wire all four graduation surfaces to the one computation.
5. [x] Add 10 regressions; full suite **736 passed, 1 skipped**.
6. [x] compileall, `pip check`, v2.23.2 wheel gate.
7. [x] Bump version 2.23.1 → 2.23.2; reconcile CHANGELOG/ARCHITECTURE/TODO/SESSION_STATE.
8. [x] Push `origin/arena/01a008d1-sky`; open **PR #37**; both CI jobs green; not merged.

**Previous session `arena/01a008b9-sky` (P12.13):**

1. [x] Fix the reviewed safety gap — canonical-only global graduation.
2. [x] Rebuild `.venv`; run focused tests — **41 passed**.
3. [x] Run full suite — **726 passed, 1 skipped**.
4. [x] Run compileall, `pip check`, and v2.23.1 wheel gate.
5. [x] Reconcile TODO/architecture/roadmap/source docs and stale TODO-7 state.
6. [x] Keep thresholds, XAU status, and no-order-placement contract unchanged.
7. [x] Commit and push only to `origin/arena/01a008b9-sky`.
8. [x] Open one PR from `arena/01a008b9-sky` to `main`; do not merge it.
