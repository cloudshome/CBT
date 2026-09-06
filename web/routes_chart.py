"""web/routes_chart.py — chart/trade/terminal/journal routes (extracted from web/app.py).

Refactor step 4 (ROADMAP §19): candles/chart/stream/commands/position-size/
ticket/trades/terminal/close/journal used to live inline inside ``make_app``.
Handler bodies are semantically identical to the original (exact string
match); ``__file__``-relative paths resolve identically from this module.
"""

from __future__ import annotations

import secrets
import time

from flask import g, jsonify, request

import config
from config import SYMBOL, TIMEFRAME
from data.sample_client import maybe_client
from web.payload import _sanitize_for_json, _scan_row_to_payload, _sym, compute_payload


def register(app, ctx):
    _audit = ctx["_audit"]

    @app.get("/api/candles")
    def api_candles():
        """OHLCV for the candlestick chart.

        Every value goes through :func:`web.chart_data._num`, so Pandas /
        NumPy scalars (``int64``, ``float64``, ``NaT``, ``NaN``) can never
        reach Flask's strict jsonify and blank the chart.
        """
        from web.chart_data import _epoch_seconds, _num

        symbol = _sym(request.args.get("symbol", SYMBOL))
        tf = request.args.get("tf", TIMEFRAME)
        limit = min(int(request.args.get("limit", 90)), 1000)
        try:
            df = maybe_client().klines(symbol, tf, limit)
            candles = []
            for row in df.tail(limit).itertuples(index=False):
                data = row._asdict()
                time_s = _epoch_seconds(data.get("ts"))
                if time_s is None:
                    continue
                candles.append(
                    {
                        "time": time_s,
                        "ts": time_s * 1000,
                        "open": _num(data.get("open")),
                        "high": _num(data.get("high")),
                        "low": _num(data.get("low")),
                        "close": _num(data.get("close")),
                        "volume": _num(data.get("volume")),
                    }
                )
            return jsonify(
                {"candles": candles, "count": len(candles), "symbol": symbol, "tf": tf}
            )
        except ConnectionError as exc:
            return jsonify({"error": str(exc)}), 502
        except Exception as exc:  # never blank the chart on an engine hiccup
            return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500

    @app.get("/api/chart")
    def api_chart():
        """Full chart workspace feed: candles + overlays + panes + levels.

        This is what the TradingView-style workspace draws: OHLCV in
        Lightweight Charts' epoch-second format, EMA/VWAP/Bollinger overlays,
        volume/RSI/MACD/ADX panes, support & resistance lines and the live
        plan's entry / stop / take-profit overlay.
        """
        from web.chart_data import build_chart

        symbol = _sym(request.args.get("symbol", SYMBOL))
        tf = request.args.get("tf", TIMEFRAME)
        limit = min(int(request.args.get("limit", 300)), 1000)
        with_plan = request.args.get("plan", "1") != "0"
        try:
            df = maybe_client().klines(symbol, tf, max(limit, 250))
        except ConnectionError as exc:
            return jsonify({"error": str(exc), "candles": []}), 502
        except Exception as exc:
            return jsonify(
                {"error": f"{type(exc).__name__}: {exc}", "candles": []}
            ), 500
        payload = None
        if with_plan:
            try:
                payload = compute_payload(symbol, tf, save=False, use_cache=True)
            except Exception:
                payload = None
        try:
            return jsonify(
                _sanitize_for_json(
                    build_chart(df, symbol, tf, payload=payload, limit=limit)
                )
            )
        except Exception as exc:  # pragma: no cover — defensive
            return jsonify(
                {"error": f"{type(exc).__name__}: {exc}", "candles": []}
            ), 500

    @app.get("/api/chart/stream")
    def api_chart_stream():
        """W2 — server-sent stream of the newest bar for one symbol/timeframe.

        Read-only market data: the chart calls ``series.update()`` with each
        frame instead of reloading. Every frame states whether the feed is
        live, waiting, stale or erroring, so a dead source can never be read
        as a quiet market. No order path, no writes, no threshold touched.
        """
        from flask import Response

        from web.live_stream import candle_events, poll_interval

        symbol = _sym(request.args.get("symbol", SYMBOL))
        tf = request.args.get("tf", TIMEFRAME)
        frames = request.args.get("frames")
        try:
            max_frames = max(1, min(600, int(frames))) if frames else None
        except (TypeError, ValueError):
            max_frames = None
        interval = poll_interval(tf)
        asked = request.args.get("interval")
        if asked:
            # A client may ask for a different cadence, but never a faster one
            # than the shared floor — one browser tab must not become a load
            # generator against the market source.
            try:
                from web.live_stream import MAX_INTERVAL, MIN_INTERVAL

                interval = max(MIN_INTERVAL, min(MAX_INTERVAL, float(asked)))
            except (TypeError, ValueError):
                pass

        def fetch(sym: str, timeframe: str, limit: int):
            return maybe_client().klines(sym, timeframe, limit)

        gen = candle_events(fetch, symbol, tf, interval=interval, max_frames=max_frames)
        return Response(
            gen,
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    # ── Command Center ────────────────────────────────────────────────
    @app.get("/api/commands")
    def api_commands():
        """The clickable catalog of every CLI command (no memorization)."""
        from web.command_center import catalog

        return jsonify(catalog())

    @app.post("/api/commands/run")
    def api_commands_run():
        """Run one allow-listed catalog command and return its output.

        Only ids that exist in ``web.command_center.COMMANDS`` can run, no
        shell is used, and blocked (long-lived / interactive) commands are
        refused with the terminal instruction instead.
        """
        from web.command_center import CommandError, run_command

        body = request.get_json(silent=True) or {}
        command_id = str(body.get("id") or "").strip()
        params = body.get("params") or {}
        if not isinstance(params, dict):
            return jsonify({"ok": False, "error": "params must be an object"}), 400
        try:
            result = run_command(command_id, params, timeout=body.get("timeout"))
            _audit("command_run", command_id, ok=bool(result.get("ok")))
            return jsonify(result)
        except CommandError as exc:
            return jsonify(
                {"ok": False, "error": str(exc), "command_id": command_id}
            ), 400
        except Exception as exc:  # pragma: no cover
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    # ── Risk Center: position-size calculator ─────────────────────────
    @app.post("/api/position-size")
    def api_position_size():
        """Position-size calculator bounded by the live risk gate."""
        from brain.risk_gate import evaluate as gate_evaluate
        from data.database import SignalDB
        from web.position_sizer import calculate

        body = request.get_json(silent=True) or {}
        symbol = _sym(body.get("symbol")) if body.get("symbol") else SYMBOL
        try:
            with SignalDB() as db:
                gate = gate_evaluate(db, symbol=symbol)
        except Exception:
            gate = {}
        try:
            return jsonify(
                _sanitize_for_json(
                    calculate(
                        balance=body.get("balance"),
                        risk_pct=body.get("risk_pct"),
                        entry=body.get("entry"),
                        stop=body.get("stop_loss"),
                        take_profit=body.get("take_profit"),
                        symbol=symbol,
                        gate=gate,
                        leverage=body.get("leverage"),
                    )
                )
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.get("/api/ticket/meta")
    def api_ticket_meta():
        """Honest inputs for the terminal trade ticket (T4).

        The ticket's risk-dollar and fee estimates must never be invented
        client-side. This returns the real account balance (``ACCOUNT_BALANCE``,
        0 when unset — the UI shows ``—`` rather than a fake $100k) and the
        per-symbol cost model (``data.costs.cost_model_for_symbol``) the
        backtester uses, so the fee estimate agrees with the desk's cost
        doctrine: round-trip taker fee + full spread + slippage, no funding on
        gold spot. Read-only; no order path.
        """
        from config import ACCOUNT_BALANCE, KELLY_MAX_RISK_PCT, MAX_RISK_PCT, RISK_PCT
        from data.costs import (
            DEFAULT_FUNDING_RATE_8H,
            DEFAULT_HALF_SPREAD,
            DEFAULT_HOLDING_HOURS,
            SPREADS,
            cost_model_for_symbol,
            is_gold_symbol,
        )

        symbol = _sym(request.args.get("symbol", SYMBOL))
        model = cost_model_for_symbol(symbol)
        is_gold = is_gold_symbol(symbol)
        half_spread = (
            model.spread_pct
            if model.spread_pct is not None
            else SPREADS.get(symbol, DEFAULT_HALF_SPREAD)
        )
        fee_per_side = (
            model.spot_fee_pct if model.market == "spot" else model.taker_fee_pct
        )
        round_trip_cost_pct = round(
            2.0 * fee_per_side + 2.0 * half_spread + 2.0 * model.slip_pct, 6
        )
        return jsonify(
            _sanitize_for_json(
                {
                    "symbol": symbol,
                    "market": model.market,
                    "account_balance": float(ACCOUNT_BALANCE or 0.0),
                    "account_configured": bool(ACCOUNT_BALANCE and ACCOUNT_BALANCE > 0),
                    "default_risk_pct": RISK_PCT,
                    "max_risk_pct": MAX_RISK_PCT,
                    "kelly_max_risk_pct": KELLY_MAX_RISK_PCT,
                    "taker_fee_pct": model.taker_fee_pct,
                    "spot_fee_pct": model.spot_fee_pct,
                    "half_spread_pct": half_spread,
                    "slip_pct": model.slip_pct,
                    "funding_rate_8h": 0.0 if is_gold else DEFAULT_FUNDING_RATE_8H,
                    "holding_hours": DEFAULT_HOLDING_HOURS,
                    "round_trip_cost_pct": round_trip_cost_pct,
                    "note": (
                        None
                        if ACCOUNT_BALANCE
                        else "Set ACCOUNT_BALANCE in .env to enable position sizing."
                    ),
                }
            )
        )

    # ── Trade manager: the live open book ─────────────────────────────
    @app.get("/api/trades")
    def api_trades():
        """Open paper positions with live R, MAE/MFE and management advice."""
        from brain.coach import management_checklist
        from data.database import SignalDB

        symbol = (
            _sym(request.args.get("symbol")) if request.args.get("symbol") else None
        )
        try:
            with SignalDB() as db:
                rows = db.live_open_rows(symbol=symbol)
                stats = db.paper_trade_stats(symbol)
        except Exception as exc:
            return jsonify(
                {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "open": [],
                    "recent": [],
                }
            ), 200

        prices: dict[str, float | None] = {}

        def last_price(sym: str, tf: str) -> float | None:
            key = f"{sym}:{tf}"
            if key not in prices:
                try:
                    df = maybe_client().klines(sym, tf, 2)
                    prices[key] = float(df["close"].iloc[-1])
                except Exception:
                    prices[key] = None
            return prices[key]

        now_ms = int(time.time() * 1000)
        out = []
        for row in rows:
            entry = row.get("entry_price") or row.get("entry")
            stop = row.get("stop_loss")
            take = row.get("take_profit")
            price = last_price(
                row.get("symbol") or SYMBOL, row.get("timeframe") or TIMEFRAME
            ) or row.get("last_price")
            risk = abs(float(entry) - float(stop)) if entry and stop else None
            current_r = None
            if price is not None and entry and risk:
                delta = float(price) - float(entry)
                if str(row.get("action")).upper() == "SELL":
                    delta = -delta
                current_r = round(delta / risk, 3)
            opened = row.get("opened_ts") or row.get("created_ts") or now_ms
            item = dict(row)
            item.update(
                {
                    "current_price": price,
                    "current_r": current_r,
                    "risk_per_unit": risk,
                    "stop_distance": (
                        abs(float(price) - float(stop))
                        if price is not None and stop
                        else None
                    ),
                    "tp_distance": (
                        abs(float(take) - float(price))
                        if price is not None and take
                        else None
                    ),
                    "minutes_in_trade": max(0, int((now_ms - int(opened)) / 60000)),
                    "management": management_checklist(
                        {
                            "entry": entry,
                            "stop_loss": stop,
                            "take_profits": [take] if take is not None else [],
                        }
                    ),
                }
            )
            out.append(item)
        return jsonify(
            _sanitize_for_json(
                {
                    "ok": True,
                    "open": out,
                    "count": len(out),
                    "recent": (stats or {}).get("recent", []),
                    "overall": (stats or {}).get("overall", {}),
                }
            )
        )

    # ── T3 — Trade Terminal: confirm ticket → desk path → paper position ─
    @app.post("/api/terminal/confirm")
    def api_terminal_confirm():
        """Turn a confirmed terminal ticket into an enrolled paper trade.

        T3 — the product expression of the money path. This does not bypass
        the desk: the ticket becomes a real scan row in the human approval
        queue (``save_scan``, PENDING_REVIEW), the risk & discipline gate is
        freshly evaluated on the server immediately before the APPROVED
        decision, the journal-first discipline (W3.3) applies exactly as in
        ``/api/review``, and the paper runner enrolls + fills the position.
        ``ticket_id`` makes a retried confirm idempotent. Market tickets are
        paper-filled at the confirmed entry; limit/conditional tickets wait
        for the entry level like any conditional desk plan. Still paper-only;
        never an exchange order.
        """
        body = request.get_json(silent=True) or {}
        symbol = _sym(body.get("symbol"))
        timeframe = str(body.get("timeframe") or TIMEFRAME)
        action = str(body.get("action") or "").upper()
        ticket_type = str(body.get("ticket_type") or "market").lower()
        if action not in ("BUY", "SELL"):
            return jsonify({"error": "action must be BUY or SELL"}), 400
        if ticket_type not in ("market", "limit", "conditional"):
            return jsonify(
                {
                    "error": f"bad ticket_type {ticket_type!r} "
                    "(market | limit | conditional)"
                }
            ), 400
        try:
            entry = float(body.get("entry"))
            stop = float(body.get("stop_loss"))
        except (TypeError, ValueError):
            return jsonify({"error": "entry and stop_loss are required numbers"}), 400
        if entry <= 0 or stop <= 0:
            return jsonify({"error": "entry and stop_loss must be positive"}), 400
        # Side sanity — fail closed on an inverted stop, never on a tight one.
        if action == "BUY" and stop >= entry:
            return jsonify({"error": "BUY stop must be below entry"}), 400
        if action == "SELL" and stop <= entry:
            return jsonify({"error": "SELL stop must be above entry"}), 400
        tps = []
        for value in body.get("take_profits") or []:
            try:
                tps.append(float(value))
            except (TypeError, ValueError):
                return jsonify({"error": "take_profits must be numbers"}), 400
        tps = [t for t in tps if t > 0]
        if tps:
            for i in (1, 2):
                if len(tps) > i and tps[i] <= tps[i - 1]:
                    return jsonify(
                        {"error": "take_profits must be strictly increasing"}
                    ), 400
        tp1 = tps[0] if tps else None
        rr = round(abs(tp1 - entry) / abs(entry - stop), 3) if tp1 is not None else None
        risk_raw = body.get("risk_pct")
        try:
            # `or 0.5` would silently swallow an explicit 0 — fail closed.
            risk_pct = float(risk_raw) if risk_raw not in (None, "") else 0.5
        except (TypeError, ValueError):
            return jsonify({"error": "risk_pct must be a number"}), 400
        if not (0 < risk_pct <= 100):
            return jsonify({"error": "risk_pct must be in (0, 100]"}), 400
        plan_type = str(body.get("plan_type") or "Manual").strip()[:60] or "Manual"
        conf = body.get("confidence")
        try:
            conf = int(conf) if conf not in (None, "") else None
        except (TypeError, ValueError):
            conf = None
        conf_label = str(body.get("confidence_label") or "").strip()[:20] or None
        reason = str(body.get("reason") or "manual terminal ticket")[:300]
        ticket_id = str(body.get("ticket_id") or "")[:80]
        sentiment = (
            body.get("sentiment") if isinstance(body.get("sentiment"), dict) else {}
        )
        now_ms = int(time.time() * 1000)
        signal_id = (
            f"terminal_{ticket_id}"
            if ticket_id
            else f"terminal_{symbol}_{now_ms}_{secrets.token_hex(3)}"
        )
        from brain.risk_gate import evaluate as gate_evaluate
        from data.database import SignalDB
        from data.paper_trading import PaperTradingRunner

        with SignalDB() as db:
            # Idempotency: a retried confirm reuses the same ticket scan
            # instead of enrolling a second position.
            existing = None
            if ticket_id:
                row = db.conn.execute(
                    "SELECT id, status FROM scans WHERE signal_id=?", (signal_id,)
                ).fetchone()
                if row:
                    existing = dict(row)
            if existing:
                paper = db.paper_trade_for_scan(int(existing["id"]))
                if existing["status"] in ("CLOSED", "REJECTED", "SKIPPED"):
                    return jsonify(
                        {
                            "ok": False,
                            "error": f"ticket already used "
                            f"(scan #{existing['id']} is "
                            f"{existing['status']})",
                            "scan_id": existing["id"],
                            "status": existing["status"],
                        }
                    ), 409
                return jsonify(
                    {
                        "ok": True,
                        "duplicate": True,
                        "scan_id": existing["id"],
                        "status": existing["status"],
                        "paper_trade": paper,
                    }
                ), 200
            plan = {
                "id": "terminal",
                "type": plan_type,
                "action": action,
                "condition": (reason or "manual terminal ticket"),
                "trigger_level": entry,
                "entry": entry,
                "stop_loss": stop,
                "take_profits": tps,
                "risk_reward": rr,
                "confidence": conf,
                "confidence_label": conf_label,
                # market tickets fill at the confirmed entry; limit and
                # conditional tickets wait for the level, like desk plans.
                "status": "active" if ticket_type == "market" else "waiting",
            }
            payload = {
                "signal": {
                    "signal_id": signal_id,
                    "timestamp": now_ms,
                    "asset": symbol,
                    "timeframe": timeframe,
                    "action": action,
                    "entry": entry,
                    "stop_loss": stop,
                    "take_profit": tp1,
                    "risk_reward": rr,
                    "confidence": conf_label,
                    "reason": reason,
                    "signal_type": "SIGNAL",
                },
                "plans": [plan],
                "snapshot": {
                    "features": {
                        "price": entry,
                        "score_used": conf,
                        "regime_name": str(body.get("regime") or "").strip()[:40],
                    }
                },
                "market_context": {},
                "sentiment": sentiment,
            }
            scan_id = db.save_scan(payload)
            # Fresh server-side gate read immediately before the decision —
            # same evaluation the desk uses, with the ticket's own plan type.
            gate = gate_evaluate(db, symbol=symbol, plan_type=plan_type, action=action)
            force = bool(body.get("force"))
            if not gate["allowed"] and not force:
                _audit(
                    "terminal_confirm",
                    symbol,
                    ok=False,
                    detail={
                        "scan_id": scan_id,
                        "action": action,
                        "plan_type": plan_type,
                        "blocked_by": gate["blocked_by"],
                    },
                )
                return jsonify(
                    {
                        "error": "Risk gate CLOSED — " + "; ".join(gate["blocked_by"]),
                        "blocked_by": gate["blocked_by"],
                        "force_available": config.SKY_ALLOW_FORCE_APPROVE,
                    }
                ), 409
            if force and not config.SKY_ALLOW_FORCE_APPROVE:
                return jsonify(
                    {
                        "error": "force confirm is disabled "
                        "(SKY_ALLOW_FORCE_APPROVE is not set)"
                    }
                ), 403
            # W3.3 journal-first discipline — same fail-closed population and
            # audited escape as /api/review.
            if not body.get("acknowledge_journal"):
                from brain.weekly import missing_journals

                jg = missing_journals(db)
                if jg["missing"]:
                    return jsonify(
                        {
                            "error": (
                                f"Journal-first discipline: {jg['missing']} "
                                "decided real trade(s) unjournaled — journal "
                                "them before the next commitment"
                            ),
                            "journal_block": jg,
                            "acknowledge_available": True,
                        }
                    ), 409
            reviewer = (getattr(g, "user", None) or {}).get("username") or "terminal"
            new_status = db.update_status(
                scan_id,
                "APPROVED",
                note=(
                    f"terminal confirm: {action} {entry:,.8g} SL {stop:,.8g} "
                    f"TPs {tps} ({plan_type}, {ticket_type}, {risk_pct}% risk)"
                ),
                reviewer=reviewer,
            )
            if new_status is None:
                return jsonify({"error": f"scan #{scan_id} not found"}), 404
            run = (
                PaperTradingRunner(db=db, client=maybe_client())
                .run_once(symbol=symbol)
                .as_dict()
            )
            paper = db.paper_trade_for_scan(scan_id)
            scan = db.get_scan(scan_id)
        _audit(
            "terminal_confirm",
            symbol,
            detail={
                "scan_id": scan_id,
                "action": action,
                "entry": entry,
                "stop_loss": stop,
                "take_profits": tps,
                "risk_pct": risk_pct,
                "plan_type": plan_type,
                "ticket_type": ticket_type,
                "forced": force,
                "acknowledged_journal": bool(body.get("acknowledge_journal")),
            },
        )
        return jsonify(
            _sanitize_for_json(
                {
                    "ok": True,
                    "scan_id": scan_id,
                    "status": (scan or {}).get("status"),
                    "gate": {
                        "allowed": gate["allowed"],
                        "blocked_by": gate["blocked_by"],
                    },
                    "paper_trade": paper,
                    "run": run,
                }
            )
        )

    @app.post("/api/terminal/close")
    def api_terminal_close():
        """Close one open paper position from the terminal (T3).

        The scan lifecycle advances exactly like the desk close decision, and
        the paper row is closed with the real economic outcome: the existing
        ``TP_HIT`` / ``STOP_LOSS`` buckets (the populations every discipline
        surface — win-rate, journal gate, graduation — already counts), with
        ``close_reason`` recording that this was a manual terminal close and
        the exact exit. A position still ``WAITING_ENTRY`` is cancelled —
        nothing was traded, nothing needs journaling. Paper-only; never an
        exchange order.
        """
        body = request.get_json(silent=True) or {}
        try:
            trade_id = int(body.get("trade_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "trade_id is required"}), 400
        exit_price = body.get("exit_price")
        if exit_price not in (None, ""):
            try:
                exit_price = float(exit_price)
            except (TypeError, ValueError):
                return jsonify({"error": "exit_price must be a number"}), 400
            if exit_price <= 0:
                return jsonify({"error": "exit_price must be positive"}), 400
        from data.database import SignalDB
        from engine.lifecycle import LifecycleError

        reviewer = (getattr(g, "user", None) or {}).get("username") or "terminal"
        now_ms = int(time.time() * 1000)
        with SignalDB() as db:
            trade = db.get_paper_trade(trade_id)
            if trade is None:
                return jsonify({"error": f"paper trade #{trade_id} not found"}), 404
            if trade.get("status") not in ("WAITING_ENTRY", "OPEN"):
                return jsonify(
                    {
                        "ok": False,
                        "error": f"paper trade #{trade_id} is already "
                        f"{trade.get('status')}",
                        "status": trade.get("status"),
                    }
                ), 409
            scan = db.get_scan(int(trade["scan_id"]))
            if scan is None:
                return jsonify({"error": f"scan #{trade['scan_id']} not found"}), 404
            scan_status = scan.get("status")

            if trade.get("status") == "WAITING_ENTRY":
                db.cancel_paper_trade(
                    trade_id, reason="terminal close before entry", closed_ts=now_ms
                )
                if scan_status == "APPROVED":
                    try:
                        db.update_status(
                            int(trade["scan_id"]),
                            "SKIPPED",
                            note="terminal close before entry",
                            reviewer=reviewer,
                        )
                    except LifecycleError:
                        pass
                _audit(
                    "terminal_close",
                    str(trade.get("symbol")),
                    detail={
                        "trade_id": trade_id,
                        "scan_id": trade["scan_id"],
                        "outcome": "NOT_FILLED",
                    },
                )
                return jsonify(
                    {
                        "ok": True,
                        "trade_id": trade_id,
                        "scan_id": trade["scan_id"],
                        "status": "CANCELLED",
                        "outcome": None,
                        "exit_price": None,
                        "rr_achieved": None,
                        "journal_required": False,
                    }
                )

            entry = float(trade["entry_price"] or trade["entry"])
            stop = float(trade["stop_loss"])
            risk = abs(entry - stop)
            if exit_price is None:
                exit_price = (
                    float(trade["last_price"])
                    if trade.get("last_price") is not None
                    else None
                )
            if exit_price is None:
                try:
                    df = maybe_client().klines(
                        trade["symbol"] or SYMBOL, trade["timeframe"] or TIMEFRAME, 2
                    )
                    exit_price = float(df["close"].iloc[-1])
                except Exception:
                    exit_price = None
            if exit_price is None:
                return jsonify(
                    {
                        "error": "no exit price available — pass "
                        "exit_price or let the paper runner "
                        "populate last_price first"
                    }
                ), 409
            side = str(trade["action"]).upper()
            rr = round(
                (entry - exit_price) / risk
                if side == "SELL"
                else (exit_price - entry) / risk,
                3,
            )
            tp = trade.get("take_profit")
            if side == "SELL":
                hit_tp = tp is not None and exit_price <= float(tp)
                hit_sl = exit_price >= stop
            else:
                hit_tp = tp is not None and exit_price >= float(tp)
                hit_sl = exit_price <= stop
            if hit_tp:
                outcome = "TP_HIT"
                reason = "manual terminal close at/through target"
            elif hit_sl:
                outcome = "STOP_LOSS"
                reason = "manual terminal close at/through stop"
            elif rr >= 0:
                outcome = "TP_HIT"
                reason = "manual terminal close in profit before target"
            else:
                outcome = "STOP_LOSS"
                reason = "manual terminal close in loss before stop"
            # Lifecycle: EXECUTED → CLOSED. A trade the runner never advanced
            # past APPROVED is advanced honestly first (fill at its entry).
            try:
                if scan_status == "APPROVED":
                    db.update_status(
                        int(trade["scan_id"]),
                        "EXECUTED",
                        note=f"terminal close fill at entry {entry:,.8g}",
                        reviewer=reviewer,
                    )
                db.update_status(
                    int(trade["scan_id"]),
                    "CLOSED",
                    note=(
                        f"terminal manual close at {exit_price:,.8g} "
                        f"— {outcome} ({rr:+.2f}R) — {reason}"
                    ),
                    reviewer=reviewer,
                )
            except LifecycleError as exc:
                return jsonify({"error": f"scan cannot be closed: {exc.message}"}), 409
            closed = db.close_paper_trade(
                trade_id,
                outcome=outcome,
                exit_price=exit_price,
                rr_achieved=rr,
                close_reason=reason,
                closed_ts=now_ms,
                last_price=exit_price,
            )
            if not closed:
                return jsonify(
                    {
                        "error": "position was closed concurrently "
                        "(runner or another session)"
                    }
                ), 409
        _audit(
            "terminal_close",
            str(trade.get("symbol")),
            detail={
                "trade_id": trade_id,
                "scan_id": trade["scan_id"],
                "exit_price": exit_price,
                "outcome": outcome,
                "rr_achieved": rr,
            },
        )
        return jsonify(
            {
                "ok": True,
                "trade_id": trade_id,
                "scan_id": trade["scan_id"],
                "status": "CLOSED",
                "outcome": outcome,
                "exit_price": exit_price,
                "rr_achieved": rr,
                "journal_required": True,
            }
        )

    # ── Journal: a real form, not a CLI instruction ───────────────────
    @app.get("/api/journal")
    def api_journal_get():
        """Journal entry for a scan, or the discipline summary when no id."""
        from brain.journal import (
            EMOTIONS,
            execution_quality,
            get_journal,
            pre_trade_checklist,
            violation_rate,
        )
        from data.database import SignalDB

        scan_id = request.args.get("scan_id", type=int)
        try:
            with SignalDB() as db:
                summary = violation_rate(db)
                if scan_id is None:
                    # Every recent decision is journalable — including the ones
                    # you rejected or stood aside on. "I did not take it, and
                    # here is why" is the entry that builds discipline fastest.
                    recent = db.latest_scans(limit=40)
                    decided = ("CLOSED", "EXECUTED", "APPROVED", "REJECTED", "SKIPPED")
                    recent.sort(
                        key=lambda r: (
                            r.get("status") not in decided,
                            -(r.get("id") or 0),
                        )
                    )
                    return jsonify(
                        _sanitize_for_json(
                            {
                                "ok": True,
                                "summary": summary,
                                "emotions": list(EMOTIONS),
                                "journalable": recent,
                            }
                        )
                    )
                scan = db.get_scan(scan_id)
                entry = get_journal(db, scan_id)
                quality = execution_quality(db, scan_id)
                # get_scan() returns the FLAT scans row; pre_trade_checklist
                # reads the nested scan payload, so re-nest it here (the
                # checklist silently reported "—" for every field otherwise).
                checklist = pre_trade_checklist(_scan_row_to_payload(scan))
                paper = db.paper_trade_for_scan(scan_id)
            return jsonify(
                _sanitize_for_json(
                    {
                        "ok": True,
                        "scan_id": scan_id,
                        "entry": entry,
                        "scan": scan,
                        "paper": paper,
                        "quality": quality,
                        "checklist": checklist,
                        "emotions": list(EMOTIONS),
                        "summary": summary,
                    }
                )
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    @app.post("/api/journal")
    def api_journal_save():
        """Save the post-trade journal from the dashboard form."""
        from brain.journal import execution_quality, save_journal
        from data.database import SignalDB

        body = request.get_json(silent=True) or {}
        scan_id = body.get("scan_id")
        try:
            scan_id = int(scan_id)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "scan_id is required"}), 400
        followed = body.get("followed_rules")
        if followed is not None:
            followed = str(followed).lower() in ("1", "true", "yes", "on")
        try:
            with SignalDB() as db:
                entry = save_journal(
                    db,
                    scan_id,
                    followed_rules=followed,
                    emotion=str(body.get("emotion") or ""),
                    mistake=str(body.get("mistake") or ""),
                    screenshot_path=str(body.get("screenshot_path") or ""),
                    would_change=str(body.get("would_change") or ""),
                    notes=str(body.get("notes") or ""),
                )
                quality = execution_quality(db, scan_id)
            _audit("journal", str(scan_id), detail={"followed_rules": followed})
            return jsonify(
                _sanitize_for_json(
                    {"ok": True, "scan_id": scan_id, "entry": entry, "quality": quality}
                )
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), 500

    # ── Real-world connections ────────────────────────────────────────
