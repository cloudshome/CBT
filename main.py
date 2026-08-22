#!/usr/bin/env python3
"""CryptoBrain — AI trading-brain signal engine.

Usage:
  python main.py scan --symbol BTCUSDT --tf 15m --json
  python main.py scan --symbols BTCUSDT,ETHUSDT,XAUUSD
  python main.py intelligence --symbol XAUUSD --tf 15m      # JSON-only desk report
  python main.py watch --symbol ETH --interval 120          # continuous loop
  python main.py web                                         # dashboard
  python main.py paper --watch                               # live-market paper monitor
  python main.py sources                                     # CryptoDada + Discord + news
  python main.py brief                                       # daily desk briefing (alias)
  python main.py agent morning                               # desk morning briefing
  python main.py agent ask "is the risk gate open?"          # natural-language question
  python main.py agent ask "am i ready for micro?"           # graduation gate
  python main.py agent all                                   # health + briefing + graduation
  python main.py health                                      # system health (+ KuCoin/OKX/Bybit cross-check)
  python main.py desk                                        # one-call desk advisory (gate + P&L + graduation + advice)
  python main.py daily                                       # 10-minute daily ritual (readiness + loop health + gate + journal)
  python main.py preflight                                   # strict live-paper operations gate
  python main.py simulator                                   # grind 100/20 sample proof
  python main.py backfill --symbol BTCUSDT --market perp     # P10.2: paginated Binance history → Parquet store
  python main.py derivatives collect --symbol BTCUSDT   # P10.4: funding/OI/mark/index/basis → Parquet store
  python main.py cross collect --symbol BTCUSDT         # P10.7: premium/discount + funding spread
  python main.py store --market perp                         # inspect the stored candle history
  python main.py validate lookahead                          # P12.2 future-shift guard
  python main.py xau-evidence --tf 15m                       # P12.12 PAXG/XAU basis dossier
  python main.py mcp                                         # MCP server for Claude/Cursor
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import importlib.util
import subprocess
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _ensure_runtime():
    """Make ``python main.py`` a genuine one-command launcher.

    Normal installations already have the dependencies and this is a cheap
    import check. On a fresh checkout, install the pinned project requirements
    once, then continue into the same dashboard process. Set
    ``SKY_NO_AUTO_INSTALL=1`` for locked-down/CI environments.
    """
    required = {"flask": "flask", "dotenv": "python-dotenv", "numpy": "numpy",
                "pandas": "pandas", "requests": "requests"}
    missing = [package for module, package in required.items()
               if importlib.util.find_spec(module) is None]
    if not missing or os.getenv("SKY_NO_AUTO_INSTALL") == "1":
        if missing:
            raise RuntimeError("Missing dependencies: " + ", ".join(missing)
                               + ". Run: python -m pip install -r requirements.txt")
        return
    print("SKY: first run detected — preparing an isolated environment…", flush=True)
    # Ubuntu/Debian enforce PEP 668 and reject system-wide pip installs.
    # Create a project-local virtualenv and transparently re-launch the same
    # command inside it, so the user still only runs `python3 main.py`.
    venv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv")
    if sys.prefix == getattr(sys, "base_prefix", sys.prefix) and os.getenv("SKY_IN_VENV") != "1":
        try:
            subprocess.check_call([sys.executable, "-m", "venv", venv_dir])
            vpy = os.path.join(venv_dir, "bin", "python")
            env = os.environ.copy()
            env["SKY_IN_VENV"] = "1"
            os.execve(vpy, [vpy, os.path.abspath(__file__), *sys.argv[1:]], env)
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            raise RuntimeError(
                "Could not create .venv. Run: sudo apt install -y python3-venv "
                "then retry python3 main.py") from exc
    print("SKY: installing dashboard dependencies in .venv…", flush=True)
    # Minimal Ubuntu images often ship python3 without pip. Try the standard
    # library bootstrap first; if the distro disables it, report the exact
    # one-time package command instead of exposing a cryptic pip traceback.
    if importlib.util.find_spec("pip") is None:
        try:
            subprocess.check_call([sys.executable, "-m", "ensurepip", "--upgrade"])
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError(
                "pip is not installed. Run: sudo apt update && "
                "sudo apt install -y python3-pip python3-venv, then rerun: "
                "python3 main.py")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])


try:
    _ensure_runtime()
except (RuntimeError, subprocess.CalledProcessError) as exc:
    print(f"SKY cannot start: {exc}", file=sys.stderr)
    sys.exit(1)

from config import (SYMBOL, SYMBOLS, TIMEFRAME, BARS, MIN_CONFIDENCE,
                    DASHBOARD_HOST, DASHBOARD_PORT, PAPER_POLL_SECONDS, VERSION,
                    BACKTEST_MIN_BARS, BACKTEST_STEP, ROOT)

from data.sample_client import maybe_client
from output.notifiers import notify_all

# Refactor step 2a (ROADMAP §19): the shared CLI helpers and the run_scan
# pipeline live in cli/common.py.  Re-exported here so `from main import
# run_scan` (ai/mcp_server.py) and every cmd_* body keep working unchanged.
from cli.common import (  # noqa: F401 — re-exported for back-compat
    _client, _load_calibration, _source_key_arg, _sym, _symbols, run_scan,
)
# Refactor step 2b: the P12/P13 validation commands live in cli/validation.py.
# Re-exported so the argparse wiring (func=cmd_*) keeps working unchanged.
from cli.validation import (  # noqa: F401 — re-exported for back-compat
    cmd_backtest, cmd_edge_validate, cmd_monte, cmd_validate, cmd_xau_evidence,
)
from cli.daily import (  # noqa: F401 — re-exported for back-compat
    cmd_scan, _print_human, cmd_watch, cmd_sources, cmd_signal, cmd_learn, cmd_coach, cmd_glossary, _print_context, cmd_intelligence, cmd_card, cmd_analyze, cmd_state, cmd_stats, cmd_web, cmd_sourcetrust, cmd_risk, cmd_tradestate, cmd_journal, cmd_ask, cmd_postreview, cmd_agent, cmd_brief, cmd_health, cmd_desk, cmd_daily, cmd_weekly, cmd_practice,
)
from cli.paper import (  # noqa: F401 — re-exported for back-compat
    _print_review_row, cmd_review, _decide, cmd_approve, cmd_reject, cmd_execute, cmd_close, _print_paper_run, cmd_paper, cmd_simulator,
)
from cli.analytics import (  # noqa: F401 — re-exported for back-compat
    cmd_scorecard, cmd_calendar, cmd_quality,
)
from cli.market import (  # noqa: F401 — re-exported for back-compat
    cmd_backfill, cmd_store, cmd_doctor, cmd_channels, cmd_derivatives, cmd_cross, cmd_correlation,
)
from cli.system import (  # noqa: F401 — re-exported for back-compat
    cmd_preflight, cmd_mcp, cmd_sky_agent, cmd_release, cmd_companion, cmd_hub, cmd_hidden, cmd_skill,
)



def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CryptoBrain — AI trading-brain signal engine")
    sub = ap.add_subparsers(dest="cmd")

    p_scan = sub.add_parser("scan", help="one-shot signal scan")
    p_scan.add_argument("--symbol", default=SYMBOL, help="single asset (aliases: BTC, ETH, XAU/GOLD)")
    p_scan.add_argument("--symbols", default=None,
                        help=f"comma-separated watchlist (e.g. {','.join(SYMBOLS)}); overrides --symbol")
    p_scan.add_argument("--tf", default=TIMEFRAME)
    p_scan.add_argument("--bars", type=int, default=BARS)
    p_scan.add_argument("--json", action="store_true", help="raw JSON output")
    p_scan.add_argument("--llm", action="store_true", help="attach LLM narrative if configured")
    p_scan.add_argument("--no-save", action="store_true", help="do not write the scan to the signal database")
    p_scan.add_argument("--auto-approve", action="store_true",
                        help="skip the human approval gate (unattended mode)")
    p_scan.set_defaults(func=cmd_scan)

    p_watch = sub.add_parser("watch", help="continuous monitor loop")
    p_watch.add_argument("--symbol", default=SYMBOL, help="asset to watch (aliases: BTC, ETH, XAU/GOLD)")
    p_watch.add_argument("--tf", default=TIMEFRAME)
    p_watch.add_argument("--bars", type=int, default=BARS)
    p_watch.add_argument("--interval", type=int, default=120)
    p_watch.add_argument("--notify", action="store_true", help="push signals to Telegram/Discord")
    p_watch.add_argument("--no-save", action="store_true", help="do not write scans to the signal database")
    p_watch.add_argument("--auto-approve", action="store_true",
                        help="approve signals automatically (unattended mode)")
    p_watch.set_defaults(func=cmd_watch)

    p_paper = sub.add_parser("paper", help="monitor approved paper trades; never sends exchange orders")
    p_paper.add_argument("--symbol", default=None, help="optional symbol filter, e.g. BTCUSDT, ETH, XAUUSD")
    p_paper.add_argument("--watch", action="store_true", help="keep monitoring until Ctrl+C")
    p_paper.add_argument("--interval", type=int, default=PAPER_POLL_SECONDS,
                         help="seconds between checks in --watch mode")
    p_paper.add_argument("--no-enroll", action="store_true",
                         help="only check existing paper trades; do not enroll new approvals")
    p_paper.add_argument("--json", action="store_true", help="machine-readable run summary")
    p_paper.add_argument(
        "--allow-demo", action="store_true",
        help="allow DEMO_MODE=1 for a rehearsal; never counts as live paper evidence",
    )
    p_paper.set_defaults(func=cmd_paper)

    p_src = sub.add_parser("sources", help="pull CryptoDada + Discord + news")
    p_src.set_defaults(func=cmd_sources)

    p_bt = sub.add_parser("backtest", help="walk-forward grade of engine plans")
    p_bt.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_bt.add_argument("--tf", default=TIMEFRAME)
    p_bt.add_argument("--bars", type=int, default=BARS)
    p_bt.add_argument("--horizons", default="1,4,24", help="comma-separated hours, e.g. 1,4,24")
    p_bt.add_argument("--min-conf", type=int, default=MIN_CONFIDENCE)
    p_bt.add_argument("--step", type=int, default=BACKTEST_STEP,
                      help="walk-forward bar step (1 = every bar)")
    p_bt.add_argument("--save", action="store_true", help="store graded outcomes in the signal database")
    p_bt.add_argument("--source", default="auto", choices=("auto", "store"),
                      help="auto = live (or demo) client; store = the P10 Parquet "
                           "series (offline, P12.3.2 real data)")
    p_bt.add_argument("--exchange", default="binance",
                      help="store venue (binance|bybit|dukascopy)")
    p_bt.add_argument("--market", default="spot", choices=("spot", "perp"),
                      help="store series market label (used with --source store)")
    p_bt.set_defaults(func=cmd_backtest)

    p_val = sub.add_parser(
        "validate",
        help="P12 validation: locked protocol or `lookahead` source guard")
    p_val.add_argument("mode", nargs="?", choices=("lookahead",), default=None,
                       help="lookahead = P12.2 negative-shift guard; omit for P12.1 protocol")
    p_val.add_argument("--path", dest="lookahead_paths", action="append", default=None,
                       help="lookahead file/directory to scan (repeatable; default: engine, brain, data)")
    p_val.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_val.add_argument("--tf", default=TIMEFRAME)
    p_val.add_argument("--exchange", default="binance", help="stored series venue (binance|bybit)")
    p_val.add_argument("--market", default="perp", help="spot or perp series")
    p_val.add_argument("--bars", type=int, default=2000,
                       help="most-recent bars from the store to validate over")
    p_val.add_argument("--step", type=int, default=3,
                       help="bar step for the walk-forward scan (1 = every bar)")
    p_val.add_argument("--min-bars", type=int, default=BACKTEST_MIN_BARS,
                       help="engine warm-up bars (belong to no window)")
    p_val.add_argument("--min-conf", type=int, default=MIN_CONFIDENCE)
    p_val.add_argument("--min-decided", type=int, default=30,
                       help="minimum decided trades per window for a bar check")
    p_val.add_argument("--horizons", default="1,4,24",
                       help="comma-separated hours; verdicts use the first (primary)")
    p_val.add_argument("--train", type=float, default=0.60,
                       help="train window fraction (earliest)")
    p_val.add_argument("--val", type=float, default=0.15,
                       help="validation window fraction")
    p_val.add_argument("--oos", type=float, default=0.15,
                       help="sealed OOS window fraction")
    p_val.add_argument("--recent", type=float, default=0.10,
                       help="sealed recent window fraction (newest)")
    p_val.add_argument("--json", action="store_true",
                       help="machine-readable result")
    p_val.add_argument("--store-root", default=None,
                       help="store root override (default data/store; mirrors backfill --root)")
    p_val.add_argument("--seal-dir", default=None,
                       help="sealed-OOS envelope directory override")
    p_val.add_argument("--reseal", action="store_true",
                       help="re-open the sealed OOS envelope (recorded in seal history)")
    p_val.set_defaults(func=cmd_validate)

    p_edge = sub.add_parser(
        "edge-validate",
        help="P13: honest regime-aware edge verdict on the sealed OOS + recent "
             "windows (EDGE_CONFIRMED / NO EDGE / INSUFFICIENT_DATA)")
    p_edge.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_edge.add_argument("--tf", default=TIMEFRAME)
    p_edge.add_argument("--bars", type=int, default=2000,
                        help="most-recent bars to validate over")
    p_edge.add_argument("--horizons", default="1", help="comma-separated hours; verdict uses the primary")
    p_edge.add_argument("--step", type=int, default=3,
                        help="bar step for the walk-forward scan (1 = every bar)")
    p_edge.add_argument("--min-bars", type=int, default=BACKTEST_MIN_BARS,
                        help="engine warm-up bars (belong to no window)")
    p_edge.add_argument("--min-conf", type=int, default=MIN_CONFIDENCE)
    p_edge.add_argument("--min-decided", type=int, default=30,
                        help="minimum decided trades on decisive windows for a claim")
    p_edge.add_argument("--regime-min-decided", type=int, default=10,
                        help="decided trades a regime needs to count as well-sampled")
    p_edge.add_argument("--positive-regime-frac", type=float, default=0.5,
                        help="fraction of well-sampled regimes that must be net-positive")
    p_edge.add_argument("--decisive-windows", default="oos,recent",
                        help="comma-separated windows that count as untouched evidence")
    p_edge.add_argument("--execution", default="none", choices=("none", "slip", "impact"),
                        help="fill model for the walk (none = raw close fill; "
                             "slip/impact = realistic slippage)")
    p_edge.add_argument("--source", default="auto", choices=("auto", "store"),
                        help="auto = live (or demo) client; store = the P10 Parquet series")
    p_edge.add_argument("--exchange", default="binance", help="store venue (binance|bybit|dukascopy)")
    p_edge.add_argument("--market", default="perp", choices=("spot", "perp"),
                        help="store series market label (used with --source store)")
    p_edge.add_argument("--train", type=float, default=0.60)
    p_edge.add_argument("--val", type=float, default=0.15)
    p_edge.add_argument("--oos", type=float, default=0.15)
    p_edge.add_argument("--recent", type=float, default=0.10)
    p_edge.add_argument("--monte", action="store_true",
                        help="P13.5: run Monte-Carlo resampling of the "
                             "decisive-window R series and apply a stability "
                             "floor (p5 net expectancy > 0)")
    p_edge.add_argument("--monte-samples", type=int, default=2000,
                        help="P13.5: number of MC bootstrap samples (default 2000)")
    p_edge.add_argument("--monte-risk-pct", type=float, default=1.0,
                        help="P13.5: position size %% per trade for the MC "
                             "equity simulation (default 1.0)")
    p_edge.add_argument("--monte-seed", type=int, default=None,
                        help="P13.5: RNG seed for reproducible MC output")
    p_edge.add_argument("--ladder", action="store_true",
                        help="P13.6: pair the verdict with the canonical live "
                             "paper book in one backtest -> OOS -> paper "
                             "comparison")
    p_edge.add_argument("--json", action="store_true", help="machine-readable result")
    p_edge.set_defaults(func=cmd_edge_validate)

    p_xau = sub.add_parser(
        "xau-evidence",
        help="P12.12: read-only PAXG-vs-XAU basis + sealed-OOS promotion dossier")
    p_xau.add_argument("--tf", default="15m",
                       help="timeframe stored for both series (default 15m)")
    p_xau.add_argument("--bars", type=int, default=12000,
                       help="most-recent rows read independently from each series")
    p_xau.add_argument("--min-overlap", type=int, default=100,
                       help="minimum exact-time matched bars for a measured basis")
    p_xau.add_argument("--store-root", default=str(ROOT / "data" / "store"),
                       help="CandleStore root containing separately keyed series")
    p_xau.add_argument("--seal-dir", default=str(ROOT / "data" / "store" / "validation"),
                       help="directory holding the Dukascopy XAU validation seal")
    p_xau.add_argument("--json", action="store_true",
                       help="machine-readable research dossier")
    p_xau.set_defaults(func=cmd_xau_evidence)

    p_score = sub.add_parser(
        "scorecard",
        help="P12.3 strategy scorecard — one boxed block (side/regime/session, "
             "Sharpe/Sortino/Calmar, holding time)")
    p_score.add_argument("--source", default="db",
                         choices=("db", "backtest", "paper", "store"),
                         help="db = stored backtest+paper outcomes (default); "
                              "backtest/paper = one book; store = fresh "
                              "walk-forward grade of the stored series")
    p_score.add_argument("--symbol", default=None,
                         help="asset filter / store symbol (BTC, ETH, XAU/GOLD)")
    p_score.add_argument("--tf", default=TIMEFRAME, help="store timeframe")
    p_score.add_argument("--exchange", default="binance",
                         help="stored series venue (binance|bybit)")
    p_score.add_argument("--market", default="perp", help="spot or perp series")
    p_score.add_argument("--bars", type=int, default=1000,
                         help="--source store: most-recent bars to grade")
    p_score.add_argument("--horizons", default="4",
                         help="--source store: comma-separated hours; the "
                              "first is scored")
    p_score.add_argument("--min-bars", type=int, default=BACKTEST_MIN_BARS,
                         help="--source store: engine warm-up bars")
    p_score.add_argument("--step", type=int, default=3,
                         help="walk-forward bar step used to grade backtest "
                              "rows (overlap correction, P12.3.3)")
    p_score.add_argument("--min-conf", type=int, default=MIN_CONFIDENCE)
    p_score.add_argument("--min-decided", type=int, default=30,
                         help="minimum decided trades before a verdict is given")
    p_score.add_argument("--exclude-sim", action="store_true",
                         help="drop simulator walk-forward samples (real book only)")
    p_score.add_argument("--since", default=None,
                         help="db sources: score rows at/after this signal bar "
                              "(epoch ms or YYYY-MM-DD) — separates data eras")
    p_score.add_argument("--until", default=None,
                         help="db backtest rows: score rows at/before this "
                              "signal bar (epoch ms or YYYY-MM-DD)")
    p_score.add_argument("--no-costs", action="store_true",
                         help="disable cost modeling (score gross outcomes only)")
    p_score.add_argument("--maker", action="store_true",
                         help="model maker fees instead of default taker fees")
    p_score.add_argument("--conditioned", action="store_true",
                         help="include conditioned splits by funding and CVD order flow")
    p_score.add_argument("--quality", action="store_true",
                         help="P12.4: embed the Backtest Quality Score 0–100 "
                              "for the same book")
    p_score.add_argument("--source-key", default=None,
                         help="P12.11: score ONE price series only — "
                              "'live' (canonical Binance spot), "
                              "'exchange:market[:bid|ask]' e.g. "
                              "dukascopy:spot:bid, or 'all' (default) to pool "
                              "every source and report the mix")
    p_score.add_argument("--json", action="store_true",
                         help="machine-readable result")
    p_score.set_defaults(func=cmd_scorecard)

    p_quality = sub.add_parser(
        "quality",
        help="P12.4 Backtest Quality Score 0–100 with the parameter-plateau "
             "sweep (store-only): re-grades min_confidence ±5 and caps an "
             "isolated-peak edge at 50")
    p_quality.add_argument("--symbol", default=None,
                           help="asset symbol (BTC, ETH, XAU/GOLD)")
    p_quality.add_argument("--tf", default=TIMEFRAME, help="store timeframe")
    p_quality.add_argument("--exchange", default="binance",
                           help="stored series venue (binance|bybit)")
    p_quality.add_argument("--market", default="perp", help="spot or perp series")
    p_quality.add_argument("--bars", type=int, default=1000,
                           help="most-recent bars to grade")
    p_quality.add_argument("--horizons", default="4",
                           help="comma-separated hours; the first is scored")
    p_quality.add_argument("--min-bars", type=int, default=BACKTEST_MIN_BARS,
                           help="engine warm-up bars")
    p_quality.add_argument("--step", type=int, default=3,
                           help="walk-forward bar step (overlap correction, P12.3.3)")
    p_quality.add_argument("--min-conf", type=int, default=MIN_CONFIDENCE,
                           help="base strategy parameter; swept at ±5")
    p_quality.add_argument("--min-decided", type=int, default=30,
                           help="minimum decided trades before a verdict is given")
    p_quality.add_argument("--no-costs", action="store_true",
                           help="disable cost modeling (score gross outcomes only)")
    p_quality.add_argument("--maker", action="store_true",
                           help="model maker fees instead of default taker fees")
    p_quality.add_argument("--json", action="store_true",
                           help="machine-readable result")
    p_quality.set_defaults(func=cmd_quality)

    p_cal = sub.add_parser(
        "calendar",
        help="P12.9: venue trading calendar — is the market open, and how "
             "much of a stored series' span was scheduled closure?")
    p_cal.add_argument("--symbol", default=None,
                       help="asset symbol (default XAUUSD)")
    p_cal.add_argument("--tf", default="1m", help="store timeframe")
    p_cal.add_argument("--exchange", default="dukascopy",
                       help="stored series venue (binance|bybit|dukascopy)")
    p_cal.add_argument("--market", default="spot", help="spot or perp series")
    p_cal.add_argument("--calendar", default=None,
                       help="force a calendar by name (crypto-24x7|xau-otc)")
    p_cal.add_argument("--at", type=int, default=None,
                       help="UTC epoch ms to evaluate (default: now)")
    p_cal.add_argument("--series", action="store_true",
                       help="also read the stored series and report its "
                            "calendar-aware health")
    p_cal.add_argument("--root", default=None, help="store root override")
    p_cal.add_argument("--json", action="store_true",
                       help="machine-readable result")
    p_cal.set_defaults(func=cmd_calendar)

    p_stats = sub.add_parser("stats", help="what the engine has learned (DB + backtests)")
    p_stats.add_argument("--symbol", default=None, help="optional asset filter (BTC, ETH, XAU/GOLD)")
    p_stats.set_defaults(func=cmd_stats)

    p_rev = sub.add_parser("review", help="list signals awaiting human approval")
    p_rev.add_argument("--symbol", default=None, help="optional asset filter (BTC, ETH, XAU/GOLD)")
    p_rev.set_defaults(func=cmd_review)

    p_app = sub.add_parser("approve", help="approve a pending signal (risk gate enforced)")
    p_app.add_argument("scan_id", type=int)
    p_app.add_argument("--note", default="")
    p_app.add_argument("--force", action="store_true",
                       help="override a closed risk gate consciously")
    p_app.add_argument("--acknowledge-journal", action="store_true",
                       help="approve even though decided real trades are "
                            "unjournaled (W3.3; audited; journal them after)")
    p_app.set_defaults(func=cmd_approve)

    p_rej = sub.add_parser("reject", help="reject a pending signal")
    p_rej.add_argument("scan_id", type=int)
    p_rej.add_argument("--note", default="")
    p_rej.set_defaults(func=cmd_reject)

    p_exec = sub.add_parser("execute", help="mark an approved signal as executed")
    p_exec.add_argument("scan_id", type=int)
    p_exec.add_argument("--note", default="")
    p_exec.set_defaults(func=cmd_execute)

    p_close = sub.add_parser("close", help="close an executed signal (outcome recorded)")
    p_close.add_argument("scan_id", type=int)
    p_close.add_argument("--note", default="")
    p_close.set_defaults(func=cmd_close)

    p_sig = sub.add_parser("signal", help="show a signal's full detail + lifecycle")
    p_sig.add_argument("scan_id", type=int)
    p_sig.set_defaults(func=cmd_signal)

    p_learn = sub.add_parser("learn", help="recompute the self-improvement calibration profile")
    p_learn.add_argument("--json", action="store_true")
    p_learn.set_defaults(func=cmd_learn)

    p_coach = sub.add_parser("coach", help="teaching mode: explain + mentor + personal feedback")
    p_coach.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_coach.add_argument("--tf", default=TIMEFRAME)
    p_coach.add_argument("--bars", type=int, default=BARS)
    p_coach.add_argument("--term", default=None, help="explain a glossary term (e.g. FVG)")
    p_coach.set_defaults(func=cmd_coach)

    p_gl = sub.add_parser("glossary", help="list trading terms used by the engine")
    p_gl.add_argument("term", nargs="?", default=None)
    p_gl.set_defaults(func=cmd_glossary)

    p_intel = sub.add_parser("intelligence", help="professional AI trading desk report (JSON or card)")
    p_intel.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_intel.add_argument("--tf", default=TIMEFRAME)
    p_intel.add_argument("--bars", type=int, default=BARS)
    p_intel.add_argument("--card", action="store_true", help="render institutional terminal signal card")
    p_intel.set_defaults(func=cmd_intelligence)

    p_card = sub.add_parser("card", help="render Institutional AI Signal Card v2.0")
    p_card.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_card.add_argument("--tf", default=TIMEFRAME)
    p_card.add_argument("--bars", type=int, default=BARS)
    p_card.add_argument("--json", action="store_true", help="output card as raw JSON")
    p_card.set_defaults(func=cmd_card)

    p_an = sub.add_parser("analyze", help="full human-trader analysis (MTF + context + styles + memory)")
    p_an.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_an.add_argument("--tf", default=TIMEFRAME)
    p_an.add_argument("--bars", type=int, default=BARS)
    p_an.add_argument("--json", action="store_true")
    p_an.set_defaults(func=cmd_analyze)

    p_st = sub.add_parser("state", help="show the AI's remembered market state + event log")
    p_st.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_st.add_argument("--tf", default=TIMEFRAME)
    p_st.set_defaults(func=cmd_state)

    p_risk = sub.add_parser("risk", help="risk & discipline gate status (daily/weekly/drawdown/progression)")
    p_risk.set_defaults(func=cmd_risk)

    p_monte = sub.add_parser("monte", help="Monte Carlo risk-of-ruin table (expected DD / ruin prob / streak / TTR)")
    p_monte.add_argument("--risk-pcts", default="0.25,0.5,1.0,1.5,2.0",
                         help="comma-separated risk percentages per trade to sweep")
    p_monte.add_argument("--ruin-threshold", type=float, default=50.0,
                         help="drawdown %% that counts as ruin (default 50)")
    p_monte.add_argument("--samples", type=int, default=2000,
                         help="Monte Carlo samples (default 2000)")
    p_monte.add_argument("--seed", type=int, default=None,
                         help="RNG seed for reproducible output")
    p_monte.add_argument("--json", action="store_true", help="raw JSON output")
    p_monte.set_defaults(func=cmd_monte)

    p_st2 = sub.add_parser("sourcetrust", help="record a source's information tier (1-5) + trust (0-1)")
    p_st2.add_argument("source")
    p_st2.add_argument("tier", type=int, choices=(1, 2, 3, 4, 5))
    p_st2.add_argument("trust", type=float)
    p_st2.add_argument("--note", default="")
    p_st2.set_defaults(func=cmd_sourcetrust)

    p_ts = sub.add_parser("tradestate", help="set/clear behavioral no-trade flags (angry/tired/revenge/chasing)")
    p_ts.add_argument("--angry", action="store_true", default=None)
    p_ts.add_argument("--tired", action="store_true", default=None)
    p_ts.add_argument("--revenge", action="store_true", default=None)
    p_ts.add_argument("--chasing", action="store_true", default=None)
    p_ts.add_argument("--clear", action="store_true", help="clear all flags")
    p_ts.add_argument("--note", default="")
    p_ts.set_defaults(func=cmd_tradestate)

    p_j = sub.add_parser("journal", help="professional trading journal (post-trade fields + execution quality)")
    p_j.add_argument("scan_id", nargs="?", type=int, default=None)
    p_j.add_argument("--followed-rules", type=int, choices=(0, 1), default=None,
                     help="1 = followed the system, 0 = broke the rules (the headline field)")
    p_j.add_argument("--emotion", default="", help="calm/anxious/euphoric/fearful/frustrated/greedy/...")
    p_j.add_argument("--mistake", default="")
    p_j.add_argument("--screenshot", default="", help="path to chart screenshot")
    p_j.add_argument("--would-change", default="")
    p_j.add_argument("--notes", default="")
    p_j.set_defaults(func=cmd_journal)

    p_web = sub.add_parser("web", help="run the web dashboard")
    p_web.add_argument("--host", default=None)
    p_web.add_argument("--port", type=int, default=None)
    p_web.set_defaults(func=cmd_web)

    p_ask = sub.add_parser("ask", help="grounded RAG question over the trading library (with citations)")
    p_ask.add_argument("question")
    p_ask.add_argument("--top-k", type=int, default=3)
    p_ask.add_argument("--llm", action="store_true",
                       help="narrate the grounded answer with the LLM (if configured)")
    p_ask.add_argument("--json", action="store_true")
    p_ask.set_defaults(func=cmd_ask)

    p_pr = sub.add_parser("postreview", help="post-trade review for a closed scan (R, MAE/MFE, discipline)")
    p_pr.add_argument("scan_id", type=int)
    p_pr.add_argument("--json", action="store_true")
    p_pr.set_defaults(func=cmd_postreview)

    p_agent = sub.add_parser("agent", help="desk agent: morning, health, ask, all, watchdog, paper-reviewer, weekly-review")
    p_agent.set_defaults(func=cmd_agent)
    a_sub = p_agent.add_subparsers(dest="action", required=True)
    p_morning = a_sub.add_parser("morning", help="morning briefing across the watchlist")
    p_morning.add_argument("--symbols", default=None,
                           help="comma-separated watchlist (default: BTCUSDT,ETHUSDT,XAUUSD)")
    p_morning.add_argument("--tf", default=TIMEFRAME)
    p_morning.add_argument("--bars", type=int, default=BARS)
    p_morning.add_argument("--save", action="store_true",
                           help="also persist each scan to the signal database")
    p_morning.add_argument("--json", action="store_true")
    p_health_a = a_sub.add_parser("health", help="system health report")
    p_health_a.add_argument("--json", action="store_true")
    p_ask_a = a_sub.add_parser("ask", help="ask the desk a natural-language question")
    p_ask_a.add_argument("question")
    p_ask_a.add_argument("--symbol", default=None, help="asset context (BTC, ETH, GOLD)")
    p_ask_a.add_argument("--tf", default=TIMEFRAME)
    p_ask_a.add_argument("--bars", type=int, default=BARS)
    p_ask_a.add_argument("--json", action="store_true")
    p_all_a = a_sub.add_parser("all", help="one desk run: health + briefing + graduation")
    p_all_a.add_argument("--symbols", default=None,
                         help="comma-separated watchlist (default: BTCUSDT,ETHUSDT,XAUUSD)")
    p_all_a.add_argument("--tf", default=TIMEFRAME)
    p_all_a.add_argument("--bars", type=int, default=BARS)
    p_all_a.add_argument("--save", action="store_true",
                         help="also persist each scan to the signal database")
    p_all_a.add_argument("--json", action="store_true")
    # Autonomous desk agents (brain/agents.py) — audit-logged to agent_runs
    for name, helptext in (
            ("watchdog", "paper-trade monitoring + stale-cleanup alarms"),
            ("paper-reviewer", "post-mortem aggregation over closed paper trades"),
            ("weekly-review", "metrics, rule-compliance and change detection")):
        p_auto = a_sub.add_parser(name, help=helptext)
        p_auto.add_argument("--json", action="store_true")

    p_brief = sub.add_parser("brief", help="daily desk briefing (alias for `agent morning`)")
    p_brief.add_argument("--symbols", default=None,
                         help="comma-separated watchlist (default: BTCUSDT,ETHUSDT,XAUUSD)")
    p_brief.add_argument("--tf", default=TIMEFRAME)
    p_brief.add_argument("--bars", type=int, default=BARS)
    p_brief.add_argument("--save", action="store_true",
                         help="also persist each scan to the signal database")
    p_brief.add_argument("--json", action="store_true")
    p_brief.set_defaults(func=cmd_brief)

    p_health = sub.add_parser("health", help="system health (data feeds, DB, risk gate, MCP)")
    p_health.add_argument("--json", action="store_true")
    p_health.set_defaults(func=cmd_health)

    p_desk = sub.add_parser(
        "desk",
        help="one-call desk advisory: risk gate + P&L + graduation + next agent + advice",
    )
    p_desk.add_argument("--json", action="store_true")
    p_desk.set_defaults(func=cmd_desk)

    p_daily = sub.add_parser(
        "daily",
        help="10-minute daily ritual: readiness + loop health + gate + journal prompt",
    )
    p_daily.add_argument("--json", action="store_true")
    p_daily.add_argument("--brief", action="store_true",
                         help="also run the morning briefing (scans the watchlist)")
    p_daily.add_argument("--tf", default=TIMEFRAME)
    p_daily.add_argument("--bars", type=int, default=BARS)
    p_daily.set_defaults(func=cmd_daily)

    p_loop = sub.add_parser(
        "loop-health",
        help="alias for `daily` — the one loop-health number",
    )
    p_loop.add_argument("--json", action="store_true")
    p_loop.add_argument("--brief", action="store_true",
                        help="also run the morning briefing (scans the watchlist)")
    p_loop.add_argument("--tf", default=TIMEFRAME)
    p_loop.add_argument("--bars", type=int, default=BARS)
    p_loop.set_defaults(func=cmd_daily)

    p_wk = sub.add_parser(
        "weekly",
        help="weekly trader review: this week vs all time, R distribution, "
             "violations, graduation tracker, next practice task",
    )
    p_wk.add_argument("--json", action="store_true")
    p_wk.add_argument("--days", type=int, default=7,
                      help="review window in days (default 7)")
    p_wk.add_argument("--export", default=None,
                      help="also write the full JSON review to this path")
    p_wk.set_defaults(func=cmd_weekly)

    p_pr = sub.add_parser(
        "practice",
        help="practice calibration: desk-agreement plus replay-tape outcomes, "
             "agreement rates, weakest component, one coaching takeaway",
    )
    p_pr.add_argument("--json", action="store_true")
    p_pr.add_argument("--days", type=int, default=30,
                      help="window in days (default 30)")
    p_pr.set_defaults(func=cmd_practice)

    p_preflight = sub.add_parser(
        "preflight",
        help="strict safety/readiness gate before unattended live paper trading",
    )
    p_preflight.add_argument("--json", action="store_true")
    p_preflight.add_argument(
        "--allow-demo", action="store_true",
        help="allow sample/synthetic data for a rehearsal (not live evidence)",
    )
    p_preflight.set_defaults(func=cmd_preflight)

    p_sim = sub.add_parser("simulator",
                           help="grind unique backtest + paper samples per setup (A6/B10)")
    p_sim.add_argument("--rounds", type=int, default=1, help="rounds to run (default 1)")
    p_sim.add_argument("--symbols", default=None,
                       help="comma-separated watchlist (default: BTCUSDT,ETHUSDT,XAUUSD)")
    p_sim.add_argument("--tf", default=TIMEFRAME)
    p_sim.add_argument("--bars", type=int, default=600, help="history bars per symbol")
    p_sim.add_argument("--step", type=int, default=3, help="window step (1 = every bar)")
    p_sim.add_argument("--min-conf", type=int, default=MIN_CONFIDENCE)
    p_sim.add_argument("--horizons", default="1,4,24",
                       help="comma-separated forward horizons in hours")
    p_sim.add_argument("--source", default="auto", choices=("auto", "store"),
                       help="auto = live (or demo) client; store = the P10 Parquet "
                            "series (offline, P12.3.2 real data)")
    p_sim.add_argument("--exchange", default="binance",
                       help="store venue (binance|bybit|dukascopy)")
    p_sim.add_argument("--market", default="spot", choices=("spot", "perp"),
                       help="store series market label (used with --source store)")
    p_sim.add_argument("--dry-run", action="store_true",
                       help="compute what WOULD be added without storing anything")
    p_sim.add_argument("--json", action="store_true")
    p_sim.set_defaults(func=cmd_simulator)

    p_bf = sub.add_parser(
        "backfill",
        help="P10: paginated REST candle backfill into the Parquet store "
             "(resumable, rate-limit aware, idempotent)")
    p_bf.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_bf.add_argument("--tf", default="1m")
    p_bf.add_argument("--exchange", default="binance", choices=("binance", "bybit"),
                      help="venue to backfill (P10.6: bybit pages the V5 klines endpoint)")
    p_bf.add_argument("--market", default="perp", choices=("spot", "perp"),
                      help="spot (/api/v3/klines or V5 spot) or perp (/fapi/v1/klines or V5 linear)")
    p_bf.add_argument("--start-ts", type=int, default=None,
                      help="inclusive candle OPEN (UTC epoch ms)")
    p_bf.add_argument("--end-ts", type=int, default=None,
                      help="stop at this candle OPEN (UTC epoch ms)")
    p_bf.add_argument("--since", default=None,
                      help="alternative to --start-ts: epoch ms, YYYY-MM-DD, or Nd (e.g. 90d)")
    p_bf.add_argument("--until", default=None,
                      help="alternative to --end-ts: epoch ms, YYYY-MM-DD, or Nd")
    p_bf.add_argument("--page-limit", type=int, default=1000)
    p_bf.add_argument("--sleep", type=float, default=0.2,
                      help="seconds between pages (rate-limit courtesy)")
    p_bf.add_argument("--no-sleep", action="store_true")
    p_bf.add_argument("--no-resume", action="store_true",
                      help="ignore already-stored tail; re-walk the range")
    p_bf.add_argument("--max-requests", type=int, default=5000,
                      help="safety cap on requests per run; 0 = unlimited. "
                           "An interrupted run resumes on re-run")
    p_bf.add_argument("--dry-run", action="store_true",
                      help="fetch + count only; write nothing")
    p_bf.add_argument("--repair", action="store_true",
                      help="P10.3: detect + fetch missing 1m holes")
    p_bf.add_argument("--rollup", action="store_true",
                      help="P10.3: aggregate stored 1m → 5m/15m/1h/4h/1d")
    p_bf.add_argument("--from-csv", default=None, metavar="PATH",
                      help="import local OHLCV CSV(.gz) through validation — "
                           "Binance Vision/klines or dukascopy-node format")
    p_bf.add_argument("--csv-source", default="binance",
                      choices=("binance", "dukascopy"),
                      help="CSV provenance; dukascopy stores a separate "
                           "dukascopy/spot series (never relabelled Binance)")
    p_bf.add_argument("--price-type", default="bid", choices=("bid", "ask"),
                      help="dukascopy-node candle side (default bid; ignored "
                           "for Binance CSV)")
    p_bf.add_argument("--csv-sha256", default=None, metavar="HEX",
                      help="provenance pin: refuse to import unless the "
                           "decompressed CSV matches this sha256")
    p_bf.add_argument("--root", default=None, help="CandleStore root (tests)")
    p_bf.add_argument("--json", action="store_true")
    p_bf.set_defaults(func=cmd_backfill)

    p_der = sub.add_parser(
        "derivatives",
        help="P10.4: collect/inspect derivatives time series (funding / OI / mark / index / basis)")
    der_sub = p_der.add_subparsers(dest="subcmd", required=True)
    p_der_c = der_sub.add_parser("collect", help="paginated derivatives history into the Parquet store")
    p_der_c.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH)")
    p_der_c.add_argument("--market", default="perp", choices=("perp",),
                         help="derivatives exist for perp markets only")
    p_der_c.add_argument("--since", type=int, default=None,
                         help="first record (UTC epoch ms); default: resume after the last stored one")
    p_der_c.add_argument("--until", type=int, default=None,
                         help="last record (UTC epoch ms); default: now")
    p_der_c.add_argument("--metrics", default=None,
                         help="comma-separated: funding_rate,open_interest,open_interest_value,"
                              "mark_price,index_price,basis (default: all)")
    p_der_c.add_argument("--sleep", type=float, default=0.2,
                         help="seconds between pages (rate-limit courtesy)")
    p_der_c.add_argument("--dry-run", action="store_true", help="fetch + count only")
    p_der_c.add_argument("--json", action="store_true")
    p_der_c.set_defaults(func=cmd_derivatives)
    p_der_s = der_sub.add_parser("status", help="what derivatives series are stored")
    p_der_s.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH)")
    p_der_s.add_argument("--market", default="perp", choices=("perp",))
    p_der_s.add_argument("--json", action="store_true")
    p_der_s.set_defaults(func=cmd_derivatives)

    p_cross = sub.add_parser(
        "cross",
        help="P10.7: collect/inspect cross-exchange premium/discount + funding spread")
    cross_sub = p_cross.add_subparsers(dest="subcmd", required=True)
    p_cross_c = cross_sub.add_parser(
        "collect", help="persist the probe snapshot + derive Binance-vs-Bybit series")
    p_cross_c.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH)")
    p_cross_c.add_argument("--market", default="perp", choices=("spot", "perp"),
                           help="candle-store market used for historical premium")
    p_cross_c.add_argument("--tf", default="1m",
                           help="candle timeframe used for historical premium")
    p_cross_c.add_argument("--since", type=int, default=None,
                           help="first record (UTC epoch ms)")
    p_cross_c.add_argument("--until", type=int, default=None,
                           help="last record (UTC epoch ms); default: now")
    p_cross_c.add_argument("--sleep", type=float, default=0.2,
                           help="seconds between Bybit funding pages")
    p_cross_c.add_argument("--no-snapshot", action="store_true",
                           help="skip the live/fake probe snapshot; derive only")
    p_cross_c.add_argument("--dry-run", action="store_true",
                           help="compute only; write nothing")
    p_cross_c.add_argument("--root", default=None, help="CrossExchangeStore root (tests)")
    p_cross_c.add_argument("--candle-root", default=None, help="CandleStore root override")
    p_cross_c.add_argument("--deriv-root", default=None, help="DerivativesStore root override")
    p_cross_c.add_argument("--json", action="store_true")
    p_cross_c.set_defaults(func=cmd_cross)
    p_cross_s = cross_sub.add_parser("status", help="what cross-exchange series are stored")
    p_cross_s.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH)")
    p_cross_s.add_argument("--root", default=None, help="CrossExchangeStore root (tests)")
    p_cross_s.add_argument("--json", action="store_true")
    p_cross_s.set_defaults(func=cmd_cross)

    p_st = sub.add_parser("store", help="inspect the P10 Parquet candle store (count/span/partitions)")
    p_st.add_argument("--exchange", default="binance")
    p_st.add_argument("--market", default="perp", choices=("spot", "perp"))
    p_st.add_argument("--symbol", default=SYMBOL, help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_st.add_argument("--tf", default="1m", help="timeframe")
    p_st.add_argument("--demo", action="store_true",
                      help="inspect the demo store (data/store_demo) instead of the real one")
    p_st.add_argument("--root", default=None, help="CandleStore root override")
    p_st.add_argument("--json", action="store_true")
    p_st.set_defaults(func=cmd_store)

    p_mcp = sub.add_parser("mcp", help="run the Model Context Protocol server (stdio)")
    p_mcp.set_defaults(func=cmd_mcp)

    p_corr = sub.add_parser(
        "correlation",
        help="measured BTC/ETH/GOLD correlation matrix + ETH/BTC beta (read-only)")
    p_corr.add_argument("--symbols", default=None,
                        help="comma-separated watchlist (default: BTCUSDT,ETHUSDT,XAUUSD)")
    p_corr.add_argument("--tf", default="1h")
    p_corr.add_argument("--bars", type=int, default=300)
    p_corr.add_argument("--window", type=int, default=60,
                        help="rolling window of aligned returns")
    p_corr.add_argument("--json", action="store_true")
    p_corr.set_defaults(func=cmd_correlation)

    # ── Agent-Reach-inspired surface (P7/P8, additive) ────────────────
    # `doctor` is a non-mutating readiness report: data feeds, DB, risk
    # gate, MCP, and the per-channel backend registry.  Default inspect
    # only; --json is machine-readable; --fix is reserved for future
    # opt-in prescription execution (currently a no-op).
    p_doc = sub.add_parser(
        "doctor",
        help="non-mutating readiness report (channels + immune + risk gate + data quality)")
    p_doc.add_argument("--json", action="store_true")
    p_doc.add_argument("--strip", action="store_true",
                       help="print only the combined readiness strip "
                            "(one line per pillar) instead of the full report")
    p_doc.set_defaults(func=cmd_doctor)

    # `channels` lists the per-source backend registry + active backend.
    # Read-only; never mutates anything.
    p_ch = sub.add_parser(
        "channels",
        help="per-source backend registry (cryptodada / discord / news / llm) with active backend")
    p_ch.add_argument("--json", action="store_true")
    p_ch.set_defaults(func=cmd_channels)

    # `skill` exposes SKILL.md to agents and agent runtimes.
    # Default is inspect-only: prints the SKILL to stdout.  --install /
    # --uninstall require --system (matches Agent-Reach's safety posture:
    # never write under $HOME without explicit operator consent).
    p_skill = sub.add_parser(
        "skill",
        help="print or install the agent-facing SKILL.md (default: print to stdout)")
    p_skill.add_argument("--print", action="store_true", default=True,
                         help="print the SKILL.md to stdout (default behaviour)")
    p_skill.add_argument("--install", action="store_true",
                         help="install SKILL.md into the local agent skills dir (requires --system)")
    p_skill.add_argument("--uninstall", action="store_true",
                         help="remove a previously installed SKILL.md (requires --system)")
    p_skill.add_argument("--system", action="store_true",
                         help="permit writing under $HOME; required for --install / --uninstall")
    p_skill.add_argument("--dry-run", action="store_true",
                         help="preview install/uninstall without writing")
    p_skill.add_argument("--target-dir", default=None,
                         help="override the install directory (default: ~/.claude/skills/cryptobrain)")
    p_skill.set_defaults(func=cmd_skill)

    # ── P19 Ubuntu Hub ────────────────────────────────────────────────
    p_rel = sub.add_parser(
        "release",
        help="P22.3 signing + clean-target drills (catalog / evidence check)")
    p_rel.set_defaults(func=cmd_release)
    p_rel.add_argument("release_action", nargs="?", default="drills",
                       choices=("drills", "sign-plan", "status", "check"))
    p_rel.add_argument("--drill", default="",
                       help="check: drill id from the catalog")
    p_rel.add_argument("--evidence", default="",
                       help="check: path to operator evidence JSON")
    p_rel.add_argument("--evidence-dir", default=None,
                       help="directory of <drill-id>.json files")
    p_rel.add_argument("--json", action="store_true")

    p_comp = sub.add_parser(
        "companion",
        help="P20 Windows / P21 Android companion: spec, validate-url, status (unsigned recipe)")
    p_comp.set_defaults(func=cmd_companion)
    p_comp.add_argument("companion_action", nargs="?", default="spec",
                        choices=("spec", "validate-url", "status", "lint"))
    p_comp.add_argument("--platform", choices=("windows", "android"), default="windows",
                        help="which companion contract to report (default: windows)")
    p_comp.add_argument("--hub", default="https://127.0.0.1")
    p_comp.add_argument("--state", default=None)
    p_comp.add_argument("--json", action="store_true")

    p_hub = sub.add_parser(
        "hub",
        help="Ubuntu Hub: setup, status, backup/restore, doctor, diagnostics, uninstall")
    p_hub.set_defaults(func=cmd_hub)
    p_hub.add_argument("hub_action",
                       choices=("setup", "status", "logs", "backup",
                                "restore", "doctor", "diagnostics", "uninstall",
                                "first-night", "pair"),
                       help="hub subcommand")
    p_hub.add_argument("--mode", choices=("local", "remote"), default="local",
                       help="setup: local-only or remote-behind-TLS")
    p_hub.add_argument("--owner", default="",
                       help="setup: owner hint (password still created in the UI)")
    p_hub.add_argument("--prefix", default=None,
                       help="sandbox FHS prefix (tests / dry hosts)")
    p_hub.add_argument("--archive", default=None,
                       help="restore input, or diagnostics output .tar.gz path")
    p_hub.add_argument("--overwrite", action="store_true",
                       help="setup: rewrite env; restore: replace existing data")
    p_hub.add_argument("--purge", action="store_true",
                       help="uninstall: also delete /etc/sky and /var/lib/sky")
    p_hub.add_argument("--no-store", action="store_true",
                       help="backup: skip the Parquet store")
    p_hub.add_argument("--platform", choices=("windows", "android"), default="windows",
                       help="pair: which companion client the code is for (default: windows)")
    p_hub.add_argument("--retention-days", type=int, default=14)
    p_hub.add_argument("--unit", default="sky-dashboard.service")
    p_hub.add_argument("--lines", type=int, default=80)
    p_hub.add_argument("--json", action="store_true")

    # ── hidden alpha CLI (regime + CVD + kelly + MAE/MFE + Monte Carlo) ──
    p_hidden = sub.add_parser(
        "hidden", help="hidden alpha layer: regime, CVD, kelly, MAE/MFE, Monte Carlo")
    # ── 24/7 SKY Intelligence Agent (research & monitoring, never trades) ──
    p_sa = sub.add_parser("sky-agent", help="24/7 SKY Intelligence & Research Agent (discovery doc: docs/DISCOVERY_2026-08-19_AGENT.md)")
    p_sa.set_defaults(func=cmd_sky_agent)
    p_sa.add_argument("sky_agent_action", nargs="?", default="health", choices=("health", "status", "collect", "report", "run", "hypothesize"), help="health|status|collect|report|run|hypothesize")
    p_sa.add_argument("--json", action="store_true", help="machine-readable JSON")
    p_sa.add_argument("--demo", action="store_true", help="offline deterministic demo (no network)")
    p_sa.add_argument("--target", default="all", choices=("all", "market", "system", "edgar", "news"), help="collect: which poller")
    p_sa.add_argument("--hypothesis-id", default=None, help="hypothesize: which H-XXX to backtest")
    p_sa.add_argument("--symbol", default=SYMBOL, help="hypothesis symbol")
    p_sa.add_argument("--tf", default=TIMEFRAME, help="hypothesis timeframe")
    p_sa.add_argument("--max-ticks", type=int, default=None, help="run: cap ticks (tests)")

    p_hidden.set_defaults(func=cmd_hidden)
    p_hidden.add_argument("--symbol", default=SYMBOL,
                          help="asset (aliases: BTC, ETH, XAU/GOLD)")
    p_hidden.add_argument("--tf", default=TIMEFRAME)
    p_hidden.add_argument("--bars", type=int, default=BARS)
    h_sub = p_hidden.add_subparsers(dest="subcmd", required=False)
    # hidden chart_read [SYMBOL]
    p_cr = h_sub.add_parser("chart_read", help="HMM regime + CVD + kelly (advisory)")
    p_cr.add_argument("symbol", nargs="?", default=None,
                      help="asset (defaults to configured symbol)")
    p_cr.add_argument("--tf", default=TIMEFRAME, help="timeframe")
    p_cr.add_argument("--bars", type=int, default=BARS, help="number of bars")
    # hidden analytics mae|mc [SYMBOL]
    p_an = h_sub.add_parser("analytics", help="MAE/MFE summary or Monte Carlo equity")
    p_an.add_argument("analytics_subcmd", choices=["mae", "mc"],
                      help="mae | mc")
    p_an.add_argument("symbol", nargs="?", default=None,
                      help="asset (defaults to configured symbol)")
    p_an.add_argument("--tf", default=TIMEFRAME, help="timeframe (unused for analytics)")
    p_an.add_argument("--plan-type", default=None,
                      help="filter MAE/MFE summary by plan type")
    p_an.add_argument("--samples", type=int, default=2000,
                      help="Monte Carlo samples (analytics mc only)")
    p_an.add_argument("--seed", type=int, default=None,
                      help="Monte Carlo RNG seed")

    args = ap.parse_args(argv)
    if args.cmd == "scan" and args.symbols is None:
        args.symbols = args.symbol
    if args.cmd is None:
        # Default: open the all-in-one dashboard (watch everything + click to approve)
        from web.app import make_app, serve
        print("=" * 62)
        print(f"🧠 SKY v{VERSION} — Trading Workstation")
        print(f"   open  http://localhost:{DASHBOARD_PORT}")
        print("")
        print("   Everything is clickable in the browser — no command to memorize:")
        print("     📊 Chart          candles, EMA/VWAP/Bollinger, RSI, MACD, S/R, entry/SL/TP")
        print("     🎯 Signal desk    BUY / SELL / NO TRADE with the reason and invalidation")
        print("     ⚡ Trades         approve · reject · execute · close (paper only)")
        print("     🎛 Trade manager  open positions, live R, MAE/MFE, management steps")
        print("     🛡 Risk center    gate, loss budgets, trader state, position-size calculator")
        print("     📓 Journal        a real form: rules, emotion, mistake, what to change")
        print("     🧑‍🏫 Learning       backtest, calibrate, scorecard, simulator")
        print("     ⌘ Command center EVERY CLI command as a button, with its output")
        print("     🧩 Modules        what every part of the engine does")
        print("     ⚙️ System         data health, channels, doctor, MCP")
        print("")
        print("   The desk is advisory. You approve every trade. Paper only —")
        print("   no exchange key exists in this app, so no real order can be sent.")
        print("=" * 62)
        serve(make_app(), DASHBOARD_HOST, DASHBOARD_PORT)
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
