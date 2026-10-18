"""web/routes_paper.py — paper/review/risk/monte/trader-state/history/signal/learning/coach routes.

Refactor step 4 (ROADMAP §19): these handlers used to live inline inside
``make_app``; they live here now.  ``register(app, ctx)`` unpacks the one
make_app closure they need (``_audit``); everything else is imported
directly.  Handler bodies are semantically identical to the original
(verified by exact string match).
"""

from __future__ import annotations

import json

from flask import g, jsonify, request

import config
from config import SYMBOL, TIMEFRAME
from data.sample_client import maybe_client
from web.payload import _sym, compute_payload


def register(app, ctx):
    _audit = ctx["_audit"]

    @app.get("/api/paper")
    def api_paper():
        """Paper-monitor dashboard state. Read-only; does not start a runner."""
        symbol = _sym(request.args.get("symbol")) if request.args.get("symbol") else None
        from data.database import SignalDB

        with SignalDB() as db:
            return jsonify({"stats": db.paper_trade_stats(symbol)})

    @app.post("/api/paper/run")
    def api_paper_run():
        """One explicit, safe runner pass for the dashboard button.

        Continuous unattended monitoring belongs to ``python main.py paper
        --watch`` so it survives a browser tab closing.  This endpoint never
        sends an order to an exchange.
        """
        body = request.get_json(silent=True) or {}
        symbol = _sym(body.get("symbol")) if body.get("symbol") else None
        try:
            from data.database import SignalDB
            from data.paper_trading import PaperTradingRunner

            with SignalDB() as db:
                run = (
                    PaperTradingRunner(db=db, client=maybe_client())
                    .run_once(symbol=symbol)
                    .as_dict()
                )
            _audit(
                "paper_run",
                symbol or "all",
                detail={
                    "checked": run.get("checked"),
                    "opened": run.get("opened"),
                    "closed": run.get("closed"),
                },
            )
            return jsonify({"ok": True, "run": run})
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.post("/api/review")
    def api_review():
        body = request.get_json(silent=True) or {}
        scan_id = body.get("scan_id")
        decision = (body.get("decision") or "").upper()
        note = body.get("note", "")
        force = bool(body.get("force"))
        reviewer = (getattr(g, "user", None) or {}).get("username") or "dashboard"
        if decision not in ("APPROVED", "REJECTED", "EXECUTED", "CLOSED", "SKIPPED"):
            return jsonify({"error": f"bad decision {decision}"}), 400
        from brain.risk_gate import evaluate as gate_evaluate
        from data.database import SignalDB
        from data.paper_trading import _primary_plan
        from engine.lifecycle import LifecycleError

        with SignalDB() as db:
            # Enforced risk & discipline gate (decisions B6/B7/B9/B10).
            if decision == "APPROVED" and not force:
                scan = db.get_scan(int(scan_id)) if str(scan_id).isdigit() else None
                if scan is None:
                    return jsonify({"error": f"scan #{scan_id} not found"}), 404
                plan_type = _primary_plan(scan).get("type")
                gate = gate_evaluate(
                    db,
                    symbol=scan.get("symbol"),
                    plan_type=plan_type,
                    action=scan.get("action"),
                )
                if not gate["allowed"]:
                    # P18.1: an operator cannot bypass the risk gate. The legacy
                    # force-approve escape hatch is disabled unless explicitly
                    # opted into, and always audited.
                    return jsonify(
                        {
                            "error": "Risk gate CLOSED — " + "; ".join(gate["blocked_by"]),
                            "blocked_by": gate["blocked_by"],
                            "force_available": config.SKY_ALLOW_FORCE_APPROVE,
                        }
                    ), 409
            if decision == "APPROVED" and force and not config.SKY_ALLOW_FORCE_APPROVE:
                return jsonify(
                    {"error": "force approve is disabled (SKY_ALLOW_FORCE_APPROVE is not set)"}
                ), 403
            # W3.3 journal-first discipline: a decided real trade without its
            # journal answer means the last commitment was never processed,
            # so the next one waits. Same fail-closed population as the
            # graduation discipline criterion (P12.14). Never bypasses the
            # risk gate; only delays commitments, and the escape is audited.
            if decision == "APPROVED" and not body.get("acknowledge_journal"):
                from brain.weekly import missing_journals

                jg = missing_journals(db)
                if jg["missing"]:
                    return jsonify(
                        {
                            "error": (
                                f"Journal-first discipline: {jg['missing']} decided "
                                "real trade(s) unjournaled — journal them before the "
                                "next commitment"
                            ),
                            "journal_block": jg,
                            "acknowledge_available": True,
                        }
                    ), 409
            try:
                new = db.update_status(int(scan_id), decision, note=note, reviewer=reviewer)
            except (LifecycleError, TypeError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 400
            if new is None:
                return jsonify({"error": f"scan #{scan_id} not found"}), 404
        _audit(
            "review",
            str(scan_id),
            detail={
                "decision": decision,
                "note": note,
                "forced": force,
                "acknowledged_journal": bool(body.get("acknowledge_journal")),
            },
        )
        return jsonify({"ok": True, "scan_id": scan_id, "status": new})

    @app.get("/api/risk")
    def api_risk():
        """Risk & discipline gate status (decisions B4/B5/B6/B7/B9)."""
        from brain.analytics import monte_carlo_ruin_table
        from brain.journal import violation_rate
        from brain.metrics import business_metrics
        from brain.risk_gate import evaluate as gate_evaluate
        from brain.risk_gate import status_text
        from data.database import SignalDB

        try:
            with SignalDB() as db:
                gate = gate_evaluate(db)
                metrics = business_metrics(db)
                journal = violation_rate(db)
                state = db.get_trader_state()
                monte = monte_carlo_ruin_table(db)
            return jsonify(
                {
                    "gate": gate,
                    "trader_state": state,
                    "metrics": metrics,
                    "journal": journal,
                    "monte": monte,
                    "status_text": status_text.__doc__ or "",
                }
            )
        except Exception as exc:
            return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

    @app.get("/api/monte")
    def api_monte():
        """Monte Carlo risk-of-ruin table (expected DD / ruin prob / streak / TTR)."""
        from brain.analytics import monte_carlo_ruin_table
        from data.database import SignalDB

        try:
            samples = request.args.get("samples", type=int) or 2000
            seed = request.args.get("seed", type=int)
            ruin = request.args.get("ruin_threshold", type=float) or 50.0
            rp_raw = request.args.get("risk_pcts", type=str)
            risk_pcts = None
            if rp_raw:
                try:
                    risk_pcts = tuple(float(x.strip()) for x in rp_raw.split(",") if x.strip())
                except ValueError:
                    return jsonify({"error": "risk_pcts must be comma-separated floats"}), 400
            with SignalDB() as db:
                result = monte_carlo_ruin_table(
                    db,
                    risk_percents=risk_pcts or (0.25, 0.5, 1.0, 1.5, 2.0),
                    ruin_threshold_pct=ruin,
                    samples=min(samples, 20000),
                    seed=seed,
                )
            return jsonify(result)
        except Exception as exc:
            return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

    @app.get("/api/risk/veto-timeline")
    def api_risk_veto_timeline():
        """Audit timeline of trade vetoes and risk gate blocks."""
        from data.database import SignalDB

        sym = request.args.get("symbol")
        limit = request.args.get("limit", 50, type=int)
        with SignalDB() as db:
            vetoes = db.get_risk_vetoes(symbol=sym, limit=limit)
        return jsonify({"ok": True, "vetoes": vetoes, "total": len(vetoes)})

    @app.get("/api/analytics/r-distribution")
    def api_analytics_r_distribution():
        """Histogram distribution of realized net R-multiples."""
        from brain.analytics import r_distribution
        from data.database import SignalDB

        with SignalDB() as db:
            dist = r_distribution(db)
        return jsonify({"ok": True, "r_distribution": dist})

    @app.post("/api/trader-state")
    def api_trader_state():
        """Set/clear behavioral no-trade flags (decision B7)."""
        body = request.get_json(silent=True) or {}
        from data.database import SignalDB

        with SignalDB() as db:
            state = db.set_trader_state(
                angry=body.get("angry"),
                tired=body.get("tired"),
                revenge=body.get("revenge"),
                chasing=body.get("chasing"),
                note=body.get("note", ""),
            )
        _audit(
            "trader_state",
            "set",
            detail={k: body.get(k) for k in ("angry", "tired", "revenge", "chasing")},
        )
        return jsonify({"ok": True, "state": state})

    @app.get("/api/history")
    def api_history():
        from data.database import SignalDB

        with SignalDB() as db:
            return jsonify({"history": db.latest_scans(limit=15)})

    @app.get("/api/signal")
    def api_signal():
        scan_id = request.args.get("id", type=int)
        from data.database import SignalDB

        with SignalDB() as db:
            scan = db.get_scan(scan_id)
            if scan is None:
                return jsonify({"error": "not found"}), 404
            plans = json.loads(scan.get("plans_json") or "[]")
            decisions = db.decision_history(scan_id)
            paper_trade = db.paper_trade_for_scan(scan_id)
            journal = db.get_journal(scan_id)
        from brain.coach import management_checklist

        plan0 = (
            plans[0]
            if plans
            else {
                "entry": scan.get("entry"),
                "stop_loss": scan.get("stop_loss"),
                "take_profit": scan.get("take_profit"),
            }
        )
        management = management_checklist(plan0)
        return jsonify(
            {
                "scan": scan,
                "plans": plans,
                "decisions": decisions,
                "paper_trade": paper_trade,
                "journal": journal,
                "management": management,
            }
        )

    @app.get("/api/learning")
    def api_learning():
        from data.database import SignalDB

        try:
            with SignalDB() as db:
                from brain.journal import violation_rate
                from brain.metrics import business_metrics

                return jsonify(
                    {
                        "backtest": db.backtest_stats(),
                        "calibration": db.load_calibration(),
                        # P12.11 — which price series the learning store holds.
                        "sources": db.source_inventory(),
                        "plan_stats": db.plan_stats(),
                        "metrics": business_metrics(db),
                        "journal": violation_rate(db),
                    }
                )
        except Exception as exc:  # never 500 — the card degrades gracefully
            return jsonify(
                {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "backtest": {"overall": {"n": 0}},
                    "calibration": {},
                    "plan_stats": [],
                }
            )

    @app.get("/api/coach")
    def api_coach():
        symbol = _sym(request.args.get("symbol", SYMBOL))
        tf = request.args.get("tf", TIMEFRAME)
        from brain.coach import (
            explain_signal,
            five_levels,
            management_checklist,
            mentor,
            personal_feedback,
        )
        from data.database import SignalDB

        payload = compute_payload(symbol, tf, save=False, use_cache=False)
        with SignalDB() as db:
            feedback = personal_feedback(db)
        plans = payload.get("plans") or []
        return jsonify(
            {
                "explain": explain_signal(payload),
                "mentor": mentor(payload),
                "feedback": feedback,
                "five_levels": five_levels(payload),
                "management": (
                    payload.get("management") or management_checklist(plans[0] if plans else None)
                ),
            }
        )
