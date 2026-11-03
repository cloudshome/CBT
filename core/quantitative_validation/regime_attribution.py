"""
core/quantitative_validation/regime_attribution.py
=================================================
Market Regime Intelligence & Strategy Attribution Decomposition.
Classifies trades into 4 distinct regimes:
1. BULL_TREND: Momentum continuation, higher-highs, positive slope.
2. BEAR_TREND: Breakdown continuation, lower-lows, negative slope.
3. RANGING_CHOP: Low ADX, mean-reverting, low-volume consolidation.
4. VOLATILITY_SHOCK: Extreme ATR expansion, high funding/liquidation cascades.

Identifies regime subsidization (where 1 regime hides severe losses in others).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from .metrics import TradeReturn, calculate_net_expectancy, calculate_profit_factor


class MarketRegime(StrEnum):
    BULL_TREND = "BULL_TREND"
    BEAR_TREND = "BEAR_TREND"
    RANGING_CHOP = "RANGING_CHOP"
    VOLATILITY_SHOCK = "VOLATILITY_SHOCK"
    UNKNOWN = "UNKNOWN"


def classify_market_regime(
    adx: float,
    atr_percentile: float,
    ema_slope: float,
    funding_rate: float = 0.0,
) -> MarketRegime:
    """
    Classifies market conditions based on volatility, trend strength, and direction.
    """
    # 1. Volatility Shock takes precedence
    if atr_percentile >= 90.0 or abs(funding_rate) >= 0.0008:
        return MarketRegime.VOLATILITY_SHOCK

    # 2. Ranging / Low-Energy Chop
    if adx < 20.0 and atr_percentile < 60.0:
        return MarketRegime.RANGING_CHOP

    # 3. Trending Regimes
    if adx >= 20.0:
        if ema_slope > 0.0:
            return MarketRegime.BULL_TREND
        if ema_slope < 0.0:
            return MarketRegime.BEAR_TREND

    return MarketRegime.RANGING_CHOP


def decompose_regime_performance(trades: list[TradeReturn]) -> dict[str, Any]:
    """
    Decomposes trade performance by market regime.
    Computes per-regime expectancy, win rate, profit factor, and trade counts.
    Executes Subsidization Audit: detects if one regime masks losses in others.
    """
    regime_buckets: dict[str, list[TradeReturn]] = {
        MarketRegime.BULL_TREND.value: [],
        MarketRegime.BEAR_TREND.value: [],
        MarketRegime.RANGING_CHOP.value: [],
        MarketRegime.VOLATILITY_SHOCK.value: [],
        MarketRegime.UNKNOWN.value: [],
    }

    for t in trades:
        reg = t.regime if t.regime in regime_buckets else MarketRegime.UNKNOWN.value
        regime_buckets[reg].append(t)

    regime_metrics: dict[str, dict[str, Any]] = {}
    negative_expectancy_regimes: list[str] = []
    positive_expectancy_regimes: list[str] = []
    total_net_pnl = sum(t.net_r for t in trades)

    for reg_name, reg_trades in regime_buckets.items():
        count = len(reg_trades)
        if count == 0:
            regime_metrics[reg_name] = {
                "trade_count": 0,
                "net_expectancy_r": 0.0,
                "win_rate_pct": 0.0,
                "profit_factor": 0.0,
                "total_net_r": 0.0,
            }
            continue

        wins = sum(1 for t in reg_trades if t.is_win)
        win_rate = round((wins / count) * 100.0, 2)
        exp_r = round(calculate_net_expectancy(reg_trades), 4)
        pf = calculate_profit_factor(reg_trades)
        reg_net = round(sum(t.net_r for t in reg_trades), 4)

        regime_metrics[reg_name] = {
            "trade_count": count,
            "net_expectancy_r": exp_r,
            "win_rate_pct": win_rate,
            "profit_factor": pf,
            "total_net_r": reg_net,
        }

        if exp_r < 0.0:
            negative_expectancy_regimes.append(reg_name)
        elif exp_r > 0.0:
            positive_expectancy_regimes.append(reg_name)

    # Subsidization Audit
    # If total PnL is positive but 2 or more active regimes have negative expectancy
    active_regimes = [r for r, m in regime_metrics.items() if m["trade_count"] >= 3]
    subsidization_risk = False
    subsidization_reason = "None: Balanced performance across active regimes."

    if total_net_pnl > 0 and len(negative_expectancy_regimes) >= 2 and len(active_regimes) >= 3:
        subsidization_risk = True
        subsidization_reason = (
            f"Subsidization detected: Favorable regime(s) {positive_expectancy_regimes} "
            f"are disguising persistent negative expectancy in {negative_expectancy_regimes}."
        )

    return {
        "regime_metrics": regime_metrics,
        "active_regimes_count": len(active_regimes),
        "positive_expectancy_regimes": positive_expectancy_regimes,
        "negative_expectancy_regimes": negative_expectancy_regimes,
        "subsidization_risk": subsidization_risk,
        "subsidization_reason": subsidization_reason,
    }
