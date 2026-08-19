"""web/command_center.py — every CLI command as a clickable, documented action.

The trader should never have to memorize a command.  This module is the single
source of truth for the browser Command Center:

  * :data:`COMMANDS` — a catalog of the CLI surface (``python main.py …``),
    grouped by category, with a human explanation, declared inputs and a
    safety class for each action.
  * :func:`run_command` — an allow-listed, non-shell runner. Only catalog
    entries can be executed, only declared inputs are accepted, arguments are
    passed as an argv list (never a shell string) and every run has a timeout.

Safety model
------------
``safety`` is one of:

``read``      pure report; changes nothing.
``write``     writes to the local learning database / store (paper only).
``long``      can take minutes (backtests, backfills) — run consciously.
``blocked``   never runnable from the browser (interactive/long-lived
              processes such as ``watch``, ``paper --watch`` and ``mcp``).

No catalog entry can place an exchange order: the engine has no trading keys
and the paper runner is simulation-only.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_TIMEOUT = 180
MAX_TIMEOUT = 900

# ── input helpers ────────────────────────────────────────────────────────
def _text(name: str, label: str, default: str = "", placeholder: str = "",
          required: bool = False, flag: str | None = None) -> dict:
    return {"name": name, "label": label, "type": "text", "default": default,
            "placeholder": placeholder, "required": required,
            "flag": flag if flag is not None else f"--{name.replace('_', '-')}"}


def _int(name: str, label: str, default: int | None = None,
         required: bool = False, flag: str | None = None) -> dict:
    return {"name": name, "label": label, "type": "int", "default": default,
            "required": required,
            "flag": flag if flag is not None else f"--{name.replace('_', '-')}"}


def _choice(name: str, label: str, options: list[str], default: str = "",
            flag: str | None = None) -> dict:
    return {"name": name, "label": label, "type": "choice", "options": options,
            "default": default or (options[0] if options else ""),
            "flag": flag if flag is not None else f"--{name.replace('_', '-')}"}


def _bool(name: str, label: str, default: bool = False,
          flag: str | None = None) -> dict:
    return {"name": name, "label": label, "type": "bool", "default": default,
            "flag": flag if flag is not None else f"--{name.replace('_', '-')}"}


def _positional(name: str, label: str, kind: str = "text", required: bool = True,
                options: list[str] | None = None, default: Any = "") -> dict:
    entry = {"name": name, "label": label, "type": kind, "default": default,
             "required": required, "flag": None, "positional": True}
    if options:
        entry["options"] = options
    return entry


_SYMBOL = _text("symbol", "Asset", "BTCUSDT", "BTCUSDT / ETHUSDT / XAUUSD")
_TF = _choice("tf", "Timeframe", ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"], "15m")


def _cmd(cid: str, category: str, title: str, argv: list[str], what: str,
         *, inputs: list[dict] | None = None, safety: str = "read",
         related: list[str] | None = None, timeout: int = DEFAULT_TIMEOUT,
         note: str = "") -> dict:
    return {"id": cid, "category": category, "title": title, "argv": argv,
            "what": what, "inputs": inputs or [], "safety": safety,
            "related": related or [], "timeout": timeout, "note": note}


# ── the catalog ──────────────────────────────────────────────────────────
COMMANDS: list[dict] = [
    # ── Scan ─────────────────────────────────────────────────────────────
    _cmd("scan", "Scan", "Scan", ["scan"],
         "One full signal scan of an asset: engine plans, desk decision, "
         "entry / stop / take-profit and the reason behind them.",
         inputs=[_SYMBOL, _TF, _bool("json", "Raw JSON output"),
                 _bool("no_save", "Do not store this scan")],
         safety="write", related=["intelligence", "analyze", "review"]),
    _cmd("intelligence", "Scan", "Intelligence", ["intelligence"],
         "Institutional desk report: probability score, trade quality grade, "
         "invalidation, scenarios and management plan.",
         inputs=[_SYMBOL, _TF], related=["scan", "card"]),
    _cmd("card", "Scan", "Signal card", ["card"],
         "Render the Institutional AI Signal Card v2.0 for the asset.",
         inputs=[_SYMBOL, _TF], related=["intelligence"]),
    _cmd("analyze", "Scan", "Analyze", ["analyze"],
         "Full human-trader analysis: multi-timeframe alignment, context, "
         "trading styles and the engine's memory of this market.",
         inputs=[_SYMBOL, _TF], related=["state", "scan"]),
    _cmd("state", "Scan", "State memory", ["state"],
         "What the AI currently remembers about this market plus its recent "
         "state-change event log.",
         inputs=[_SYMBOL, _TF], related=["analyze"]),
    _cmd("sources", "Scan", "Refresh sources", ["sources"],
         "Pull the external information sources (news, Discord, CryptoDada).",
         safety="write", related=["health"]),

    # ── Risk ─────────────────────────────────────────────────────────────
    _cmd("risk", "Risk", "Risk gate", ["risk"],
         "Full risk & discipline status: daily and weekly loss limits, "
         "drawdown ladder, progression level and whether the gate is open.",
         related=["tradestate", "monte", "desk"]),
    _cmd("tradestate", "Risk", "Trader state", ["tradestate"],
         "Set or clear the behavioral no-trade flags. Angry, tired, revenge "
         "or chasing all close the gate until cleared.",
         inputs=[_bool("angry", "Angry"), _bool("tired", "Tired"),
                 _bool("revenge", "Revenge"), _bool("chasing", "Chasing"),
                 _bool("clear", "Clear every flag"),
                 _text("note", "Note", "", "why you set this")],
         safety="write", related=["risk"]),
    _cmd("monte", "Risk", "Monte Carlo", ["monte"],
         "Risk-of-ruin table: expected drawdown, ruin probability, worst "
         "streak and time-to-recovery per risk-per-trade setting.",
         inputs=[_int("samples", "Samples", 2000)], related=["risk"]),
    _cmd("doctor", "Risk", "Doctor", ["doctor"],
         "Full self-diagnosis of the system with a plain-language verdict.",
         inputs=[_bool("strip", "One-line readiness strip only")],
         related=["health", "channels"]),
    _cmd("health", "Risk", "Health", ["health"],
         "System health: data feeds, database, risk gate, MCP and LLM.",
         related=["doctor", "channels"]),
    _cmd("preflight", "Risk", "Preflight", ["preflight"],
         "Strict operations gate before live paper work: refuses to proceed "
         "when data, gate or discipline are not ready.",
         related=["daily", "doctor"]),

    # ── Desk ─────────────────────────────────────────────────────────────
    _cmd("desk", "Desk", "Desk advisory", ["desk"],
         "One-call desk snapshot: gate, P&L, graduation and the single "
         "recommended action for right now.",
         related=["daily", "brief"]),
    _cmd("daily", "Desk", "Daily ritual", ["daily"],
         "The ten-minute daily routine and the one number that matters: "
         "real paper sample count, net expectancy and graduation progress.",
         related=["desk", "scorecard"]),
    _cmd("weekly", "Desk", "Weekly trader review", ["weekly"],
         "W3 Sunday mirror: this week vs all time (net), the R-multiple "
         "distribution, violations and repeating mistakes, the per-setup "
         "graduation tracker, one next practice task and an advisory grade.",
         inputs=[_int("days", "Window (days)", 7),
                 _bool("json", "Raw JSON output")],
         related=["daily", "agent_weekly", "journal"]),
    _cmd("practice", "Desk", "Practice calibration", ["practice"],
         "W3.4 your reads vs the desk plus W3.6 replay-tape outcomes: every "
         "read committed on the Chart tab scored for agreement, and tape "
         "reads graded against the hidden forward window. Study metric "
         "only; it feeds no gate.",
         inputs=[_int("days", "Window (days)", 30),
                 _bool("json", "Raw JSON output")],
         related=["weekly", "daily", "coach"]),
    _cmd("brief", "Desk", "Morning brief", ["brief"],
         "Desk briefing across the whole watchlist before you trade.",
         inputs=[_text("symbols", "Watchlist", "", "BTCUSDT,ETHUSDT,XAUUSD"), _TF],
         related=["agent_morning"]),
    _cmd("agent_morning", "Desk", "Agent morning", ["agent", "morning"],
         "Agent-run morning briefing, audit-logged to the agent run history.",
         inputs=[_text("symbols", "Watchlist", "", "BTCUSDT,ETHUSDT,XAUUSD"), _TF],
         safety="write", related=["brief"]),
    _cmd("agent_all", "Desk", "Agent full run", ["agent", "all"],
         "One desk run: health, briefing and graduation together.",
         inputs=[_TF], safety="write", related=["agent_morning"]),
    _cmd("agent_weekly", "Desk", "Weekly review", ["agent", "weekly-review"],
         "Weekly trader review: metrics, rule compliance and change detection.",
         safety="write", related=["scorecard", "journal_summary"]),
    _cmd("agent_watchdog", "Desk", "Watchdog", ["agent", "watchdog"],
         "Paper-trade monitoring plus stale-position alarms.",
         safety="write", related=["paper_once"]),
    _cmd("agent_reviewer", "Desk", "Paper reviewer", ["agent", "paper-reviewer"],
         "Post-mortem aggregation over every closed paper trade.",
         safety="write", related=["scorecard"]),
    _cmd("sky_agent_health", "Desk", "24/7 agent health", ["sky-agent", "health"],
         "System probe for the research daemon: CPU/RAM/disk plus the "
         "readiness strip. Research only — never trades.",
         inputs=[_bool("json", "Raw JSON output")],
         related=["sky_agent_status", "doctor", "health"]),
    _cmd("sky_agent_status", "Desk", "24/7 agent status", ["sky-agent", "status"],
         "Recent hypotheses, archived intelligence reports, regime log and "
         "SEC event rows. Read-only memory, not evidence for graduation.",
         inputs=[_bool("json", "Raw JSON output")],
         related=["sky_agent_report", "sky_agent_health"]),
    _cmd("sky_agent_report", "Desk", "24/7 agent daily report", ["sky-agent", "report"],
         "Evidence-backed daily intelligence report. Recommendations are "
         "WATCH / CONSIDER / WAIT / AVOID only — never BUY NOW.",
         inputs=[_bool("demo", "Offline demo payload"),
                 _bool("json", "Raw JSON output")],
         related=["sky_agent_status", "daily"]),
    _cmd("sky_agent_collect", "Desk", "24/7 agent collect", ["sky-agent", "collect"],
         "One polling pass: market snapshot, system probe, news, optional "
         "EDGAR demo ingest. Writes research memory only.",
         inputs=[_choice("target", "Target", ["all", "market", "system", "edgar", "news"], "all"),
                 _bool("demo", "Offline demo (no network)"),
                 _bool("json", "Raw JSON output")],
         safety="write", related=["sky_agent_status"]),
    _cmd("sky_agent_run", "Desk", "24/7 agent daemon", ["sky-agent", "run"],
         "Long-lived research daemon. It never exits, so run it under "
         "systemd or a terminal — not from the browser.",
         safety="blocked",
         note="run in a terminal: python main.py sky-agent run --demo"),
    _cmd("ask", "Desk", "Ask the desk", ["ask"],
         "Ask a natural-language question; the answer is grounded in the "
         "trading library with citations.",
         inputs=[_positional("question", "Question", "text", True, default="")],
         related=["coach"]),

    # ── Trades ───────────────────────────────────────────────────────────
    _cmd("review", "Trades", "Review queue", ["review"],
         "List every signal waiting for your approval.",
         inputs=[_text("symbol", "Asset filter", "", "optional")],
         related=["approve", "reject"]),
    _cmd("approve", "Trades", "Approve", ["approve"],
         "Approve a pending signal. The risk gate is enforced — a closed gate "
         "refuses the approval unless you consciously force it.",
         inputs=[_positional("scan_id", "Scan ID", "int"),
                 _text("note", "Note", ""), _bool("force", "Force past a closed gate")],
         safety="write", related=["execute", "reject"]),
    _cmd("reject", "Trades", "Reject", ["reject"],
         "Reject a pending signal and record why.",
         inputs=[_positional("scan_id", "Scan ID", "int"), _text("note", "Note", "")],
         safety="write", related=["review"]),
    _cmd("execute", "Trades", "Execute (paper)", ["execute"],
         "Mark an approved signal as executed. Paper only — no exchange order "
         "is ever sent.",
         inputs=[_positional("scan_id", "Scan ID", "int"), _text("note", "Note", "")],
         safety="write", related=["close"]),
    _cmd("close", "Trades", "Close", ["close"],
         "Close an executed signal and record the outcome.",
         inputs=[_positional("scan_id", "Scan ID", "int"), _text("note", "Note", "")],
         safety="write", related=["journal_new", "postreview"]),
    _cmd("signal", "Trades", "Signal detail", ["signal"],
         "Full detail and lifecycle trail for one scan.",
         inputs=[_positional("scan_id", "Scan ID", "int")],
         related=["review"]),
    _cmd("paper_once", "Trades", "Paper run (once)", ["paper"],
         "One pass of the paper runner: enroll approvals, check open "
         "positions, record fills and exits. Never sends a real order.",
         inputs=[_text("symbol", "Asset filter", "", "optional")],
         safety="write", related=["agent_watchdog"]),
    _cmd("postreview", "Trades", "Post-trade review", ["postreview"],
         "Post-trade review of a closed scan: R achieved, MAE/MFE and the "
         "discipline verdict.",
         inputs=[_positional("scan_id", "Scan ID", "int")],
         related=["journal_new"]),

    # ── Learning ─────────────────────────────────────────────────────────
    _cmd("backtest", "Learning", "Backtest", ["backtest"],
         "Walk-forward grade of the engine's plans over history.",
         inputs=[_SYMBOL, _TF, _int("bars", "Bars", 500),
                 _bool("save", "Store the graded outcomes")],
         safety="long", timeout=600, related=["scorecard", "learn"]),
    _cmd("learn", "Learning", "Learn / calibrate", ["learn"],
         "Recompute the self-improvement calibration profile from every "
         "graded outcome.",
         safety="write", related=["stats", "backtest"]),
    _cmd("stats", "Learning", "Stats", ["stats"],
         "What the engine has actually learned so far.",
         inputs=[_text("symbol", "Asset filter", "", "optional")],
         related=["scorecard"]),
    _cmd("scorecard", "Learning", "Scorecard", ["scorecard"],
         "Strategy scorecard net of costs: by setup, regime, side and "
         "session, with Sharpe / Sortino / Calmar and holding time.",
         inputs=[_choice("source", "Book", ["db", "backtest", "paper", "store"], "db"),
                 _text("symbol", "Asset filter", "", "optional"),
                 _int("min_decided", "Minimum decided trades", 30),
                 _bool("quality", "Include quality score")],
         safety="long", timeout=600, related=["daily", "quality"]),
    _cmd("quality", "Learning", "Backtest quality", ["quality"],
         "Backtest Quality Score 0–100 with the parameter-plateau sweep — "
         "catches an edge that only exists at one setting.",
         inputs=[_text("symbol", "Asset", "BTCUSDT"), _TF],
         safety="long", timeout=600, related=["scorecard"]),
    _cmd("simulator", "Learning", "Simulator", ["simulator"],
         "Grind unique backtest and paper samples per setup toward the "
         "100/20 evidence bar. Simulator rows never count as live evidence.",
         inputs=[_int("rounds", "Rounds", 3),
                 _text("symbols", "Assets", "", "BTCUSDT,ETHUSDT"), _TF],
         safety="long", timeout=900, related=["scorecard", "daily"]),
    _cmd("validate", "Learning", "Look-ahead guard", ["validate", "lookahead"],
         "Scan the engine source for future-shift (look-ahead) leaks.",
         related=["quality"]),
    _cmd("correlation", "Learning", "Correlation", ["correlation"],
         "Cross-asset correlation view used by the portfolio veto.",
         related=["stats"]),
    _cmd("hidden_chart", "Learning", "Chart read (hidden alpha)", ["hidden", "chart_read"],
         "Hidden-alpha read: HMM regime, cumulative volume delta and the "
         "Kelly advisory. Advisory only.",
         inputs=[_positional("symbol", "Asset", "text", False, default="BTCUSDT"), _TF],
         related=["risk"]),

    # ── Journal ──────────────────────────────────────────────────────────
    _cmd("journal_new", "Journal", "New journal entry", ["journal"],
         "Record the post-trade fields for a scan: did you follow the system, "
         "how did you feel, what was the mistake, what would you change.",
         inputs=[_positional("scan_id", "Scan ID", "int"),
                 _choice("followed_rules", "Followed rules", ["1", "0"], "1"),
                 _choice("emotion", "Emotion",
                         ["calm", "anxious", "euphoric", "fearful", "frustrated",
                          "greedy", "revengeful", "bored", "confident"], "calm"),
                 _text("mistake", "Mistake", "none"),
                 _text("would_change", "What would you change", ""),
                 _text("notes", "Notes", "")],
         safety="write", related=["journal_summary", "postreview"]),
    _cmd("journal_summary", "Journal", "Journal summary", ["journal"],
         "Discipline summary across every journalled trade.",
         related=["scorecard"]),

    # ── Data ─────────────────────────────────────────────────────────────
    _cmd("store", "Data", "Store inspector", ["store"],
         "Inspect the local candle store: rows, span and partitions.",
         inputs=[_choice("market", "Market", ["spot", "perp"], "spot")],
         related=["backfill"]),
    _cmd("backfill", "Data", "Backfill history", ["backfill"],
         "Download paginated candle history into the local Parquet store.",
         inputs=[_SYMBOL, _choice("tf", "Timeframe",
                                  ["1m", "5m", "15m", "1h", "4h", "1d"], "1m"),
                 _choice("market", "Market", ["spot", "perp"], "perp"),
                 _text("since", "Since", "30d", "30d / 2026-01-01 / epoch ms"),
                 _bool("dry_run", "Dry run (count only, write nothing)")],
         safety="long", timeout=900, related=["store", "derivatives_status"]),
    _cmd("derivatives_status", "Data", "Derivatives status", ["derivatives", "status"],
         "What derivatives series (funding, open interest, basis) are stored.",
         related=["derivatives_collect"]),
    _cmd("derivatives_collect", "Data", "Collect derivatives", ["derivatives", "collect"],
         "Collect funding, open interest, mark, index and basis history.",
         inputs=[_SYMBOL], safety="long", timeout=900,
         related=["derivatives_status"]),
    _cmd("cross_status", "Data", "Cross-exchange status", ["cross", "status"],
         "What cross-exchange premium and funding-spread series are stored.",
         related=["cross_collect"]),
    _cmd("cross_collect", "Data", "Collect cross-exchange", ["cross", "collect"],
         "Collect premium/discount and funding spread across venues.",
         inputs=[_SYMBOL], safety="long", timeout=900, related=["cross_status"]),
    _cmd("calendar", "Data", "Trading calendar", ["calendar"],
         "Is the venue open, and how much of a stored series was scheduled "
         "closure?",
         inputs=[_text("symbol", "Asset", "XAUUSD")], related=["store"]),

    # ── Integration ──────────────────────────────────────────────────────
    _cmd("channels", "Integration", "Channel registry", ["channels"],
         "Every external dependency as an ordered channel, and which backend "
         "is actually serving right now.",
         related=["doctor", "health"]),
    _cmd("sourcetrust", "Integration", "Source trust", ["sourcetrust"],
         "Record an information source's tier (1–5) and trust (0–1).",
         inputs=[_positional("source", "Source", "text"),
                 _positional("tier", "Tier 1-5", "int", default=3),
                 _positional("trust", "Trust 0-1", "text", default="0.5")],
         safety="write", related=["channels"]),
    _cmd("hub_first_night", "Hub", "First night (home PC)", ["hub", "first-night"],
         "One-page checklist to run SKY 24h on a home Ubuntu PC. "
         "No trade keys, no public :8050.",
         related=["hub_status", "hub_doctor", "hub_role"]),
    _cmd("hub_role", "Hub", "This PC role", ["hub", "role"],
         "How the always-on Ubuntu PC is used: one Hub, one research agent, "
         "no second PC-use agent, no live execution.",
         related=["hub_status", "hub_first_night", "sky_agent_health"]),
    _cmd("hub_status", "Hub", "Hub status", ["hub", "status"],
         "Ubuntu Hub layout, disk, backups and systemd snapshot. "
         "Does not place an order.",
         related=["hub_doctor", "hub_backup"]),
    _cmd("hub_doctor", "Hub", "Hub doctor", ["hub", "doctor"],
         "Hub health: private env, loopback bind, disk, backup privacy.",
         related=["hub_status", "doctor"]),
    _cmd("hub_backup", "Hub", "Hub backup", ["hub", "backup"],
         "SQLite-safe + redacted-config backup under /var/lib/sky/backups. "
         "Secrets are stripped. Archives are mode 0600.",
         safety="write", related=["hub_status"]),
    _cmd("release_drills", "Hub", "Release drills", ["release", "drills"],
         "P22.3 catalog of trusted signing and clean-target install/upgrade/"
         "rollback drills. Linux CI cannot pass them; attach operator evidence.",
         related=["hub_doctor", "companion_lint"]),
    _cmd("companion_lint", "Hub", "Companion lint", ["companion", "lint"],
         "Static inventory of the Windows and Android project trees. "
         "Refuses committed keystores and any live-order path.",
         related=["release_drills"]),
    _cmd("mcp", "Integration", "MCP server", ["mcp"],
         "Long-lived Model Context Protocol server for Claude Desktop or "
         "Cursor. Start it from a terminal, not the browser.",
         safety="blocked", note="run in a terminal: python main.py mcp"),

    # ── Education ────────────────────────────────────────────────────────
    _cmd("coach", "Education", "Coach", ["coach"],
         "Teaching mode: what the setup is, why it exists, how it can fail "
         "and personal feedback on your decisions.",
         inputs=[_SYMBOL, _TF], related=["glossary", "ask"]),
    _cmd("glossary", "Education", "Glossary", ["glossary"],
         "Every trading term the engine uses, in plain language.",
         related=["coach"]),
    _cmd("skill", "Education", "Skill pack", ["skill"],
         "Show the Claude skill pack definition for this desk.",
         inputs=[_bool("dry_run", "Preview only", True)], related=["mcp"]),

    # ── Long-lived processes (never run from the browser) ────────────────
    _cmd("watch", "Scan", "Watch loop", ["watch"],
         "Continuous monitor loop. It never exits, so run it in a terminal.",
         safety="blocked", note="run in a terminal: python main.py watch --symbol BTCUSDT"),
    _cmd("paper_watch", "Trades", "Paper watch loop", ["paper", "--watch"],
         "Continuous paper monitoring that survives closing this browser tab.",
         safety="blocked", note="run in a terminal: python main.py paper --watch"),
]

CATEGORY_ORDER = ["Scan", "Risk", "Desk", "Trades", "Learning", "Journal",
                  "Data", "Hub", "Integration", "Education"]

BY_ID: dict[str, dict] = {c["id"]: c for c in COMMANDS}


def catalog() -> dict:
    """The full clickable catalog, grouped by category (browser-ready)."""
    groups: dict[str, list[dict]] = {}
    for cmd in COMMANDS:
        groups.setdefault(cmd["category"], []).append({
            **{k: v for k, v in cmd.items() if k != "argv"},
            "cli": "python main.py " + " ".join(cmd["argv"]),
        })
    ordered = [{"category": name, "commands": groups[name]}
               for name in CATEGORY_ORDER if name in groups]
    for name in sorted(groups):
        if name not in CATEGORY_ORDER:
            ordered.append({"category": name, "commands": groups[name]})
    return {"categories": ordered, "count": len(COMMANDS)}


class CommandError(ValueError):
    """Raised when a command id is unknown, blocked or badly parameterised."""


def _coerce(spec: dict, raw: Any) -> Any:
    kind = spec.get("type", "text")
    if kind == "int":
        if raw in (None, "", []):
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            raise CommandError(f"{spec['name']} must be a whole number")
    if kind == "bool":
        return bool(raw) and str(raw).lower() not in ("0", "false", "no", "")
    if kind == "choice":
        text = str(raw or "").strip()
        options = spec.get("options") or []
        if text and options and text not in options:
            raise CommandError(f"{spec['name']} must be one of: {', '.join(options)}")
        return text
    text = str(raw if raw is not None else "").strip()
    if "\n" in text:
        raise CommandError(f"{spec['name']} must be a single line")
    return text


def build_argv(command_id: str, params: dict | None = None) -> list[str]:
    """Translate a catalog id + user inputs into a safe argv list."""
    cmd = BY_ID.get(command_id)
    if cmd is None:
        raise CommandError(f"unknown command: {command_id}")
    if cmd["safety"] == "blocked":
        raise CommandError(
            cmd.get("note") or f"{command_id} must be run in a terminal")
    params = params or {}
    argv = list(cmd["argv"])
    positionals: list[str] = []
    for spec in cmd["inputs"]:
        value = _coerce(spec, params.get(spec["name"], spec.get("default")))
        if spec.get("positional"):
            if value in (None, "", False):
                if spec.get("required"):
                    raise CommandError(f"{spec['label']} is required")
                continue
            positionals.append(str(value))
            continue
        if spec["type"] == "bool":
            if value:
                argv.append(spec["flag"])
            continue
        if value in (None, ""):
            if spec.get("required"):
                raise CommandError(f"{spec['label']} is required")
            continue
        argv.extend([spec["flag"], str(value)])
    # positionals belong directly after the subcommand words
    head = len(cmd["argv"])
    argv = argv[:head] + positionals + argv[head:]
    return argv


def run_command(command_id: str, params: dict | None = None,
                timeout: int | None = None) -> dict:
    """Run one catalog command as a subprocess and capture its output.

    Never uses a shell, never accepts a free-form command string, and only
    ever runs ``python main.py <catalog argv>`` from the project root.
    """
    cmd = BY_ID.get(command_id)
    if cmd is None:
        raise CommandError(f"unknown command: {command_id}")
    argv = build_argv(command_id, params)
    limit = min(int(timeout or cmd.get("timeout") or DEFAULT_TIMEOUT), MAX_TIMEOUT)
    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")
    env["SKY_NO_AUTO_INSTALL"] = "1"   # the dashboard's interpreter already has deps
    started = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "main.py"), *argv],
            cwd=str(ROOT), env=env, capture_output=True, text=True,
            timeout=limit, check=False)
        output = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        ok = proc.returncode == 0
        code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        output += f"\n… timed out after {limit}s — run this one in a terminal."
        ok, code = False, -1
    return {
        "ok": ok,
        "command_id": command_id,
        "cli": "python main.py " + " ".join(argv),
        "exit_code": code,
        "elapsed_ms": int((time.time() - started) * 1000),
        "output": output.strip() or "(no output)",
    }
