"""web/routes_system.py — system/connections/practice/readiness/scorecard routes.

Refactor step 4 (ROADMAP §19): connections, account, unlock, evidence,
modules, state, learn, backtest, sources, diag, health, channels, doctor,
desk, loop-health, weekly, ritual, practice, readiness, scorecard, agents,
mcp, ask and glossary used to live inline inside ``make_app``.  Handler
bodies are semantically identical to the original (exact string match);
``__file__``-relative paths resolve identically from this module.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from flask import Response, g, jsonify, request

from config import MIN_CONFIDENCE, SYMBOL, TIMEFRAME
from data.sample_client import maybe_client
from web import api_v1 as apiv1
from web import jobs as jobsmod
from web.payload import _sanitize_for_json, _source_key_param, _sym, compute_payload


def register(app, ctx):
    _audit = ctx["_audit"]
    job_manager = ctx["job_manager"]
    V1_PREFIX = ctx["V1_PREFIX"]

    @app.get("/api/connections")
    def api_connections():
        """Every real-world link: what it gives you and whether it is live."""
        from brain.connections import probe_all as probe_connections

        try:
            return jsonify(_sanitize_for_json(probe_connections()))
        except Exception as exc:  # never blank the page
            return jsonify(
                {
                    "connections": [],
                    "level": "down",
                    "headline": f"connection probe failed: {type(exc).__name__}: {exc}",
                }
            )

    @app.post("/api/connections/test")
    def api_connections_test():
        """Test one connection on demand (the Test button on each card)."""
        from brain.connections import probe_one

        body = request.get_json(silent=True) or {}
        cid = str(body.get("id") or "").strip()
        try:
            return jsonify(_sanitize_for_json(probe_one(cid)))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

    @app.post("/api/alerts/test")
    def api_alerts_test():
        """Send a real test alert so the user can confirm it reaches them."""
        from output.notifiers import send_test_alert

        body = request.get_json(silent=True) or {}
        try:
            res = send_test_alert(str(body.get("channel") or ""))
            _audit("test_alert", str(body.get("channel") or ""), ok=bool(res.get("ok")))
            return jsonify(res)
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.get("/api/account")
    def api_account():
        """READ-ONLY exchange account snapshot: real balance, real orders.

        Backed by ``data/exchange_account.py``, which signs GET requests
        against a read-only allow-list and has no order-placement path.
        """
        from data.exchange_account import ExchangeAccount

        try:
            return jsonify(_sanitize_for_json(ExchangeAccount().snapshot()))
        except Exception as exc:
            return jsonify(
                {
                    "configured": False,
                    "connected": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "balances": [],
                    "open_orders": [],
                }
            )

    # ── Why blocked / how to unlock ───────────────────────────────────
    @app.get("/api/unlock")
    def api_unlock():
        """Why the gate is closed and exactly what to click to open it."""
        from brain.unlock import explain
        from data.database import SignalDB

        plan_type = request.args.get("plan_type") or None
        symbol = _sym(request.args.get("symbol")) if request.args.get("symbol") else None
        try:
            with SignalDB() as db:
                if plan_type is None:
                    # default to the setup the live scan is currently proposing
                    try:
                        payload = compute_payload(
                            symbol or SYMBOL, TIMEFRAME, save=False, use_cache=True
                        )
                        plans = payload.get("plans") or []
                        plan_type = plans[0].get("type") if plans else None
                    except Exception:
                        plan_type = None
                return jsonify(_sanitize_for_json(explain(db, plan_type=plan_type, symbol=symbol)))
        except Exception as exc:
            return jsonify(
                {
                    "allowed": False,
                    "blocks": [],
                    "headline": "could not evaluate the gate",
                    "summary": f"{type(exc).__name__}: {exc}",
                }
            ), 200

    @app.get("/api/evidence")
    def api_evidence():
        """Progress toward proving every setup — the honest edge scoreboard."""
        from brain.unlock import evidence_overview
        from data.database import SignalDB

        try:
            with SignalDB() as db:
                return jsonify(_sanitize_for_json(evidence_overview(db)))
        except Exception as exc:
            return jsonify(
                {"setups": [], "count": 0, "headline": f"{type(exc).__name__}: {exc}"}
            ), 200

    # ── Module catalog: every module visible ──────────────────────────
    @app.get("/api/modules")
    def api_modules():
        """Every Python module in the engine with its one-line purpose."""
        import ast

        groups = {
            "engine": "Signal engine",
            "brain": "Decision brain",
            "data": "Market data & storage",
            "output": "Output & notifiers",
            "web": "Dashboard",
            "ai": "LLM & MCP",
        }
        root = Path(__file__).resolve().parent.parent
        out = []
        for package, label in groups.items():
            modules = []
            for path in sorted((root / package).rglob("*.py")):
                if path.name == "__init__.py":
                    continue
                doc = ""
                try:
                    doc = (
                        ast.get_docstring(
                            ast.parse(path.read_text(encoding="utf-8", errors="replace"))
                        )
                        or ""
                    )
                except Exception:
                    doc = ""
                rel = str(path.relative_to(root))
                summary = doc.strip().split("\n")[0].strip()
                # Many modules open with "package/file.py — what it does";
                # show only the explanation, never the filename twice.
                if summary.startswith(rel) or summary.startswith(f"{package}/"):
                    for sep in ("—", "-", ":"):
                        if sep in summary:
                            summary = summary.split(sep, 1)[1].strip()
                            break
                    else:
                        summary = ""
                if not summary and len(doc.strip().split("\n")) > 1:
                    summary = next(
                        (ln.strip() for ln in doc.strip().split("\n")[1:] if ln.strip()),
                        "",
                    )
                modules.append(
                    {
                        "name": path.relative_to(root).as_posix(),
                        "module": path.relative_to(root).as_posix().replace("/", ".")[:-3],
                        "summary": summary or "—",
                        "lines": len(
                            path.read_text(encoding="utf-8", errors="replace").splitlines()
                        ),
                    }
                )
            out.append(
                {
                    "package": package,
                    "label": label,
                    "modules": modules,
                    "count": len(modules),
                }
            )
        return jsonify({"packages": out, "count": sum(g["count"] for g in out)})

    @app.get("/api/state")
    @app.get("/api/state")
    def api_state():
        symbol = _sym(request.args.get("symbol", SYMBOL))
        tf = request.args.get("tf", TIMEFRAME)
        from brain.state_memory import SignalMemory

        mem = SignalMemory()
        return jsonify(
            {
                "state": mem.get_state(symbol, tf),
                "events": mem.history(symbol, tf, limit=15),
            }
        )

    @app.post("/api/learn")
    def api_learn():
        """One-click: recompute the calibration profile from stored backtests."""
        from brain.calibrator import learn

        try:
            res = learn()
            _audit("learn", "calibration")
            return jsonify({"ok": True, **res})
        except Exception as exc:  # pragma: no cover
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.post("/api/backtest")
    def api_backtest():
        """One-click: quick backtest on recent bars + auto-learn."""
        body = request.get_json(silent=True) or {}
        symbol = _sym(body.get("symbol", SYMBOL))
        tf = body.get("tf", TIMEFRAME)
        bars = min(int(body.get("bars", 300)), 1000)
        step = int(body.get("step", 3))
        horizons = [float(h) for h in str(body.get("horizons", "1,4,24")).split(",") if h]
        try:
            from brain.calibrator import learn
            from data.backtester import run_backtest
            from data.database import SignalDB

            df = maybe_client().klines(symbol, tf, bars)
            res = run_backtest(
                df,
                symbol=symbol,
                timeframe=tf,
                horizons=horizons,
                step=step,
                min_confidence=MIN_CONFIDENCE,
            )
            run_id = time.strftime("%Y%m%d_%H%M%S")
            rows = []
            for g in res["graded"]:
                r = g.as_row()
                r.update({"run_id": run_id, "symbol": symbol, "timeframe": tf})
                rows.append(r)
            with SignalDB() as db:
                n = db.save_backtest_rows(rows, run_id)
            profile = learn()
            _audit("backtest", f"{symbol}:{tf}", detail={"bars": bars, "saved": n})
            return jsonify(
                _sanitize_for_json(
                    {
                        "ok": True,
                        "saved": n,
                        "report": res["report"],
                        "calibration": profile["profile"],
                    }
                )
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.get("/api/sources")
    def api_sources():
        """Configuration status of optional external connections."""
        from config import (
            CRYPTODADA_BASE_URL,
            DISCORD_ANNOUNCE_WEBHOOK,
            DISCORD_CHANNEL_IDS,
            DISCORD_TOKEN,
            LLM_PROVIDER,
            TELEGRAM_BOT_TOKEN,
            TELEGRAM_CHAT_ID,
        )

        return jsonify(
            {
                "cryptodada": bool(
                    CRYPTODADA_BASE_URL and "YOUR-CRYPTODADA" not in CRYPTODADA_BASE_URL
                ),
                "discord_read": bool(DISCORD_TOKEN and DISCORD_CHANNEL_IDS),
                "discord_webhook": bool(DISCORD_ANNOUNCE_WEBHOOK),
                "telegram": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
                "llm": LLM_PROVIDER != "off",
            }
        )

    @app.get("/api/diag")
    def api_diag():
        """Connectivity check: which external sources are reachable, with
        response times — powers the dashboard 'System check' button."""
        import requests as _req

        from data.binance_client import BINANCE_FUTURES_HOSTS, BINANCE_HOSTS

        out: dict = {}

        def probe(name, fn):
            t0 = time.time()
            try:
                ok = fn()
                out[name] = {"ok": bool(ok), "ms": int((time.time() - t0) * 1000)}
            except Exception as exc:
                out[name] = {
                    "ok": False,
                    "ms": int((time.time() - t0) * 1000),
                    "err": str(exc)[:120],
                }

        def spot():
            r = _req.get(f"{BINANCE_HOSTS[0]}/api/v3/ping", timeout=4)
            return r.status_code == 200

        def fapi():
            r = _req.get(f"{BINANCE_FUTURES_HOSTS[0]}/fapi/v1/ping", timeout=4)
            return r.status_code == 200

        def fng():
            r = _req.get("https://api.alternative.me/fng/?limit=1", timeout=4)
            return r.status_code == 200

        def cg():
            r = _req.get(
                "https://api.coingecko.com/api/v3/global",
                timeout=4,
                headers={"User-Agent": "CryptoBrain/1.0"},
            )
            return r.status_code == 200

        def stooq():
            r = _req.get(
                "https://stooq.com/q/l/?s=^spx&f=sd2t2ohlcv&h&e=csv",
                timeout=4,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            return r.status_code == 200

        def news():
            r = _req.get(
                "https://cointelegraph.com/rss",
                timeout=4,
                headers={"User-Agent": "CryptoBrain/1.0"},
            )
            return r.status_code == 200

        from concurrent.futures import ThreadPoolExecutor

        probes = {
            "binance_spot": spot,
            "binance_futures": fapi,
            "fear_greed": fng,
            "coingecko": cg,
            "stooq_equities": stooq,
            "news_rss": news,
        }
        with ThreadPoolExecutor(max_workers=len(probes)) as ex:
            futs = {ex.submit(probe, n, f): n for n, f in probes.items()}
            for fut in futs:
                fut.result()
        ok_count = sum(1 for v in out.values() if v.get("ok"))
        return jsonify(
            {
                "sources": out,
                "ok_count": ok_count,
                "total": len(out),
                "all_ok": ok_count == len(out),
            }
        )

    @app.get("/api/health")
    def health():
        """Full system health — same report as `python main.py agent health`."""
        try:
            from brain.agent import health_report

            return jsonify(health_report())
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/channels")
    def api_channels():
        """P8 ordered-backend channel registry (Panniantong/Agent-Reach pattern).

        Every external dependency the engine has (data sources + LLM) is a
        *channel* with an ordered list of backend candidates. The first
        backend that is configured and probes clean is the *active* one.
        Channels never block the engine — when nothing is configured, the
        channel reports ``active: "none"`` and the rest of the brain
        continues unaffected. Probes are exception-isolated: a broken
        backend in one channel cannot crash this endpoint.
        """
        try:
            from brain.channels import probe_all

            channels = probe_all()
            return jsonify(
                _sanitize_for_json(
                    {
                        "channels": {n: ch.to_dict() for n, ch in channels.items()},
                    }
                )
            )
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}", "channels": {}})

    @app.get("/api/doctor")
    def api_doctor():
        """Human-readable doctor report — same output as `python main.py doctor`."""
        try:
            from brain.channels import doctor_report

            # doctor_report returns a multi-line string in text mode
            return jsonify({"report": doctor_report(as_json=False)})
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/desk")
    def api_desk():
        """One-call desk advisory — same snapshot as `python main.py desk`."""
        try:
            from brain.agent import desk_status

            return jsonify(_sanitize_for_json(desk_status()))
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/loop-health")
    def api_loop_health():
        """The one daily number — same snapshot as `python main.py daily`."""
        try:
            from brain.agent import loop_health

            payload = loop_health()
            payload["evidence_guidance"] = _jobs.evidence_guidance(
                (payload.get("graduation") or {}).get("by_setup") or []
            )
            return jsonify(_sanitize_for_json(payload))
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/weekly")
    def api_weekly():
        """W3 weekly trader review — the same computation as
        `python main.py weekly`, the MCP ``weekly_review`` tool and the
        ``weekly_review`` desk agent. Read-only over the canonical live
        book, NET of costs; advisory only, never a gate."""
        try:
            from brain.weekly import weekly_review

            days = request.args.get("days", 7)
            days = min(90, max(1, int(days)))
            from data.database import SignalDB

            with SignalDB() as db:
                payload = weekly_review(db, days=days)
            return jsonify(_sanitize_for_json(payload))
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/weekly/export")
    def api_weekly_export():
        """Download the weekly review as a JSON attachment (evidence archive)."""
        try:
            from brain.weekly import weekly_review

            days = request.args.get("days", 7)
            days = min(90, max(1, int(days)))
            from data.database import SignalDB

            with SignalDB() as db:
                payload = weekly_review(db, days=days)
            body = json.dumps(_sanitize_for_json(payload), indent=2, default=str)
            day = time.strftime("%Y-%m-%d", time.gmtime())
            return Response(
                body,
                mimetype="application/json",
                headers={
                    "Content-Disposition": f"attachment; filename=sky-weekly-review-{day}.json"
                },
            )
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/ritual")
    def api_ritual():
        """W3.2 — today's daily-ritual checklist with its persisted ticks."""
        try:
            from brain.ritual import ritual_today
            from data.database import SignalDB

            with SignalDB() as db:
                payload = ritual_today(db)
            return jsonify(_sanitize_for_json(payload))
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.post("/api/ritual")
    def api_ritual_set():
        """W3.2 — tick/untick one canonical ritual step for today.

        Fail-closed on unknown step names (no invented ritual history), and
        audited like every human action. A tick is a memory note, never
        permission and never a threshold."""
        body = request.get_json(silent=True) or {}
        name = str(body.get("step") or body.get("name") or "")
        try:
            done = bool(body.get("done"))
            from brain.ritual import ritual_set
            from data.database import SignalDB

            with SignalDB() as db:
                payload = ritual_set(db, name, done)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        _audit("ritual", name, detail={"done": done, "day": payload.get("day")})
        return jsonify(_sanitize_for_json(payload))

    @app.get("/api/practice")
    def api_practice():
        """W3.4 practice calibration — the same computation as
        `python main.py practice`, the Chart/Review tab cards and the
        read-only MCP ``practice_scorecard`` tool. Coaching memory only:
        agreement with the desk is not evidence, and this payload is never
        read by any gate or graduation surface."""
        try:
            from brain.practice import practice_scorecard
            from data.database import SignalDB

            days = min(365, max(1, int(request.args.get("days", 30))))
            with SignalDB() as db:
                payload = practice_scorecard(db, days=days)
            return jsonify(_sanitize_for_json(payload))
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.post("/api/practice")
    def api_practice_submit():
        """W3.4 — commit one practice read and score it against the desk's
        current read.

        The engine payload is computed with ``save=False``: a practice
        attempt never enters the scans table, the review queue or the live
        book. Fail-closed validation (400) before the desk read is computed;
        if the engine itself cannot produce a read, nothing is recorded
        (502) — an unscored attempt would corrupt the calibration history.
        """
        body = request.get_json(silent=True) or {}
        from brain.practice import (
            desk_read_from_payload,
            submit_attempt,
            validate_user_read,
        )

        try:
            user = validate_user_read(body)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        try:
            payload = compute_payload(user["symbol"], user["tf"], save=False, use_cache=True)
        except Exception as exc:
            return jsonify(
                {
                    "ok": False,
                    "error": f"desk read unavailable — attempt not recorded: "
                    f"{type(exc).__name__}: {exc}",
                }
            ), 502
        try:
            desk = desk_read_from_payload(payload, user["symbol"], user["tf"])
            from data.database import SignalDB

            with SignalDB() as db:
                result = submit_attempt(db, user, desk)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        _audit(
            "practice",
            f"{user['symbol']} {user['tf']}",
            detail={
                "score": result["score"]["total"],
                "grade": result["score"]["grade"],
                "duplicate": bool(result.get("duplicate")),
            },
        )
        return jsonify(_sanitize_for_json(result))

    @app.post("/api/practice/tape")
    def api_practice_tape():
        """W3.6 — commit one practice read against the hidden replay window.

        The server fetches the same candle series the chart draws and walks
        the bars *after* ``commit_time``. The client cannot supply the
        future. Fail-closed validation (400) before any row is written.
        Never writes scans or paper_trades — coaching memory only.
        """
        body = request.get_json(silent=True) or {}
        from brain.practice import load_ohlc, submit_tape_attempt, validate_tape_request

        try:
            user, _commit_ms, _horizon = validate_tape_request(body)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        try:
            candles = load_ohlc(user["symbol"], user["tf"])
        except Exception as exc:
            return jsonify(
                {
                    "ok": False,
                    "error": "tape candles unavailable — attempt not "
                    f"recorded: {type(exc).__name__}: {exc}",
                }
            ), 502
        try:
            from data.database import SignalDB

            with SignalDB() as db:
                result = submit_tape_attempt(db, body, candles)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        _audit(
            "practice_tape",
            f"{user['symbol']} {user['tf']}",
            detail={
                "score": result["score"]["total"],
                "grade": result["score"]["grade"],
                "outcome": result["score"].get("outcome"),
                "duplicate": bool(result.get("duplicate")),
            },
        )
        return jsonify(_sanitize_for_json(result))

    @app.get("/api/readiness")
    def api_readiness():
        """Combined readiness strip: channels + immune + risk gate + data quality.

        The one verdict the dashboard shows above every tab (TODO-1.bis +
        P10.5).
        Same payload as `python main.py doctor --strip --json` and the MCP
        ``readiness`` tool — no surface computes its own verdict.
        """
        try:
            from brain.agent import readiness_strip

            return jsonify(_sanitize_for_json(readiness_strip()))
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify(
                {
                    "ok": False,
                    "level": "down",
                    "headline": "readiness unavailable",
                    "pillars": [],
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    @app.get("/api/scorecard")
    def api_scorecard():
        """P12.3 & P12.6 strategy scorecard — the same block as `python main.py
        scorecard --json` and the MCP ``scorecard`` tool.

        Read-only report over outcomes the grader already produced; no
        surface re-grades anything or computes its own verdict. Evaluated
        NET of costs (P12.6).
        """
        try:
            from data.costs import CostModel
            from data.scorecard import scorecard_from_db

            src = request.args.get("source", "db")
            sym = request.args.get("symbol") or None
            no_costs = request.args.get("no_costs", "").lower() in ("1", "true", "yes")
            conditioned = request.args.get("conditioned", "").lower() in (
                "1",
                "true",
                "yes",
            )
            quality = request.args.get("quality", "").lower() in ("1", "true", "yes")
            since = request.args.get("since")
            until = request.args.get("until")
            since_ts = int(since) if since and since.isdigit() else None
            until_ts = int(until) if until and until.isdigit() else None
            cost_model = CostModel(enabled=not no_costs)
            # P12.11 — ?source_key=live | exchange:market[:bid|ask] | all
            source_key = _source_key_param(request.args.get("source_key"))
            return jsonify(
                _sanitize_for_json(
                    scorecard_from_db(
                        symbol=_sym(sym) if sym else None,
                        source="all" if src == "db" else src,
                        min_decided=int(request.args.get("min_decided", 30)),
                        include_sim=request.args.get("include_sim", "1") != "0",
                        since_ts=since_ts,
                        until_ts=until_ts,
                        cost_model=cost_model,
                        conditioned=conditioned,
                        quality=quality,
                        source_key=source_key,
                    )
                )
            )
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/agents")
    def api_agents():
        """Desk morning briefing: watchlist + gate + queue + narrative."""
        try:
            from brain.agent import morning_briefing

            return jsonify(morning_briefing(timeframe=request.args.get("tf", TIMEFRAME)))
        except Exception as exc:  # never 500 — degrade gracefully
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.get("/api/mcp")
    def api_mcp():
        """MCP server status + tool inventory for the dashboard card."""
        try:
            from ai.mcp_server import TOOLS

            try:
                import mcp  # noqa: F401

                available = True
                note = "run `python main.py mcp` and point Claude Desktop / Cursor at it"
            except Exception:
                available = False
                note = "mcp package not installed — pip install mcp"
            return jsonify(
                {
                    "available": available,
                    "note": note,
                    "count": len(TOOLS),
                    "tools": [t["name"] for t in TOOLS],
                }
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    @app.post("/api/ask")
    def api_ask():
        """Natural-language question to the desk (intent-based, offline-capable)."""
        body = request.get_json(silent=True) or {}
        question = str(body.get("question", "")).strip()
        if not question:
            return jsonify({"ok": False, "error": "empty question"}), 400
        try:
            from brain.agent import ask

            return jsonify(
                ask(
                    question,
                    symbol=_sym(body.get("symbol")),
                    timeframe=body.get("tf", TIMEFRAME),
                )
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.get("/api/glossary")
    def api_glossary():
        """Glossary lookup for the dashboard coach card."""
        term = (request.args.get("term") or "").strip()
        if not term:
            return jsonify({"found": False, "error": "no term"}), 400
        try:
            from brain.coach import GLOSSARY

            key = next((k for k in GLOSSARY if k.lower() == term.lower()), None)
            if key is None:
                key = next(
                    (k for k in GLOSSARY if term.lower() in k.lower() or k.lower() in term.lower()),
                    None,
                )
            if key is None:
                return jsonify({"found": False, "term": term, "error": "term not found"}), 404
            meaning, why = GLOSSARY[key]
            return jsonify({"found": True, "term": key, "meaning": meaning, "why": why})
        except Exception as exc:
            return jsonify({"found": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    # ══════════════════════════════════════════════════════════════════════
    # P18.2 — /api/v1: one envelope, typed errors, versioning, idempotency
    #
    # Every delegating route calls the *same* legacy view function the
    # dashboard calls and re-renders its answer in the v1 envelope. v1 is a
    # contract over existing behaviour, never a second implementation: it
    # cannot approve something the legacy path refuses, and it adds no
    # exchange-order path (SKY has none).
    # ══════════════════════════════════════════════════════════════════════
    _idem = apiv1.IdempotencyStore()
    # P18.3 — the persisted background-job queue. One worker, one job at a
    # time; long commands (backfill/backtest/simulator/evidence) run here so
    # a browser close or a timeout cannot kill them. Tests inject a manager
    # with a fake runner so no real subprocess spawns.
    _jobs = job_manager or jobsmod.JobManager()
    # Start the worker at boot so orphaned rows from a previous process are
    # adopted immediately and queued jobs resume without waiting for a new
    # submission. Idempotent — a manager injected by a test may already run.
    _jobs.start()

    def _unwrap(rv) -> tuple[Any, int]:
        """Normalize a Flask return value into ``(json_payload, status)``.

        Subtlety worth keeping: legacy handlers return ``jsonify(...), 400``.
        The ``jsonify`` Response carries the *default* 200 — the real status
        lives in the tuple. Preferring the response's ``status_code`` here
        silently turned every legacy 4xx into a 200-shaped INTERNAL error, so
        the tuple's status must win when present.
        """
        status = None
        if isinstance(rv, tuple):
            if len(rv) >= 2 and isinstance(rv[1], int):
                status = rv[1]
            rv = rv[0]
        if hasattr(rv, "get_json"):
            try:
                payload = rv.get_json(silent=True)
            except Exception:
                payload = None
            if status is None:
                status = getattr(rv, "status_code", 200) or 200
            return payload, status
        return rv, (status if status is not None else 200)

    def _as_v1(payload: Any, status: int, request_id: str):
        """Render a legacy handler's answer in the v1 envelope.

        Legacy endpoints are inconsistent by history: some return a bare
        payload, some ``{ok: false, error: ...}`` with HTTP 200, some a real
        4xx/5xx. A v1 client must not have to know which — so failure is
        decided here, once, and always surfaces as a typed code.
        """
        body = payload if isinstance(payload, dict) else None

        failed = status >= 400 or (body is not None and body.get("ok") is False)
        # A handler that returns 200 with a bare {"error": "..."} and nothing
        # else is also a failure; but a rich payload that merely *contains* an
        # "error" field alongside real data is not.
        if (
            not failed
            and body is not None
            and body.get("error")
            and set(body.keys()) <= {"error", "code", "ok", "detail", "details"}
        ):
            failed = True

        if not failed:
            data = body if body is not None else payload
            if isinstance(data, dict) and "ok" in data:
                data = {k: v for k, v in data.items() if k != "ok"}
            return jsonify(apiv1.envelope_ok(data, request_id)), status

        message = "request failed"
        code = None
        details: dict = {}
        if body is not None:
            message = body.get("error") or body.get("message") or body.get("detail") or message
            code = body.get("code")
            details = {k: v for k, v in body.items() if k not in ("ok", "error", "code", "message")}
        # The desk's deliberate refusals deserve their own codes so a client
        # can render "the risk gate is closed" instead of a generic failure.
        if code is None:
            if isinstance(body, dict) and "blocked_by" in body:
                # The desk refusing on risk is not a malformed request; a
                # client should render the gate reasons, not "bad input".
                code = apiv1.ErrorCode.RISK_GATE_CLOSED
            elif status == 400 and "cannot go " in str(message):
                # engine/lifecycle.py rejecting an illegal state transition —
                # the usual cause is a retried decision, so name it precisely.
                code = apiv1.ErrorCode.LIFECYCLE_INVALID
            else:
                code = apiv1.code_for_status(status)
        if status < 400:
            status = 500 if code == apiv1.ErrorCode.INTERNAL else 400
        return jsonify(apiv1.envelope_error(code, message, details, request_id)), status

    def _delegate(legacy_path: str, method: str):
        """Invoke the legacy view function registered for ``legacy_path``."""
        for rule in app.url_map.iter_rules():
            if str(rule.rule) == legacy_path and method in (rule.methods or set()):
                return app.view_functions[rule.endpoint]()
        raise KeyError(f"no legacy handler for {method} {legacy_path}")

    def _make_v1_view(route: dict):
        legacy_path = route["legacy"]
        method = route["method"]
        sub = route["path"]
        idempotent = bool(route.get("idempotent"))

        def view():
            request_id = apiv1.new_request_id()
            user = getattr(g, "user", None)
            user_id = (user or {}).get("id")

            key = None
            fingerprint = ""
            if idempotent:
                try:
                    key = apiv1.validate_key(request.headers.get(apiv1.IDEMPOTENCY_HEADER))
                except ValueError as exc:
                    return jsonify(
                        apiv1.envelope_error(
                            apiv1.ErrorCode.BAD_REQUEST, str(exc), request_id=request_id
                        )
                    ), 400
            if key:
                body = request.get_json(silent=True) or {}
                fingerprint = apiv1.request_fingerprint(sub, body)
                try:
                    state, cached = _idem.lookup(key, user_id, sub, fingerprint)
                except Exception:
                    state, cached = ("miss", None)  # never fail on the cache
                if state == "replay":
                    status, stored = cached
                    if isinstance(stored, dict):
                        stored = dict(stored)
                        stored["meta"] = dict(stored.get("meta") or {})
                        stored["meta"]["idempotent_replay"] = True
                        stored["meta"]["request_id"] = request_id
                    return jsonify(stored), status
                if state == "conflict":
                    return jsonify(
                        apiv1.envelope_error(
                            apiv1.ErrorCode.IDEMPOTENCY_KEY_REUSED,
                            "This Idempotency-Key was already used for a different "
                            "request. Generate a new key per distinct action.",
                            {"key": key, "endpoint": sub},
                            request_id=request_id,
                        )
                    ), 409
                if state == "in_progress":
                    return jsonify(
                        apiv1.envelope_error(
                            apiv1.ErrorCode.IDEMPOTENCY_IN_PROGRESS,
                            "An identical request is still being processed. Retry shortly.",
                            {"key": key},
                            request_id=request_id,
                        )
                    ), 409
                try:
                    if not _idem.reserve(key, user_id, sub, fingerprint):
                        return jsonify(
                            apiv1.envelope_error(
                                apiv1.ErrorCode.IDEMPOTENCY_IN_PROGRESS,
                                "An identical request is still being processed. Retry shortly.",
                                {"key": key},
                                request_id=request_id,
                            )
                        ), 409
                except Exception:
                    key = None  # cache unavailable → execute without replay

            try:
                payload, status = _unwrap(_delegate(legacy_path, method))
            except Exception as exc:
                if key:
                    try:
                        _idem.release(key, user_id, sub)
                    except Exception:
                        pass
                return jsonify(
                    apiv1.envelope_error(
                        apiv1.ErrorCode.INTERNAL,
                        f"{type(exc).__name__}: {exc}",
                        request_id=request_id,
                    )
                ), 500

            response = _as_v1(payload, status, request_id)
            if key:
                rendered, rendered_status = response
                try:
                    stored = rendered.get_json(silent=True)
                    if stored is not None:
                        _idem.complete(key, user_id, sub, rendered_status, stored)
                    else:
                        _idem.release(key, user_id, sub)
                except Exception:
                    pass
            return response

        view.__name__ = f"v1_{method.lower()}_{sub.strip('/').replace('/', '_') or 'root'}"
        return view

    for _route in apiv1.ROUTES:
        app.add_url_rule(
            f"{V1_PREFIX}{_route['path']}",
            endpoint=f"v1_{_route['method'].lower()}_{_route['path'].strip('/').replace('/', '_')}",
            view_func=_make_v1_view(_route),
            methods=[_route["method"]],
        )
    return _jobs
