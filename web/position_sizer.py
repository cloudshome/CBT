"""web/position_sizer.py — the Risk Center position-size calculator.

Answers the only sizing question that matters: *how many units may I buy so
that being wrong costs exactly my predefined unit of risk?*

    risk amount = balance × risk %
    stop distance = |entry − stop|
    units = risk amount ÷ stop distance

The calculator is deliberately conservative:

  * the effective risk % is capped by the progression ladder (``brain.risk_gate``)
    and by the Kelly clamp, so a "student" account cannot size like a scaled one;
  * when the risk gate is CLOSED the recommended size is **zero** and the
    reason is returned with it;
  * the daily and weekly loss budgets are reported as remaining-trades counts
    so the number is meaningful, not abstract.

Nothing here places an order. It is arithmetic plus the gate's verdict.
"""

from __future__ import annotations


def _f(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None  # drop NaN


def calculate(
    *,
    balance: float | None,
    risk_pct: float | None,
    entry: float | None,
    stop: float | None,
    take_profit: float | None = None,
    symbol: str = "BTCUSDT",
    gate: dict | None = None,
    leverage: float | None = None,
) -> dict:
    """Compute a position size plus every number the trader must see."""
    from brain.risk_gate import effective_risk, progression
    from config import ACCOUNT_BALANCE, KELLY_MAX_RISK_PCT, MAX_RISK_PCT

    warnings: list[str] = []
    balance = _f(balance) or _f(ACCOUNT_BALANCE) or 0.0
    entry = _f(entry)
    stop = _f(stop)
    take_profit = _f(take_profit)
    leverage = _f(leverage) or 1.0

    eff = effective_risk()
    prog = progression()
    level = prog.get("level", "student")
    ladder_cap = float(eff.get("risk_pct") or MAX_RISK_PCT)
    requested = _f(risk_pct)
    if requested is None:
        requested = ladder_cap
    applied = min(requested, ladder_cap, MAX_RISK_PCT)
    if requested > applied:
        warnings.append(
            f"risk reduced from {requested:g}% to {applied:g}% — the "
            f"'{level}' progression level caps risk per trade"
        )

    gate = gate or {}
    gate_open = bool(gate.get("allowed", gate.get("open", True)))
    blocked_by = list(gate.get("blocked_by") or [])

    result: dict = {
        "symbol": symbol,
        "balance": round(balance, 2),
        "risk_pct_requested": requested,
        "risk_pct_applied": applied,
        "progression": level,
        "progression_label": prog.get("label"),
        "ladder_cap_pct": ladder_cap,
        "kelly_cap_pct": KELLY_MAX_RISK_PCT,
        "daily_budget_pct": eff.get("daily"),
        "weekly_budget_pct": eff.get("weekly"),
        "entry": entry,
        "stop_loss": stop,
        "take_profit": take_profit,
        "leverage": leverage,
        "gate_open": gate_open,
        "blocked_by": blocked_by,
        "warnings": warnings,
        "ok": False,
    }

    if balance <= 0:
        result["error"] = (
            "Set your account balance (or ACCOUNT_BALANCE in .env) before sizing a trade."
        )
        return result
    if entry is None or stop is None:
        result["error"] = "Entry and stop-loss are both required to size a trade."
        return result
    stop_distance = abs(entry - stop)
    if stop_distance <= 0:
        result["error"] = "Stop-loss must differ from entry — a zero stop is not a trade."
        return result

    risk_amount = balance * (applied / 100.0)
    units = risk_amount / stop_distance
    notional = units * entry
    stop_pct = stop_distance / entry * 100.0

    reward_amount = rr = None
    if take_profit is not None:
        reward_distance = abs(take_profit - entry)
        reward_amount = units * reward_distance
        rr = reward_distance / stop_distance if stop_distance else None
        if rr is not None and rr < 1.5:
            warnings.append(f"risk/reward is only 1:{rr:.2f} — the desk floor is 1:1.5")

    daily_pct = float(eff.get("daily") or 0)
    weekly_pct = float(eff.get("weekly") or 0)
    result.update(
        {
            "ok": True,
            "risk_amount": round(risk_amount, 2),
            "stop_distance": round(stop_distance, 8),
            "stop_pct": round(stop_pct, 4),
            "units": round(units, 8),
            "notional": round(notional, 2),
            "notional_pct_of_balance": round(notional / balance * 100.0, 2),
            "margin_required": round(notional / leverage, 2) if leverage else None,
            "reward_amount": round(reward_amount, 2) if reward_amount is not None else None,
            "risk_reward": round(rr, 3) if rr is not None else None,
            "losses_to_daily_limit": int(daily_pct // applied) if applied else None,
            "losses_to_weekly_limit": int(weekly_pct // applied) if applied else None,
        }
    )

    if not gate_open:
        result["recommended_units"] = 0.0
        result["verdict"] = "Risk gate CLOSED — the correct size is ZERO. " + "; ".join(blocked_by)
    else:
        result["recommended_units"] = result["units"]
        result["verdict"] = (
            f"Risking {applied:g}% ({risk_amount:,.2f}) on a "
            f"{stop_pct:.2f}% stop → {units:,.6f} units "
            f"({notional:,.2f} notional). "
            f"{result['losses_to_daily_limit']} losses in a row reach today's limit."
        )
    result["warnings"] = warnings
    return result
