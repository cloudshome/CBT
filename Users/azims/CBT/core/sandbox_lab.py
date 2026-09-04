"""
Master Backtest Sandbox & Zero-Lookahead Bar Replay Lab.
Simulates chronological step-by-step execution across historical candles,
strictly enforcing causal timestamps, realistic fee structures, and orderbook slippage.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from core.causal_firewall import causal_firewall

logger = logging.getLogger("ai_quant_sentinel.sandbox_lab")


@dataclass
class BacktestTrade:
    entry_time: int
    exit_time: int
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    pnl_usd: float
    pnl_percent: float
    rr_ratio: float
    exit_reason: str  # "TAKE_PROFIT", "STOP_LOSS", "TIME_STOP"


@dataclass
class BacktestReport:
    symbol: str
    timeframe: str
    total_trades: int
    win_rate: float
    profit_factor: float
    sharpe_ratio: float
    max_drawdown_pct: float
    net_pnl_usd: float
    trades: list[BacktestTrade]
    return_series: list[float]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["trades"] = [asdict(t) for t in self.trades]
        return d


class SandboxLab:
    """Master chronological replay backtester."""

    def run_backtest(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict[str, Any]],
        strategy_logic_fn: Callable[[dict[str, Any], int], dict[str, Any] | None] | None = None,
        starting_capital: float = 100000.0,
        risk_per_trade_pct: float = 0.01,
        taker_fee_bps: float = 5.0,
        slippage_bps: float = 3.0,
    ) -> BacktestReport:
        """
        Replays candles sequentially from oldest to newest with causal isolation.
        """
        if len(candles) < 30:
            return BacktestReport(
                symbol=symbol,
                timeframe=timeframe,
                total_trades=0,
                win_rate=0.0,
                profit_factor=0.0,
                sharpe_ratio=0.0,
                max_drawdown_pct=0.0,
                net_pnl_usd=0.0,
                trades=[],
                return_series=[],
            )

        capital = starting_capital
        equity_peak = starting_capital
        max_dd = 0.0
        trades: list[BacktestTrade] = []
        returns: list[float] = []

        active_pos = None

        for i in range(25, len(candles)):
            c = candles[i]
            c_time = c["timestamp"]
            causal_firewall.set_simulation_time(c_time)

            # Check open position exit
            if active_pos is not None:
                is_long = active_pos["direction"] == "LONG"
                entry_p = active_pos["entry_price"]
                sl_p = active_pos["stop_loss"]
                tp_p = active_pos["take_profit"]

                exit_trade = False
                exit_price = c["close"]
                reason = "TIME_STOP"

                if is_long:
                    if c["high"] >= tp_p:
                        exit_price = tp_p * (1.0 - slippage_bps / 10000.0)
                        exit_trade = True
                        reason = "TAKE_PROFIT"
                    elif c["low"] <= sl_p:
                        exit_price = sl_p * (1.0 - slippage_bps / 10000.0)
                        exit_trade = True
                        reason = "STOP_LOSS"
                else:
                    if c["low"] <= tp_p:
                        exit_price = tp_p * (1.0 + slippage_bps / 10000.0)
                        exit_trade = True
                        reason = "TAKE_PROFIT"
                    elif c["high"] >= sl_p:
                        exit_price = sl_p * (1.0 + slippage_bps / 10000.0)
                        exit_trade = True
                        reason = "STOP_LOSS"

                if exit_trade or (i - active_pos["entry_bar"] >= 20):
                    pnl_pct = (
                        (exit_price - entry_p) / entry_p
                        if is_long
                        else (entry_p - exit_price) / entry_p
                    )
                    # Deduct roundtrip fees
                    pnl_pct -= (2.0 * taker_fee_bps) / 10000.0
                    pnl_usd = active_pos["size_units"] * entry_p * pnl_pct
                    capital += pnl_usd

                    rr = (
                        abs(exit_price - entry_p) / abs(entry_p - sl_p)
                        if abs(entry_p - sl_p) > 0
                        else 1.0
                    )

                    trades.append(
                        BacktestTrade(
                            entry_time=active_pos["entry_time"],
                            exit_time=c_time,
                            symbol=symbol,
                            direction=active_pos["direction"],
                            entry_price=round(entry_p, 2),
                            exit_price=round(exit_price, 2),
                            pnl_usd=round(pnl_usd, 2),
                            pnl_percent=round(pnl_pct * 100.0, 3),
                            rr_ratio=round(rr, 2),
                            exit_reason=reason,
                        )
                    )
                    returns.append(pnl_pct)
                    active_pos = None

            # Drawdown update
            if capital > equity_peak:
                equity_peak = capital
            dd = (equity_peak - capital) / equity_peak if equity_peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

            # Generate new entry signals
            if active_pos is None and i < len(candles) - 5:
                # Built-in baseline momentum & FVG strategy trigger if no custom function provided
                c_prev = candles[i - 1]
                c_prev2 = candles[i - 2]
                bull_signal = (
                    c["close"] > c["open"]
                    and c["low"] > c_prev2["high"]
                    and c["close"] > c_prev["high"]
                )
                bear_signal = (
                    c["close"] < c["open"]
                    and c["high"] < c_prev2["low"]
                    and c["close"] < c_prev["low"]
                )

                if bull_signal:
                    entry = c["close"] * (1.0 + slippage_bps / 10000.0)
                    sl = c["low"] * 0.995
                    tp = entry + (entry - sl) * 2.0
                    risk_usd = capital * risk_per_trade_pct
                    units = risk_usd / abs(entry - sl)
                    active_pos = {
                        "direction": "LONG",
                        "entry_price": entry,
                        "stop_loss": sl,
                        "take_profit": tp,
                        "size_units": units,
                        "entry_time": c_time,
                        "entry_bar": i,
                    }
                elif bear_signal:
                    entry = c["close"] * (1.0 - slippage_bps / 10000.0)
                    sl = c["high"] * 1.005
                    tp = entry - (sl - entry) * 2.0
                    risk_usd = capital * risk_per_trade_pct
                    units = risk_usd / abs(sl - entry)
                    active_pos = {
                        "direction": "SHORT",
                        "entry_price": entry,
                        "stop_loss": sl,
                        "take_profit": tp,
                        "size_units": units,
                        "entry_time": c_time,
                        "entry_bar": i,
                    }

        # Reset causal clock to live mode
        causal_firewall.set_simulation_time(None)

        total_trades = len(trades)
        wins = [t for t in trades if t.pnl_usd > 0]
        losses = [t for t in trades if t.pnl_usd <= 0]
        win_rate = len(wins) / max(1, total_trades)

        gross_profit = sum(t.pnl_usd for t in wins)
        gross_loss = abs(sum(t.pnl_usd for t in losses))
        profit_factor = gross_profit / max(0.01, gross_loss)

        ret_arr = np.array(returns) if returns else np.zeros(1)
        sr = (
            (np.mean(ret_arr) / (np.std(ret_arr) + 1e-6)) * np.sqrt(252)
            if len(ret_arr) > 1
            else 0.0
        )

        return BacktestReport(
            symbol=symbol,
            timeframe=timeframe,
            total_trades=total_trades,
            win_rate=round(win_rate, 3),
            profit_factor=round(profit_factor, 2),
            sharpe_ratio=round(float(sr), 2),
            max_drawdown_pct=round(max_dd * 100.0, 2),
            net_pnl_usd=round(capital - starting_capital, 2),
            trades=trades,
            return_series=[round(float(r), 4) for r in returns],
        )


# Singleton
sandbox_lab = SandboxLab()
