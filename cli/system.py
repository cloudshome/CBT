"""cli/system.py — the system/release command cluster (hub/release/companion/...).

Refactor step 3 of the main.py maintainability debt (ROADMAP §19): the
system commands (preflight, mcp, sky-agent, release, companion, hub, hidden,
skill) used to live inline in ``main.py``; they live here now, byte-identical,
and ``main`` re-exports them so the argparse wiring keeps working unchanged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from cli.common import _client, _sym
from config import SYMBOL


def cmd_preflight(args) -> int:
    """Strict readiness gate for unattended live-data paper operations."""
    from brain.preflight import format_preflight, preflight_report

    report = preflight_report(allow_demo=args.allow_demo)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(format_preflight(report))
    return 0 if report["ready"] else 2


def cmd_mcp(args) -> int:
    """Run the Model Context Protocol server (stdio) for MCP clients."""
    from ai.mcp_server import run as mcp_run

    return mcp_run()


def cmd_sky_agent(args) -> int:
    """24/7 SKY Intelligence Agent — research & monitoring (never trades).

    Subcommands:
      health   — readiness + system probe (cheap, runs in <1s)
      status   — agent memory / recent reports / hypotheses
      collect  — one polling pass (market / edgar / news / system)
      report   — daily intelligence report (markdown or json)
      run      — daemon loop (systemd ExecStart; --demo for offline)
      hypothesize — propose/test trading hypotheses
    """
    action = getattr(args, "sky_agent_action", "health")
    is_json = getattr(args, "json", False)

    if action == "health":
        from brain.agent import readiness_strip
        from sky_agent.monitor_system import probe_system

        try:
            strip = readiness_strip()
        except Exception as exc:
            strip = {"error": str(exc)}
        sys_probe = probe_system()
        payload = {
            "readiness": strip,
            "system": sys_probe,
            "agent": "sky_agent",
            "ok": sys_probe.get("level") not in ("HIGH", "CRITICAL")
            or not sys_probe.get("alerts"),
        }
        if is_json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(
                f"SKY Agent health — system level {sys_probe.get('level')}  alerts: {sys_probe.get('alerts') or 'none'}"
            )
            print(
                f"  cpu {sys_probe.get('cpu_pct')}%  ram {sys_probe.get('ram_pct')}%  disk {sys_probe.get('disk_pct')}%"
            )
            print(f"  db_ok={sys_probe.get('db_ok')}")
            if strip.get("readiness") or strip.get("error"):
                print(f"  readiness: {str(strip)[:400]}")
        return 0

    if action == "status":
        from data.database import SignalDB
        from sky_agent.memory import ensure_memory_schema

        with SignalDB() as db:
            ensure_memory_schema(db)
            hyps = db.conn.execute(
                "SELECT hypothesis_id,setup,status,created_ts FROM research_hypotheses ORDER BY created_ts DESC LIMIT 20"
            ).fetchall()
            reports = db.conn.execute(
                "SELECT report_date,kind,asset,recommendation,level,created_ts FROM intelligence_reports ORDER BY created_ts DESC LIMIT 10"
            ).fetchall()
            regimes = db.conn.execute(
                "SELECT symbol,timeframe,regime,volatility_state,ts FROM market_regime_log ORDER BY ts DESC LIMIT 10"
            ).fetchall()
            filings = db.conn.execute(
                "SELECT accession,event_type,severity FROM sec_events ORDER BY created_ts DESC LIMIT 10"
            ).fetchall()
        payload = {
            "hypotheses": [dict(r) for r in hyps],
            "reports": [dict(r) for r in reports],
            "regimes": [dict(r) for r in regimes],
            "sec_events": [dict(r) for r in filings],
        }
        if is_json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(
                f"hypotheses: {len(hyps)}  reports: {len(reports)}  regimes: {len(regimes)}  sec_events: {len(filings)}"
            )
            for r in hyps[:5]:
                print(f"  {r['hypothesis_id']} {r['setup']} [{r['status']}]")
            for r in reports[:5]:
                print(
                    f"  report {r['report_date']} {r['kind']} {r['asset']} → {r['recommendation']} [{r['level']}]"
                )
        return 0

    if action == "collect":
        demo = bool(getattr(args, "demo", False))
        target = getattr(args, "target", "all")
        results: dict = {}
        if target in ("all", "market"):
            from sky_agent.monitor_market import scan_market_snapshot

            results["market"] = {"events": len(scan_market_snapshot(demo=demo))}
        if target in ("all", "system"):
            from sky_agent.monitor_system import probe_system

            results["system"] = probe_system()
        if target in ("all", "edgar"):
            from sky_agent.collectors.edgar import ingest_recent_filings, upsert_filings

            rows = ingest_recent_filings(demo=demo)
            results["edgar"] = {"filings": upsert_filings(rows)}
        if target in ("all", "news"):
            from sky_agent.collectors.news import collect_news

            results["news"] = {"items": len(collect_news(limit=10))}
        if is_json:
            print(json.dumps(results, indent=2, default=str))
        else:
            print(json.dumps(results, indent=2, default=str))
        return 0

    if action == "report":
        demo = bool(getattr(args, "demo", False))
        from sky_agent.daily_report import build_daily_report, format_report_md

        report = build_daily_report(demo=demo)
        if is_json:
            print(json.dumps(report, indent=2, default=str))
        else:
            print(format_report_md(report))
        return 0

    if action == "run":
        demo = bool(getattr(args, "demo", False))
        max_ticks = getattr(args, "max_ticks", None)
        from sky_agent.daemon import run_forever

        result = run_forever(demo=demo, max_ticks=max_ticks)
        if is_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(json.dumps(result, indent=2, default=str))
        return 0

    if action == "hypothesize":
        demo = bool(getattr(args, "demo", False))
        from sky_agent.hypothesis import propose_hypotheses, run_hypothesis_backtest

        hyps = propose_hypotheses()
        target = getattr(args, "hypothesis_id", None)
        payload: dict = {"proposed": hyps}
        if target:
            payload["backtest"] = run_hypothesis_backtest(
                target,
                symbol=getattr(args, "symbol", "BTCUSDT"),
                timeframe=getattr(args, "tf", "15m"),
            )
        if is_json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(json.dumps(payload, indent=2, default=str))
        return 0

    print(f"[!] unknown sky-agent action: {action}", file=sys.stderr)
    return 1


def cmd_release(args) -> int:
    """P22.3 signing + clean-target drill catalog / evidence check."""
    from ops.release_drills import DrillError, evaluate_file, format_catalog, p22_status

    action = getattr(args, "release_action", "drills")
    if action in ("drills", "sign-plan", "status"):
        payload = p22_status(getattr(args, "evidence_dir", None))
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(format_catalog(payload))
        return 0
    if action == "check":
        try:
            verdict = evaluate_file(args.drill, args.evidence)
        except DrillError as exc:
            print(f"[!] {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(verdict, indent=2, default=str))
        else:
            print(f"{verdict['drill']}: {verdict['note']}")
            if verdict["missing"]:
                print("  missing: " + ", ".join(verdict["missing"]))
        return 0 if verdict["passed"] else 1
    print(f"[!] unknown release action {action}", file=sys.stderr)
    return 1


def cmd_companion(args) -> int:
    """P20/P21 contracts + P22.2 native project lint (unsigned)."""
    platform = getattr(args, "platform", "windows")
    action = getattr(args, "companion_action", "spec")
    if action == "lint":
        from ops.native_projects import format_status, native_status

        payload = native_status()
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(format_status(payload))
        return 0 if payload.get("ok") else 1
    if action == "spec":
        if platform == "android":
            from ops.android_companion import android_spec, format_spec
        else:
            from ops.windows_companion import companion_spec, format_spec
        spec = android_spec() if platform == "android" else companion_spec()
        if args.json:
            print(json.dumps(spec, indent=2))
        else:
            print(format_spec(spec))
        return 0
    if action == "validate-url":
        try:
            if platform == "android":
                from ops.android_companion import CompanionError, validate_hub_url
            else:
                from ops.windows_companion import CompanionError, validate_hub_url
            url = validate_hub_url(args.hub)
        except CompanionError as exc:
            print(f"[!] {exc}", file=sys.stderr)
            return 1
        print(url)
        return 0
    if action == "status":
        if platform == "android":
            from ops.android_companion import KeystoreTokenStore as TokenStore
        else:
            from ops.windows_companion import TokenStore
        store = TokenStore(args.state)
        rec = store.load()
        if rec is None:
            print("not paired")
            return 1
        rec = {k: v for k, v in rec.items() if k != "token"}
        if args.json:
            print(json.dumps(rec, indent=2, default=str))
        else:
            print(f"paired to {rec.get('hub_url')}  scope={rec.get('scope')}")
        return 0
    print(f"[!] unknown companion action {action}", file=sys.stderr)
    return 1


def cmd_hub(args) -> int:
    """Ubuntu Hub operations, including the P22 redacted support bundle."""
    from ops.hub import dispatch, format_doctor, format_status

    action = args.hub_action
    try:
        payload = dispatch(
            action,
            prefix=getattr(args, "prefix", None),
            mode=getattr(args, "mode", "local"),
            owner=getattr(args, "owner", "") or "",
            archive=getattr(args, "archive", None),
            overwrite=bool(getattr(args, "overwrite", False)),
            purge=bool(getattr(args, "purge", False)),
            include_store=not bool(getattr(args, "no_store", False)),
            retention_days=int(getattr(args, "retention_days", 14) or 14),
            unit=getattr(args, "unit", "sky-dashboard.service"),
            lines=int(getattr(args, "lines", 80) or 80),
            platform=getattr(args, "platform", "windows"),
        )
    except (ValueError, FileNotFoundError, FileExistsError, PermissionError) as exc:
        print(f"[!] hub {action}: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    elif action == "status":
        print(format_status(payload))
    elif action == "doctor":
        print(format_doctor(payload))
    elif action == "logs":
        for line in payload.get("lines") or []:
            print(line)
        if not payload.get("ok"):
            print(payload.get("error") or "journalctl unavailable", file=sys.stderr)
            return 1
    elif action in ("first-night", "first_night", "guide"):
        print(payload.get("guide") or "")
    elif action in ("role", "host-role", "pc"):
        print(f"SKY Hub role: {payload.get('role')}")
        print(f"  {payload.get('decision')}")
        print(f"  {payload.get('why')}")
        print("  run on this PC:")
        for item in payload.get("run") or []:
            mark = "*" if item.get("required") else "-"
            print(f"    {mark} {item.get('unit')}: {item.get('job')}")
        print("  human still does: " + "; ".join(payload.get("human_still_does") or []))
        print("  do not run: " + "; ".join(payload.get("do_not_run") or []))
        print("  live exchange execution  NO")
    else:
        print(json.dumps(payload, indent=2, default=str))
    return 0 if payload.get("ok", True) else 1


def cmd_hidden(args) -> int:
    """Hidden alpha CLI: regime + CVD + kelly + MAE/MFE + Monte Carlo.

    Usage:
      python main.py hidden chart_read [SYMBOL]        # HMM regime + CVD + kelly
      python main.py hidden analytics mae [SYMBOL]     # MAE/MFE summary from DB
      python main.py hidden analytics mc [SYMBOL]      # Monte Carlo equity dist
    """
    from brain.analytics import mae_mfe_summary, monte_carlo_equity
    from data.database import SignalDB
    from engine.hidden_alpha import format_hidden, hidden_alpha_report

    # Subparser positional "symbol" overwrites parent --symbol; fall back to default
    symbol = _sym(args.symbol or SYMBOL)
    tf = args.tf

    if args.subcmd in (None, "chart_read"):
        client = _client()
        df = client.klines(symbol, tf, args.bars)
        report = hidden_alpha_report(df, symbol, tf)
        print(format_hidden(report))
        return 0

    if args.subcmd == "analytics":
        with SignalDB() as db:
            if args.analytics_subcmd == "mae":
                r = mae_mfe_summary(db, plan_type=args.plan_type)
            elif args.analytics_subcmd == "mc":
                r = monte_carlo_equity(db, samples=args.samples, seed=args.seed)
            else:
                print(
                    f"[!] unknown analytics subcommand: {args.analytics_subcmd}",
                    file=sys.stderr,
                )
                return 1
            print(json.dumps(r, indent=2, default=str))
        return 0

    print(f"[!] unknown hidden subcommand: {args.subcmd}", file=sys.stderr)
    return 1


def cmd_skill(args) -> int:
    """Print or install the agent-facing SKILL.md.

    Default behaviour: print the SKILL to stdout (read-only, never
    writes anywhere). With --install --system, copy the SKILL to
    ``~/.claude/skills/cryptobrain/SKILL.md`` (the directory layout
    Claude Code, Cursor, and Arena all recognise). --dry-run previews
    the path without touching the filesystem.
    """

    # Resolve to the repo root regardless of where this module lives: the
    # command previously sat in main.py (repo root) and read <root>/SKILL.md.
    skill_path = Path(__file__).resolve().parent.parent / "SKILL.md"
    if not skill_path.exists():
        print(f"SKILL.md not found at {skill_path}", file=sys.stderr)
        return 1

    # Default / --print: just dump it to stdout
    if not args.install and not args.uninstall:
        sys.stdout.write(skill_path.read_text(encoding="utf-8"))
        return 0

    # Mutating paths require --system (matches Agent-Reach's stance)
    if not args.system:
        print(
            "Refusing to write under $HOME without --system.\n"
            "Default is inspect-only. Re-run with --system to permit "
            "filesystem writes, or add --dry-run to preview.",
            file=sys.stderr,
        )
        return 2

    target_dir = (
        Path(args.target_dir).expanduser()
        if args.target_dir
        else Path.home() / ".claude" / "skills" / "cryptobrain"
    )
    target_path = target_dir / "SKILL.md"

    if args.uninstall:
        if args.dry_run:
            print(f"[dry-run] would remove {target_path}")
            return 0
        try:
            if target_path.is_symlink() or target_path.exists():
                target_path.unlink()
            # Best-effort: remove the now-empty parent dir
            try:
                target_dir.rmdir()
            except OSError:
                pass
            print(f"removed {target_path}")
        except FileNotFoundError:
            print(f"not installed at {target_path} (no-op)")
        return 0

    # --install
    if args.dry_run:
        print(
            f"[dry-run] would write {len(skill_path.read_text(encoding='utf-8'))} bytes "
            f"to {target_path}"
        )
        return 0

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"could not create {target_dir}: {exc}", file=sys.stderr)
        return 1
    try:
        # Atomic-ish write: write to .tmp then rename
        tmp = target_path.with_suffix(".md.tmp")
        tmp.write_text(skill_path.read_text(encoding="utf-8"), encoding="utf-8")
        tmp.replace(target_path)
    except OSError as exc:
        print(f"could not write {target_path}: {exc}", file=sys.stderr)
        return 1
    print(f"installed {target_path}")
    return 0
