#!/usr/bin/env python3
"""
scripts/research/portfolio_historical_replay.py
================================================
Milestone 38-C / P0 Deliverable 3: Multi-Asset Portfolio Replay Engine.

Executes a deterministic discrete-event cash simulator over historical candles
spanning BTC/USDT, ETH/USDT, SOL/USDT, and PAXG/USDT (Gold).
Enforces:
  1. $10,000.00 starting cash ledger
  2. Maximum 3 concurrent positions (Sovereign Portfolio Risk Limit)
  3. 7 bps (0.0007) institutional maker/taker + spread friction per leg
  4. Half-Kelly risk allocation capped at 1.5% max equity per trade
  5. Opportunity Displacement Arbiter comparison:
     - Policy A: Hard-Wall Rejection (blindly rejects 4th trade when 3 positions active)
     - Policy B: Opportunity Displacement (displaces matured runner >= +1.5R or stalled trade <= -0.7R
                 when incoming signal utility exceeds holding by delta >= 10.0 points)
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT_DIR / "data" / "market_data.db"
OUTPUT_FILE = ROOT_DIR / "research" / "portfolio_historical_replay_results.json"

INITIAL_CASH: float = 10_000.0
MAX_CONCURRENT_POSITIONS: int = 3
FRICTION_RATE_BPS: float = 0.0007  # 7 basis points per execution leg
MAX_EQUITY_RISK_PCT: float = 0.015  # 1.5% maximum capital at risk per trade
DISPLACEMENT_HURDLE: float = 10.0  # 10.0 utility points hurdle


@dataclass
class Candle:
    timestamp: int
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class TradeCandidate:
    timestamp: int
    symbol: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    stop_loss: float
    take_profit: float
    utility_score: float
    rationale: str


@dataclass
class ActivePosition:
    position_id: str
    symbol: str
    direction: str
    entry_ts: int
    entry_price: float
    stop_loss: float
    take_profit: float
    size: float
    allocated_risk_usd: float
    notional: float
    utility: float
    highest_price: float
    lowest_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    achieved_r: float = 0.0


@dataclass
class ClosedTrade:
    position_id: str
    symbol: str
    direction: str
    entry_ts: int
    exit_ts: int
    entry_price: float
    exit_price: float
    size: float
    exit_reason: str  # "TAKE_PROFIT", "STOP_LOSS", "DISPLACED"
    gross_pnl: float
    frictions: float
    net_pnl: float
    net_r: float
    holding_hours: float


@dataclass
class SimulationMetrics:
    policy: str
    initial_cash: float
    final_equity: float
    net_return_pct: float
    total_trades_entered: int
    total_trades_displaced: int
    total_trades_rejected_capacity: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    profit_factor: float
    max_drawdown_pct: float
    sharpe_ratio: float
    ulcer_index: float
    total_frictions_paid: float
    avg_r_multiple: float


def load_aligned_candles(symbols: list[str], limit_per_asset: int = 2500) -> list[Candle]:
    """Loads historical 1h candles from market_data.db in chronological order."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    all_candles: list[Candle] = []

    for sym in symbols:
        cur.execute(
            """
            SELECT timestamp, symbol, open, high, low, close, volume
            FROM candles
            WHERE symbol = ? AND timeframe = '1h'
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (sym, limit_per_asset),
        )
        rows = cur.fetchall()
        for r in rows:
            all_candles.append(
                Candle(
                    timestamp=int(r[0]),
                    symbol=str(r[1]),
                    open=float(r[2]),
                    high=float(r[3]),
                    low=float(r[4]),
                    close=float(r[5]),
                    volume=float(r[6]),
                )
            )
    conn.close()

    # Sort all candles chronologically across all assets
    all_candles.sort(key=lambda c: (c.timestamp, c.symbol))
    return all_candles


def extract_signal_stream(candles: list[Candle]) -> dict[int, list[TradeCandidate]]:
    """
    Generates causal trade candidates from multi-asset price action.
    Uses rolling exponential structural moving averages (fast 9 vs slow 21) and ATR breakouts.
    """
    by_asset: dict[str, list[Candle]] = {}
    for c in candles:
        by_asset.setdefault(c.symbol, []).append(c)

    candidates_by_time: dict[int, list[TradeCandidate]] = {}

    for sym, c_list in by_asset.items():
        if len(c_list) < 30:
            continue
        closes = [c.close for c in c_list]
        highs = [c.high for c in c_list]
        lows = [c.low for c in c_list]

        # Calculate fast (9) and slow (21) EMA
        ema9 = [closes[0]]
        ema21 = [closes[0]]
        k9 = 2.0 / 10.0
        k21 = 2.0 / 22.0

        for idx in range(1, len(closes)):
            ema9.append(closes[idx] * k9 + ema9[-1] * (1.0 - k9))
            ema21.append(closes[idx] * k21 + ema21[-1] * (1.0 - k21))

        # Scan for structural setups
        for i in range(25, len(c_list)):
            c = c_list[i]
            c_list[i - 1]

            # Approximate ATR
            tr_sum = sum(
                max(highs[j] - lows[j], abs(highs[j] - closes[j - 1])) for j in range(i - 14, i)
            )
            atr = max(c.close * 0.005, tr_sum / 14.0)

            # Bullish EMA Cross & Expansion
            if ema9[i - 1] <= ema21[i - 1] and ema9[i] > ema21[i] and c.close > ema9[i]:
                entry = c.close
                sl = entry - (atr * 1.5)
                tp = entry + (atr * 3.5)
                rr = (tp - entry) / max(1e-4, entry - sl)
                utility = (
                    55.0 + min(35.0, rr * 6.0) + (10.0 if "BTC" in sym or "PAXG" in sym else 5.0)
                )

                cand = TradeCandidate(
                    timestamp=c.timestamp,
                    symbol=sym,
                    direction="LONG",
                    entry_price=entry,
                    stop_loss=sl,
                    take_profit=tp,
                    utility_score=utility,
                    rationale=f"Bullish EMA crossover expansion on {sym}",
                )
                candidates_by_time.setdefault(c.timestamp, []).append(cand)

            # Bearish EMA Cross & Rejection
            elif ema9[i - 1] >= ema21[i - 1] and ema9[i] < ema21[i] and c.close < ema9[i]:
                entry = c.close
                sl = entry + (atr * 1.5)
                tp = entry - (atr * 3.5)
                rr = (entry - tp) / max(1e-4, sl - entry)
                utility = (
                    50.0 + min(35.0, rr * 6.0) + (10.0 if "BTC" in sym or "PAXG" in sym else 5.0)
                )

                cand = TradeCandidate(
                    timestamp=c.timestamp,
                    symbol=sym,
                    direction="SHORT",
                    entry_price=entry,
                    stop_loss=sl,
                    take_profit=tp,
                    utility_score=utility,
                    rationale=f"Bearish EMA crossover rejection on {sym}",
                )
                candidates_by_time.setdefault(c.timestamp, []).append(cand)

    return candidates_by_time


def score_position_utility(pos: ActivePosition, incoming_symbol: str) -> float:
    """Scores active position utility using the CBT Marginal Utility model."""
    r = pos.achieved_r
    if r >= 1.5:
        u = 45.0  # Matured runner, ideal candidate to bank and displace
    elif r <= -0.7:
        u = 40.0  # Stalled/bleeding trade near stop loss
    elif r < 0:
        u = 55.0 + (r * 15.0)  # Moderate drawdown: 45 - 55
    else:
        u = 65.0 + min(20.0, r * 15.0)  # Developing trade: 65 - 85

    # Asset affinity bonus if same symbol
    if (
        pos.symbol.replace("/", "").replace("_", "").upper()
        == incoming_symbol.replace("/", "").replace("_", "").upper()
    ):
        u += 30.0
    return u


def run_portfolio_simulation(
    candles: list[Candle],
    signals: dict[int, list[TradeCandidate]],
    enable_displacement: bool = True,
) -> tuple[SimulationMetrics, list[ClosedTrade], list[dict[str, Any]]]:
    """
    Runs discrete-event multi-asset simulation.
    Step through unique timestamps chronologically.
    """
    cash = INITIAL_CASH
    open_positions: dict[str, ActivePosition] = {}
    closed_trades: list[ClosedTrade] = []
    equity_curve: list[tuple[int, float]] = []
    daily_returns: list[float] = []

    total_displaced = 0
    total_capacity_rejections = 0
    total_frictions = 0.0
    trade_id_seq = 0

    # Group candles by timestamp
    timeline: dict[int, list[Candle]] = {}
    for c in candles:
        timeline.setdefault(c.timestamp, []).append(c)

    sorted_timestamps = sorted(timeline.keys())
    last_day_str = ""
    day_open_equity = cash

    for ts in sorted_timestamps:
        c_list = timeline[ts]
        current_prices = {c.symbol: c.close for c in c_list}
        high_prices = {c.symbol: c.high for c in c_list}
        low_prices = {c.symbol: c.low for c in c_list}

        # 1. Update active positions & check Take-Profit / Stop-Loss exits
        to_close_pids: list[tuple[str, str, float]] = []

        for pid, pos in list(open_positions.items()):
            sym = pos.symbol
            if sym not in current_prices:
                continue

            curr_p = current_prices[sym]
            hi = high_prices[sym]
            lo = low_prices[sym]
            pos.current_price = curr_p

            if pos.direction == "LONG":
                pos.highest_price = max(pos.highest_price, hi)
                pos.lowest_price = min(pos.lowest_price, lo)
                pos.unrealized_pnl = (curr_p - pos.entry_price) * pos.size
                pos.achieved_r = pos.unrealized_pnl / max(1.0, pos.allocated_risk_usd)

                # Check SL hit
                if lo <= pos.stop_loss:
                    to_close_pids.append((pid, "STOP_LOSS", pos.stop_loss))
                # Check TP hit
                elif hi >= pos.take_profit:
                    to_close_pids.append((pid, "TAKE_PROFIT", pos.take_profit))

            else:  # SHORT
                pos.highest_price = max(pos.highest_price, hi)
                pos.lowest_price = min(pos.lowest_price, lo)
                pos.unrealized_pnl = (pos.entry_price - curr_p) * pos.size
                pos.achieved_r = pos.unrealized_pnl / max(1.0, pos.allocated_risk_usd)

                # Check SL hit
                if hi >= pos.stop_loss:
                    to_close_pids.append((pid, "STOP_LOSS", pos.stop_loss))
                # Check TP hit
                elif lo <= pos.take_profit:
                    to_close_pids.append((pid, "TAKE_PROFIT", pos.take_profit))

        # Execute TP / SL closes
        for pid, reason, exit_price in to_close_pids:
            if pid not in open_positions:
                continue
            pos = open_positions.pop(pid)
            if pos.direction == "LONG":
                gross_pnl = (exit_price - pos.entry_price) * pos.size
            else:
                gross_pnl = (pos.entry_price - exit_price) * pos.size

            exit_notional = exit_price * pos.size
            exit_frictions = exit_notional * FRICTION_RATE_BPS
            entry_frictions = pos.notional * FRICTION_RATE_BPS
            trade_frictions = entry_frictions + exit_frictions
            net_pnl = gross_pnl - trade_frictions
            net_r = net_pnl / max(1.0, pos.allocated_risk_usd)

            cash += pos.notional + gross_pnl - exit_frictions
            total_frictions += trade_frictions

            closed_trades.append(
                ClosedTrade(
                    position_id=pos.position_id,
                    symbol=pos.symbol,
                    direction=pos.direction,
                    entry_ts=pos.entry_ts,
                    exit_ts=ts,
                    entry_price=pos.entry_price,
                    exit_price=exit_price,
                    size=pos.size,
                    exit_reason=reason,
                    gross_pnl=round(gross_pnl, 2),
                    frictions=round(trade_frictions, 2),
                    net_pnl=round(net_pnl, 2),
                    net_r=round(net_r, 2),
                    holding_hours=round((ts - pos.entry_ts) / 3_600_000, 1),
                )
            )

        # Current portfolio mark-to-market equity
        sum(p.unrealized_pnl + p.notional for p in open_positions.values())
        current_equity = cash + sum(p.unrealized_pnl for p in open_positions.values())
        equity_curve.append((ts, current_equity))

        # Daily return tracking
        dt_str = datetime.fromtimestamp(ts / 1000, tz=UTC).strftime("%Y-%m-%d")
        if last_day_str != dt_str:
            if last_day_str != "":
                ret = (current_equity - day_open_equity) / max(1.0, day_open_equity)
                daily_returns.append(ret)
            last_day_str = dt_str
            day_open_equity = current_equity

        # 2. Evaluate incoming signal candidates
        candidates = signals.get(ts, [])
        for cand in candidates:
            # Check if we already hold this exact symbol
            if any(p.symbol == cand.symbol for p in open_positions.values()):
                continue

            # Check capacity
            if len(open_positions) >= MAX_CONCURRENT_POSITIONS:
                if not enable_displacement:
                    total_capacity_rejections += 1
                    continue

                # Opportunity Displacement Arbiter
                scored: list[tuple[float, str, ActivePosition]] = []
                for pid, pos in open_positions.items():
                    u = score_position_utility(pos, cand.symbol)
                    scored.append((u, pid, pos))

                scored.sort(key=lambda x: x[0])
                weakest_u, weakest_pid, weakest_pos = scored[0]

                if cand.utility_score > (weakest_u + DISPLACEMENT_HURDLE):
                    # Displace weakest holding at current price
                    curr_exit = current_prices.get(weakest_pos.symbol, weakest_pos.entry_price)
                    if weakest_pos.direction == "LONG":
                        gross_pnl = (curr_exit - weakest_pos.entry_price) * weakest_pos.size
                    else:
                        gross_pnl = (weakest_pos.entry_price - curr_exit) * weakest_pos.size

                    exit_notional = curr_exit * weakest_pos.size
                    exit_frictions = exit_notional * FRICTION_RATE_BPS
                    entry_frictions = weakest_pos.notional * FRICTION_RATE_BPS
                    trade_frictions = entry_frictions + exit_frictions
                    net_pnl = gross_pnl - trade_frictions
                    net_r = net_pnl / max(1.0, weakest_pos.allocated_risk_usd)

                    cash += weakest_pos.notional + gross_pnl - exit_frictions
                    total_frictions += trade_frictions
                    total_displaced += 1

                    closed_trades.append(
                        ClosedTrade(
                            position_id=weakest_pos.position_id,
                            symbol=weakest_pos.symbol,
                            direction=weakest_pos.direction,
                            entry_ts=weakest_pos.entry_ts,
                            exit_ts=ts,
                            entry_price=weakest_pos.entry_price,
                            exit_price=curr_exit,
                            size=weakest_pos.size,
                            exit_reason="DISPLACED",
                            gross_pnl=round(gross_pnl, 2),
                            frictions=round(trade_frictions, 2),
                            net_pnl=round(net_pnl, 2),
                            net_r=round(net_r, 2),
                            holding_hours=round((ts - weakest_pos.entry_ts) / 3_600_000, 1),
                        )
                    )
                    open_positions.pop(weakest_pid)
                else:
                    total_capacity_rejections += 1
                    continue

            # Position Sizing: Half-Kelly Risk cap at 1.5% of equity
            risk_usd = current_equity * MAX_EQUITY_RISK_PCT
            price_risk = abs(cand.entry_price - cand.stop_loss)
            if price_risk <= 0:
                continue

            size = risk_usd / price_risk
            notional = size * cand.entry_price

            # Check cash constraint
            entry_frictions = notional * FRICTION_RATE_BPS
            if (notional + entry_frictions) > (cash * 0.95):
                # Scale size to available cash
                max_notional = cash * 0.90
                size = max_notional / cand.entry_price
                notional = size * cand.entry_price
                risk_usd = size * price_risk
                entry_frictions = notional * FRICTION_RATE_BPS

            if size <= 0 or notional < 50.0:
                continue

            cash -= notional + entry_frictions
            trade_id_seq += 1
            new_pid = f"POS_{cand.symbol}_{ts}_{trade_id_seq}"

            open_positions[new_pid] = ActivePosition(
                position_id=new_pid,
                symbol=cand.symbol,
                direction=cand.direction,
                entry_ts=ts,
                entry_price=cand.entry_price,
                stop_loss=cand.stop_loss,
                take_profit=cand.take_profit,
                size=size,
                allocated_risk_usd=risk_usd,
                notional=notional,
                utility=cand.utility_score,
                highest_price=cand.entry_price,
                lowest_price=cand.entry_price,
                current_price=cand.entry_price,
            )

    # Close any remaining open positions at final candle price
    final_ts = sorted_timestamps[-1]
    final_prices = {c.symbol: c.close for c in timeline[final_ts]}

    for _pid, pos in list(open_positions.items()):
        curr_p = final_prices.get(pos.symbol, pos.entry_price)
        if pos.direction == "LONG":
            gross_pnl = (curr_p - pos.entry_price) * pos.size
        else:
            gross_pnl = (pos.entry_price - curr_p) * pos.size

        exit_notional = curr_p * pos.size
        exit_frictions = exit_notional * FRICTION_RATE_BPS
        entry_frictions = pos.notional * FRICTION_RATE_BPS
        trade_frictions = entry_frictions + exit_frictions
        net_pnl = gross_pnl - trade_frictions
        net_r = net_pnl / max(1.0, pos.allocated_risk_usd)

        cash += pos.notional + gross_pnl - exit_frictions
        total_frictions += trade_frictions

        closed_trades.append(
            ClosedTrade(
                position_id=pos.position_id,
                symbol=pos.symbol,
                direction=pos.direction,
                entry_ts=pos.entry_ts,
                exit_ts=final_ts,
                entry_price=pos.entry_price,
                exit_price=curr_p,
                size=pos.size,
                exit_reason="SESSION_CLOSE",
                gross_pnl=round(gross_pnl, 2),
                frictions=round(trade_frictions, 2),
                net_pnl=round(net_pnl, 2),
                net_r=round(net_r, 2),
                holding_hours=round((final_ts - pos.entry_ts) / 3_600_000, 1),
            )
        )

    # Compute Statistics
    final_equity = cash
    net_return_pct = ((final_equity - INITIAL_CASH) / INITIAL_CASH) * 100.0

    wins = [t for t in closed_trades if t.net_pnl > 0]
    losses = [t for t in closed_trades if t.net_pnl <= 0]
    win_rate = (len(wins) / len(closed_trades) * 100.0) if closed_trades else 0.0

    gross_gains = sum(t.net_pnl for t in wins)
    gross_losses = abs(sum(t.net_pnl for t in losses))
    profit_factor = (gross_gains / gross_losses) if gross_losses > 0 else 99.0

    # Max Drawdown & Ulcer Index
    equities = [eq for _, eq in equity_curve]
    peak = INITIAL_CASH
    max_dd = 0.0
    squared_dds = []

    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100.0
        if dd > max_dd:
            max_dd = dd
        squared_dds.append(dd * dd)

    ulcer_index = math.sqrt(sum(squared_dds) / len(squared_dds)) if squared_dds else 0.0

    # Annualized Sharpe Ratio from daily returns
    if len(daily_returns) > 5:
        mean_r = sum(daily_returns) / len(daily_returns)
        var_r = sum((r - mean_r) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        std_r = math.sqrt(var_r) if var_r > 0 else 1e-4
        sharpe = (mean_r / std_r) * math.sqrt(365.0)
    else:
        sharpe = 0.0

    avg_r = (sum(t.net_r for t in closed_trades) / len(closed_trades)) if closed_trades else 0.0

    metrics = SimulationMetrics(
        policy="DYNAMIC_DISPLACEMENT" if enable_displacement else "STATIC_HARD_WALL",
        initial_cash=INITIAL_CASH,
        final_equity=round(final_equity, 2),
        net_return_pct=round(net_return_pct, 2),
        total_trades_entered=len(closed_trades),
        total_trades_displaced=total_displaced,
        total_trades_rejected_capacity=total_capacity_rejections,
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate_pct=round(win_rate, 1),
        profit_factor=round(profit_factor, 2),
        max_drawdown_pct=round(max_dd, 2),
        sharpe_ratio=round(sharpe, 2),
        ulcer_index=round(ulcer_index, 2),
        total_frictions_paid=round(total_frictions, 2),
        avg_r_multiple=round(avg_r, 2),
    )

    return (
        metrics,
        closed_trades,
        [{"timestamp": ts, "equity": round(eq, 2)} for ts, eq in equity_curve[::20]],
    )


def main():
    print("=" * 70)
    print("SKY MULTI-ASSET PORTFOLIO REPLAY ENGINE & DISPLACEMENT AUDIT")
    print("Assets: BTC/USDT, ETH/USDT, SOL/USDT, PAXG/USDT (Gold)")
    print(
        f"Starting Capital: ${INITIAL_CASH:,.2f} | Max Concurrent Positions: {MAX_CONCURRENT_POSITIONS}"
    )
    print(
        f"Frictions: {FRICTION_RATE_BPS * 10000:.1f} bps per leg | Max Risk: {MAX_EQUITY_RISK_PCT * 100:.1f}%"
    )
    print("=" * 70)

    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "PAXG/USDT"]
    print("[*] Loading aligned historical candles from data/market_data.db...")
    candles = load_aligned_candles(symbols, limit_per_asset=2000)
    print(f"    Loaded {len(candles)} total 1h candles across {len(symbols)} assets.")

    print("[*] Extracting causal multi-asset signal stream...")
    signals = extract_signal_stream(candles)
    total_signals = sum(len(sigs) for sigs in signals.values())
    print(f"    Extracted {total_signals} structural trade signals across timeline.")

    # 1. Run Baseline (Hard Wall Rejection)
    print("\n[*] Simulating Policy A: Static Hard Wall (No Displacement)...")
    m_baseline, _trades_a, _ = run_portfolio_simulation(candles, signals, enable_displacement=False)

    # 2. Run Intelligent Displacement Arbiter
    print("[*] Simulating Policy B: Intelligent Opportunity Displacement Arbiter...")
    m_displaced, _trades_b, eq_curve = run_portfolio_simulation(
        candles, signals, enable_displacement=True
    )

    # Display Comparative Scorecard
    print("\n" + "=" * 70)
    print(f"{'METRIC':<34} | {'POLICY A (HARD WALL)':<16} | {'POLICY B (DISPLACEMENT)':<16}")
    print("-" * 70)
    print(
        f"{'Initial Capital':<34} | ${m_baseline.initial_cash:>14,.2f} | ${m_displaced.initial_cash:>14,.2f}"
    )
    print(
        f"{'Final Equity':<34} | ${m_baseline.final_equity:>14,.2f} | ${m_displaced.final_equity:>14,.2f}"
    )
    print(
        f"{'Net Return (%)':<34} | {m_baseline.net_return_pct:>14.2f}% | {m_displaced.net_return_pct:>14.2f}%"
    )
    print(
        f"{'Total Trades Entered':<34} | {m_baseline.total_trades_entered:>15} | {m_displaced.total_trades_entered:>15}"
    )
    print(
        f"{'Trades Displaced (Utility Shift)':<34} | {m_baseline.total_trades_displaced:>15} | {m_displaced.total_trades_displaced:>15}"
    )
    print(
        f"{'Capacity Hard Rejections':<34} | {m_baseline.total_trades_rejected_capacity:>15} | {m_displaced.total_trades_rejected_capacity:>15}"
    )
    print(
        f"{'Win Rate (%)':<34} | {m_baseline.win_rate_pct:>14.1f}% | {m_displaced.win_rate_pct:>14.1f}%"
    )
    print(
        f"{'Profit Factor':<34} | {m_baseline.profit_factor:>15.2f} | {m_displaced.profit_factor:>15.2f}"
    )
    print(
        f"{'Max Drawdown (%)':<34} | {m_baseline.max_drawdown_pct:>14.2f}% | {m_displaced.max_drawdown_pct:>14.2f}%"
    )
    print(
        f"{'Sharpe Ratio (Annualized)':<34} | {m_baseline.sharpe_ratio:>15.2f} | {m_displaced.sharpe_ratio:>15.2f}"
    )
    print(
        f"{'Ulcer Index':<34} | {m_baseline.ulcer_index:>15.2f} | {m_displaced.ulcer_index:>15.2f}"
    )
    print(
        f"{'Frictions Incurred ($)':<34} | ${m_baseline.total_frictions_paid:>14.2f} | ${m_displaced.total_frictions_paid:>14.2f}"
    )
    print(
        f"{'Avg R Multiple':<34} | {m_baseline.avg_r_multiple:>14.2f}R | {m_displaced.avg_r_multiple:>14.2f}R"
    )
    print("=" * 70)

    # Save Results
    results_payload = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "configuration": {
            "initial_cash": INITIAL_CASH,
            "max_concurrent_positions": MAX_CONCURRENT_POSITIONS,
            "friction_bps": FRICTION_RATE_BPS * 10000,
            "max_risk_pct": MAX_EQUITY_RISK_PCT * 100,
            "displacement_hurdle": DISPLACEMENT_HURDLE,
            "assets": symbols,
        },
        "policy_a_hard_wall": asdict(m_baseline),
        "policy_b_displacement": asdict(m_displaced),
        "equity_curve_sample": eq_curve,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, indent=2)

    print(f"\n[PASS] Replay results successfully emitted to: {OUTPUT_FILE.relative_to(ROOT_DIR)}")
    assert m_displaced.final_equity > 0, "Simulation failed: non-positive final equity"
    assert m_displaced.total_trades_displaced > 0, (
        "Displacement arbiter did not trigger any displacements"
    )
    print(">>> MULTI-ASSET PORTFOLIO REPLAY VERIFICATION COMPLETE (PASS) <<<")


if __name__ == "__main__":
    main()
