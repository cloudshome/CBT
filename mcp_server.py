#!/usr/bin/env python3
"""mcp_server.py — Minimal, dependency-free Model Context Protocol (MCP) server.

Implements JSON-RPC 2.0 over stdio for LLM integration (Claude Desktop, Cursor,
Arena, and MCP clients). Exposes grounded trading tools while strictly enforcing
a read-only permission map (no automatic order placement or gate bypass).

TOOL PERMISSION MAP (single source of truth — see ALLOWED_TOOLS below).
Read-only / research tools only. Mutation paths (approve | reject | execute |
close | place_order | sign | withdraw | transfer) are NEVER in this map and
MUST NOT be added — the engine physically cannot be asked to trade. The
human-approval gate is the only path to action and lives in `brain/risk_gate.py`.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brain.analytics import monte_carlo_ruin_table
from brain.ask import ask
from brain.brief import generate_morning_brief, post_trade_review
from brain.risk_gate import evaluate_risk_gate
from data.database import SignalDB
from data.symbols import normalize_symbol

SERVER_NAME = "cryptobrain-mcp"
SERVER_VERSION = "1.14.0"  # bumped: W3.6 tape block on practice_scorecard
PROTOCOL_VERSION = "2024-11-05"

# Read-only / research tools allowed. No order or approval bypass tools.
#
# Test contract: tests/test_mcp_stdio.py:ROOT_TOOLS is the canonical assertion
# of this set. If you add/remove a tool here, update ROOT_TOOLS too.
ALLOWED_TOOLS = {
    "ask": {
        "description": "Query grounded trading knowledge, setup expectancies, and playbooks with source citations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Question to answer (e.g. 'which setups have positive expectancy in ranging markets?')",
                }
            },
            "required": ["query"],
        },
    },
    "tradestate": {
        "description": "View or update behavioral trader flags (angry, tired, revenge, chasing).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["get", "set", "clear"],
                    "default": "get",
                },
                "angry": {"type": "boolean"},
                "tired": {"type": "boolean"},
                "revenge": {"type": "boolean"},
                "chasing": {"type": "boolean"},
                "note": {"type": "string"},
            },
        },
    },
    "risk": {
        "description": "Get current risk gate status, daily/weekly loss limits, and progression ladder.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    "health": {
        "description": "Run immune system health diagnostics and data freshness checks.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    "brief": {
        "description": "Generate cross-asset morning briefing across BTC, ETH, and GOLD.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of symbols to brief",
                }
            },
        },
    },
    "postreview": {
        "description": "Generate post-trade review and MAE/MFE analytics for a scan ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scan_id": {
                    "type": "integer",
                    "description": "Database scan ID to review",
                }
            },
            "required": ["scan_id"],
        },
    },
    # ── P9: Capability endpoints (TODO-2). Same data as `python main.py` ──
    # All five are read-only wrappers around existing brain/engine library
    # functions. The dashboard, CLI, and MCP surface all read from the same
    # source-of-truth functions — no drift between surfaces.
    "channels": {
        "description": "Ordered-backend channel registry: per-source (cryptodada / discord / news / llm) active backend and probe status. Panniantong/Agent-Reach pattern. Read-only.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    "correlation": {
        "description": "Measured BTC/ETH/GOLD rolling correlation matrix + ETH/BTC beta. Read-only analytics — the same as `python main.py correlation --json`.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Watchlist (default BTCUSDT,ETHUSDT,XAUUSD)",
                },
                "timeframe": {
                    "type": "string",
                    "default": "1h",
                    "description": "Candle timeframe",
                },
                "bars": {
                    "type": "integer",
                    "default": 300,
                    "description": "History length (max 1000)",
                },
                "window": {
                    "type": "integer",
                    "default": 60,
                    "description": "Rolling window of aligned returns",
                },
            },
        },
    },
    "scorecard": {
        "description": "P12.3 & P12.6 & P12.3.3 & P12.4 strategy scorecard: boxed block of gross and NET expectancy R (E_net = E_gross − fees − slip − funding), win rate, profit factor, Sharpe/Sortino/Calmar, max drawdown, cost breakdown, holding time, effective sample size (N_eff, overlap-corrected with widened 95% confidence intervals), split by side (long/short), regime, session, setup, and market conditions — over outcomes the grader already produced. Pass quality=true to embed the P12.4 Backtest Quality Score 0–100 (edge, curve robustness, sample confidence; plateau n/a without the store re-grade sweep). Read-only; the same as `python main.py scorecard --json`. Evaluates performance NET of costs; never grants permission to trade.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "enum": ["db", "backtest", "paper"],
                    "default": "db",
                    "description": "db = stored backtest + paper outcomes combined; or one book alone",
                },
                "symbol": {
                    "type": "string",
                    "description": "Optional asset filter (BTCUSDT, ETHUSDT, XAUUSD)",
                },
                "min_decided": {
                    "type": "integer",
                    "default": 30,
                    "description": "Minimum decided trades before a verdict is given",
                },
                "exclude_sim": {
                    "type": "boolean",
                    "default": False,
                    "description": "Drop simulator walk-forward samples (real paper book only)",
                },
                "no_costs": {
                    "type": "boolean",
                    "default": False,
                    "description": "Disable cost modeling (evaluate gross only)",
                },
                "conditioned": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include conditioned splits by funding and CVD order flow",
                },
                "source_key": {
                    "type": "string",
                    "description": "P12.11 price-series filter: 'live' (canonical Binance spot), 'exchange:market[:bid|ask]' e.g. 'dukascopy:spot:bid', or 'all' (default) to pool every source. The report always names the sources it mixed and flags one-sided (bid/ask-only) series as research-only.",
                },
            },
        },
    },
    "hidden_chart_read": {
        "description": "HMM latent regime + CVD order flow + Bayesian Kelly advisory for a single symbol. Read-only; the same as `python main.py hidden chart_read <SYMBOL>`. Not auto-executed — advisory only.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "default": "BTCUSDT",
                    "description": "Asset (aliases: BTC, ETH, XAU/GOLD)",
                },
                "timeframe": {"type": "string", "default": "15m"},
                "bars": {
                    "type": "integer",
                    "default": 500,
                    "description": "History length",
                },
            },
        },
    },
    "hidden_analytics_mae": {
        "description": "MAE/MFE summary per setup from the paper-trade DB. Read-only; the same as `python main.py hidden analytics mae`. Surfaces where stops are too tight or targets unreachable.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "plan_type": {
                    "type": "string",
                    "description": "Optional plan-type filter (e.g. 'Buy Pullback')",
                },
            },
        },
    },
    "hidden_analytics_mc": {
        "description": "Monte Carlo resampling of realized paper outcomes (terminal equity + drawdown distribution). Read-only; the same as `python main.py hidden analytics mc`. Advisory only — does not place orders.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "samples": {
                    "type": "integer",
                    "default": 2000,
                    "description": "Number of Monte Carlo samples",
                },
                "seed": {
                    "type": "integer",
                    "description": "Optional RNG seed for reproducible runs",
                },
            },
        },
    },
    # ── P9: desk_status advisory (TODO-4) ────────────────────────────
    "desk_status": {
        "description": "One-call desk advisory: risk-gate open/closed, today's P&L, graduation verdict, next scheduled agent, and 'what would a professional do right now?'. Read-only; the same as `python main.py desk`. Never places an order.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    # ── P9: combined readiness strip (TODO-1.bis) ────────────────────
    "readiness": {
        "description": "Combined readiness verdict across four pillars — source channels, immune system, the risk gate, and stored market-data quality — rolled up worst-first to ok/degraded/blocked/down. Read-only; the same as `python main.py doctor --strip --json` and GET /api/readiness. Ask this first to know whether the desk can be trusted right now.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    # ── P14: the one daily number (operate the paper→graduation loop) ──
    "loop_health": {
        "description": "The one number a trader should open daily: how many real/canonical paper trades, net expectancy, per-setup progress, and whether the graduation bar is moving. Composes desk_status + readiness + paper_progress. Read-only; the same as `python main.py daily --json` and GET /api/loop-health. Never places an order.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    # ── W3: the weekly trader review ────────────────────────────────────
    "weekly_review": {
        "description": "W3 weekly trader review: this week vs all time on the canonical live paper book (net of costs), R-multiple distribution, rule violations + repeating mistakes, per-setup graduation tracker with the exact missing evidence, one next practice task and an advisory grade. Read-only; the same as `python main.py weekly --json`, GET /api/weekly, the dashboard Review tab and the weekly_review desk agent. Advisory only — the unchanged graduation bar remains the only gate.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "default": 7,
                    "description": "Review window in days (1-90, default 7)",
                },
            },
        },
    },
    # ── W3.4: practice calibration (your reads vs the desk) ─────────────
    "practice_scorecard": {
        "description": "W3.4+W3.6 practice calibration: desk-agreement (bias/call/ladder) plus a sibling tape block of replay outcomes. Desk keys stay desk-only so tape history cannot rewrite agreement. Coaching memory only: not evidence, feeds no gate. Read-only; same as `python main.py practice --json`, GET /api/practice and the Review-tab PRACTICE CALIBRATION card.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "default": 30,
                    "description": "Window in days (1-365, default 30)",
                },
            },
        },
    },
    # ── 24/7 SKY Intelligence Agent — research & monitoring (read-only) ──
    "sky_agent_status": {
        "description": "24/7 SKY Intelligence Agent status: recent hypotheses, intelligence reports, market regime log and SEC events. Read-only; same as `python main.py sky-agent status --json`. Never trades, never bypasses risk gate.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    "sky_agent_report": {
        "description": "Daily intelligence report builder (Market / Regime / Strategies / Research / Risk / Recommendations). Only evidence-backed suggestions; never BUY NOW. Read-only; same as `python main.py sky-agent report --json`.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "demo": {
                    "type": "boolean",
                    "default": False,
                    "description": "Use deterministic demo data (offline)",
                },
            },
        },
    },
    "sky_agent_health": {
        "description": "Combined 24/7 agent health: readiness strip + system probe (CPU/RAM/disk/DB) + agent liveness. Read-only; same as `python main.py sky-agent health --json`.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    "sky_agent_hypotheses": {
        "description": "List and optionally backtest trading hypotheses (e.g. H-001 Buy Pullback when 4H bullish + 1H bullish). Proposing is free; testing runs SKY's deterministic backtester on the stored Parquet series and returns baseline vs filtered metrics (N, expectancy R, PF, DD). Hypothesis remains unproven until it clears the graduation bar net of costs. Read-only; same as `python main.py sky-agent hypothesize --json`.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hypothesis_id": {
                    "type": "string",
                    "description": "Optional: which hypothesis to backtest (e.g. H-001). Omit to just list.",
                },
                "symbol": {"type": "string", "default": "BTCUSDT"},
                "timeframe": {"type": "string", "default": "15m"},
            },
        },
    },
}


def handle_tool_call(name: str, args: dict[str, Any]) -> dict:
    if name not in ALLOWED_TOOLS:
        raise ValueError(
            f"Tool '{name}' is not permitted or does not exist. (Permission map enforced: read-only tools only)"
        )

    if name == "ask":
        query = args.get("query", "")
        res = ask(query)
        return res

    elif name == "tradestate":
        action = args.get("action", "get")
        with SignalDB() as db:
            if action == "clear":
                db.set_trader_state(
                    angry=False,
                    tired=False,
                    revenge=False,
                    chasing=False,
                    note="cleared via MCP",
                )
            elif action == "set":
                db.set_trader_state(
                    angry=args.get("angry"),
                    tired=args.get("tired"),
                    revenge=args.get("revenge"),
                    chasing=args.get("chasing"),
                    note=args.get("note", "updated via MCP"),
                )
            return db.get_trader_state()

    elif name == "risk":
        with SignalDB() as db:
            gate = evaluate_risk_gate(db)
            gate["ruin_table"] = monte_carlo_ruin_table(db)
            return gate

    elif name == "health":
        from brain.immune import run_health_check

        return run_health_check()

    elif name == "brief":
        syms = args.get("symbols")
        return generate_morning_brief(symbols=syms)

    elif name == "postreview":
        scan_id = int(args.get("scan_id", 0))
        return post_trade_review(scan_id)

    # ── P9 capability endpoints (TODO-2) — read-only wrappers ─────────
    elif name == "channels":
        # Ordered-backend channel registry. Same data as /api/channels
        # and `python main.py channels --json`. Probe-isolated by
        # brain.channels.probe_all().
        from brain.channels import list_channels

        return list_channels(as_json=True)

    elif name == "correlation":
        # Measured cross-asset correlation + ETH/BTC beta. Read-only.
        from data.sample_client import maybe_client
        from engine.correlation import fetch_report

        client = maybe_client()
        syms = args.get("symbols")
        symbols = tuple(syms) if isinstance(syms, list) and syms else None
        return fetch_report(
            client,
            symbols=symbols,
            timeframe=args.get("timeframe", "1h"),
            bars=min(int(args.get("bars", 300)), 1000),
            window=int(args.get("window", 60)),
        )

    elif name == "scorecard":
        # P12.3 & P12.6 boxed scorecard over ALREADY-graded outcomes. Read-only: it
        # re-reads the store, never re-grades and never places anything.
        from data.costs import CostModel
        from data.scorecard import scorecard_from_db

        src = args.get("source", "db")
        cost_model = CostModel(enabled=not bool(args.get("no_costs", False)))
        # P12.11 — an explicit price-series filter; default pools and reports.
        raw_key = args.get("source_key")
        source_key = None
        if raw_key is not None:
            text = str(raw_key).strip().lower()
            if text not in ("", "all", "any", "*"):
                from data.provenance import (
                    LIVE_SOURCE_KEY,
                    parse_source_key,
                )
                from data.provenance import (
                    source_key as _mk_source_key,
                )

                source_key = (
                    LIVE_SOURCE_KEY
                    if text in ("live", "canonical", "binance", "default")
                    else _mk_source_key(*parse_source_key(text))
                )
        return scorecard_from_db(
            symbol=normalize_symbol(args["symbol"]) if args.get("symbol") else None,
            source="all" if src == "db" else src,
            min_decided=int(args.get("min_decided", 30)),
            include_sim=not bool(args.get("exclude_sim", False)),
            cost_model=cost_model,
            conditioned=bool(args.get("conditioned", False)),
            quality=bool(args.get("quality", False)),
            source_key=source_key,
        )

    elif name == "hidden_chart_read":
        # HMM regime + CVD + Kelly advisory for one symbol. Read-only.
        from data.sample_client import maybe_client
        from engine.hidden_alpha import hidden_alpha_report

        sym = normalize_symbol(args.get("symbol", "BTCUSDT"))
        tf = args.get("timeframe", "15m")
        bars = min(int(args.get("bars", 500)), 1000)
        client = maybe_client()
        df = client.klines(sym, tf, bars)
        return hidden_alpha_report(df, sym, tf)

    elif name == "hidden_analytics_mae":
        # MAE/MFE summary from the paper-trade DB. Read-only.
        from brain.analytics import mae_mfe_summary

        plan_type = args.get("plan_type")
        with SignalDB() as db:
            return mae_mfe_summary(db, plan_type=plan_type)

    elif name == "hidden_analytics_mc":
        # Monte Carlo equity / drawdown distribution. Read-only.
        from brain.analytics import monte_carlo_equity

        samples = min(int(args.get("samples", 2000)), 20000)
        seed = args.get("seed")
        with SignalDB() as db:
            return monte_carlo_equity(
                db, samples=samples, seed=int(seed) if seed is not None else None
            )

    elif name == "desk_status":
        from brain.agent import desk_status

        return desk_status()

    elif name == "readiness":
        # Combined channels + immune + risk-gate + data-quality verdict. Read-only;
        # every pillar is exception-isolated inside readiness_strip().
        from brain.agent import readiness_strip

        return readiness_strip()

    elif name == "loop_health":
        # P14 daily ritual. Composes desk_status + readiness + paper_progress.
        from brain.agent import loop_health

        return loop_health()

    elif name == "weekly_review":
        # W3 weekly trader review. Canonical live book only, NET of costs.
        from brain.weekly import weekly_review

        days = min(90, max(1, int(args.get("days", 7))))
        with SignalDB() as db:
            return weekly_review(db, days=days)

    elif name == "practice_scorecard":
        # W3.4 practice calibration. Coaching memory only — feeds no gate.
        from brain.practice import practice_scorecard

        days = min(365, max(1, int(args.get("days", 30))))
        with SignalDB() as db:
            return practice_scorecard(db, days=days)

    elif name == "sky_agent_status":
        from sky_agent.memory import ensure_memory_schema

        with SignalDB() as db:
            ensure_memory_schema(db)
            hyps = [
                dict(r)
                for r in db.conn.execute(
                    "SELECT hypothesis_id,setup,status,created_ts FROM research_hypotheses ORDER BY created_ts DESC LIMIT 20"
                ).fetchall()
            ]
            reports = [
                dict(r)
                for r in db.conn.execute(
                    "SELECT report_date,kind,asset,recommendation,level,created_ts FROM intelligence_reports ORDER BY created_ts DESC LIMIT 10"
                ).fetchall()
            ]
            regimes = [
                dict(r)
                for r in db.conn.execute(
                    "SELECT symbol,timeframe,regime,volatility_state,ts FROM market_regime_log ORDER BY ts DESC LIMIT 10"
                ).fetchall()
            ]
            filings = [
                dict(r)
                for r in db.conn.execute(
                    "SELECT accession,event_type,severity FROM sec_events ORDER BY created_ts DESC LIMIT 10"
                ).fetchall()
            ]
        return {
            "hypotheses": hyps,
            "reports": reports,
            "regimes": regimes,
            "sec_events": filings,
        }

    elif name == "sky_agent_report":
        from sky_agent.daily_report import build_daily_report

        demo = bool(args.get("demo", False))
        return build_daily_report(demo=demo)

    elif name == "sky_agent_health":
        from brain.agent import readiness_strip
        from sky_agent.monitor_system import probe_system

        try:
            strip = readiness_strip()
        except Exception as exc:
            strip = {"error": str(exc)}
        return {"readiness": strip, "system": probe_system(), "agent": "sky_agent"}

    elif name == "sky_agent_hypotheses":
        from sky_agent.hypothesis import propose_hypotheses, run_hypothesis_backtest

        hyps = propose_hypotheses()
        out: dict[str, Any] = {"hypotheses": hyps}
        hid = args.get("hypothesis_id")
        if hid:
            out["backtest"] = run_hypothesis_backtest(
                str(hid),
                symbol=str(args.get("symbol", "BTCUSDT")),
                timeframe=str(args.get("timeframe", "15m")),
            )
        return out

    raise ValueError(f"Unhandled tool: {name}")


def process_message(msg: dict) -> dict | None:
    msg_id = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {},
                },
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
            },
        }

    elif method == "notifications/initialized":
        return None

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    elif method == "tools/list":
        tools_out = []
        for name, spec in ALLOWED_TOOLS.items():
            tools_out.append(
                {
                    "name": name,
                    "description": spec["description"],
                    "inputSchema": spec["inputSchema"],
                }
            )
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools_out}}

    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments") or {}
        try:
            res_data = handle_tool_call(tool_name, tool_args)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(res_data, indent=2, default=str),
                        }
                    ]
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32000,
                    "message": str(exc),
                },
            }

    else:
        if msg_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            }
        return None


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            resp = process_message(msg)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
