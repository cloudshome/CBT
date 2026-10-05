"""
main.py
=======
Master entrypoint for SKY / CBT operations and SDCC collective commands.
"""

import sys

try:
    from cli.common import (  # noqa: F401
        _client, _load_calibration, _source_key_arg, _sym, _symbols, run_scan,
    )
    from cli.validation import (  # noqa: F401
        cmd_backtest, cmd_edge_validate, cmd_monte, cmd_validate, cmd_xau_evidence,
    )
    from cli.daily import (  # noqa: F401
        cmd_scan, _print_human, cmd_watch, cmd_sources, cmd_signal, cmd_learn, cmd_coach,
        cmd_glossary, _print_context, cmd_intelligence, cmd_card, cmd_analyze, cmd_state,
        cmd_stats, cmd_web, cmd_sourcetrust, cmd_risk, cmd_tradestate, cmd_journal, cmd_ask,
        cmd_postreview, cmd_agent, cmd_brief, cmd_health, cmd_desk, cmd_daily, cmd_weekly,
        cmd_practice,
    )
    from cli.paper import (  # noqa: F401
        _print_review_row, cmd_review, _decide, cmd_approve, cmd_reject, cmd_execute,
        cmd_close, _print_paper_run, cmd_paper, cmd_simulator,
    )
    from cli.analytics import (  # noqa: F401
        cmd_scorecard, cmd_calendar, cmd_quality,
    )
    from cli.market import (  # noqa: F401
        cmd_backfill, cmd_store, cmd_doctor, cmd_channels, cmd_derivatives, cmd_cross,
        cmd_correlation,
    )
    from cli.system import (  # noqa: F401
        cmd_preflight, cmd_mcp, cmd_sky_agent, cmd_release, cmd_companion, cmd_hub,
        cmd_hidden, cmd_skill,
    )
except ImportError:
    pass


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:]) if argv is None else list(argv)
    if args and args[0] == "collective":
        from core.collective.cli import run_collective_cli
        return run_collective_cli(args[1:])

    if args and args[0] == "desk":
        print("Crypto Brain Terminal Desk")
        return 0

    if args and args[0] == "validate":
        import argparse
        import json
        from data.validation import print_lookahead, scan_lookahead

        parser = argparse.ArgumentParser(prog="validate lookahead")
        parser.add_argument("sub", nargs="?", default="lookahead")
        parser.add_argument("--path", dest="paths", action="append")
        parser.add_argument("--json", action="store_true")
        parsed, _ = parser.parse_known_args(args[1:])
        report = scan_lookahead(paths=parsed.paths)
        if parsed.json:
            print(json.dumps(report))
        else:
            print_lookahead(report)
        return 0 if report.get("ok") else 1

    if args and args[0] == "scorecard":
        import argparse
        from cli.analytics import cmd_scorecard

        parser = argparse.ArgumentParser(prog="scorecard")
        parser.add_argument("--source", default="db", choices=("db", "backtest", "paper", "store"))
        parser.add_argument("--symbol", default=None)
        parser.add_argument("--tf", default="15m")
        parser.add_argument("--exchange", default="binance")
        parser.add_argument("--market", default="perp")
        parser.add_argument("--bars", type=int, default=1000)
        parser.add_argument("--horizons", default="4")
        parser.add_argument("--min-bars", type=int, default=50)
        parser.add_argument("--step", type=int, default=3)
        parser.add_argument("--min-conf", type=int, default=50)
        parser.add_argument("--min-decided", type=int, default=30)
        parser.add_argument("--exclude-sim", action="store_true")
        parser.add_argument("--since", default=None)
        parser.add_argument("--until", default=None)
        parser.add_argument("--no-costs", action="store_true")
        parser.add_argument("--maker", action="store_true")
        parser.add_argument("--conditioned", action="store_true")
        parser.add_argument("--quality", action="store_true")
        parser.add_argument("--source-key", default=None)
        parser.add_argument("--json", action="store_true")
        parsed, _ = parser.parse_known_args(args[1:])
        return cmd_scorecard(parsed)

    if args and args[0] == "release":
        import argparse
        from cli.system import cmd_release

        parser = argparse.ArgumentParser(prog="release")
        parser.add_argument("release_action", nargs="?", default="drills",
                            choices=("drills", "sign-plan", "status", "check"))
        parser.add_argument("--drill", default="")
        parser.add_argument("--evidence", default="")
        parser.add_argument("--evidence-dir", default=None)
        parser.add_argument("--json", action="store_true")
        parsed, _ = parser.parse_known_args(args[1:])
        return cmd_release(parsed)

    if args and args[0] == "sky-agent":
        import argparse
        from cli.system import cmd_sky_agent

        parser = argparse.ArgumentParser(prog="sky-agent")
        parser.add_argument("sky_agent_action", nargs="?", default="health",
                            choices=("health", "status", "collect", "report", "run", "hypothesize"))
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--demo", action="store_true")
        parser.add_argument("--target", default="all")
        parser.add_argument("--hypothesis-id", default=None)
        parser.add_argument("--symbol", default="BTCUSDT")
        parser.add_argument("--tf", default="15m")
        parser.add_argument("--max-ticks", type=int, default=None)
        parsed, _ = parser.parse_known_args(args[1:])
    if args and args[0] == "mcp":
        from cli.system import cmd_mcp
        return cmd_mcp(args[1:])

    print("SKY Quantitative Platform / Crypto Brain Terminal (CBT)")
    print("Available entry points:")
    print("  python main.py collective <subcommand>  - SDCC Distributed Collective Core")
    print("  uvicorn app:app --port 8000            - Start FastAPI Master Server")
    return 0


if __name__ == "__main__":
    sys.exit(main())
