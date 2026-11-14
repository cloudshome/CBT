"""
Faithful Historical Replay of SKY Intelligence Production Orchestrator.
Evaluates the actual 12-stage production decision engine (core/sky_intelligence/orchestrator.py)
across BTC, ETH, and SOL on non-overlapping multi-year windows with realistic execution frictions.

Key Invariants:
- Zero Lookahead: Next-open execution (c_next.open) for all fills.
- 3-Tier Frictions: Maker/taker fee (7 bps), half-spread, slippage, and funding cost.
- Pessimistic Intraday Resolution: When SL and TP are within the same bar, SL is hit first.
- Strict Risk Gates: Half-Kelly sizing capped at 1.5% risk, max notional 100% equity.
- Causal Bayesian Learning: Only historically closed trades prior to simulated bar are visible.
- Policy Comparison: Policy A (FCFS) vs Policy B (Opportunity Displacement Arbiter).
"""

from __future__ import annotations

import bisect
import json
import logging
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sky_intelligence import DecisionAction, sky_orchestrator

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("orchestrator_replay")


@dataclass
class AssetFrictionConfig:
    half_spread_bps: float
    slippage_bps: float
    taker_fee_bps: float = 7.0  # 7 bps institutional VIP taker
    funding_rate_8h: float = 0.0001  # 1 bp / 8h baseline funding


ASSET_CONFIGS = {
    "BTC/USDT": AssetFrictionConfig(half_spread_bps=1.0, slippage_bps=2.0),
    "ETH/USDT": AssetFrictionConfig(half_spread_bps=1.5, slippage_bps=2.5),
    "SOL/USDT": AssetFrictionConfig(half_spread_bps=3.0, slippage_bps=4.0),
}


@dataclass
class Position:
    position_id: str
    symbol: str
    direction: str  # 'LONG' or 'SHORT'
    setup_type: str
    confluence_score: float
    net_ev_r: float
    risk_reward_ratio: float
    entry_bar_idx: int
    entry_timestamp: int
    entry_price: float
    stop_loss: float
    take_profit: float
    size_units: float
    notional_usd: float
    risk_budget_usd: float
    opened_at_equity: float
    holding_bars: int = 0
    fees_paid_usd: float = 0.0
    slippage_paid_usd: float = 0.0
    funding_paid_usd: float = 0.0
    status: str = "OPEN"  # 'OPEN', 'CLOSED'
    exit_timestamp: int | None = None
    exit_price: float | None = None
    exit_reason: str | None = None  # 'TP', 'SL', 'DISPLACED', 'TIMEOUT'
    realized_pnl_usd: float = 0.0
    realized_r: float = 0.0


@dataclass
class DisplacementRecord:
    timestamp: int
    displaced_symbol: str
    displaced_setup: str
    displaced_ev_r: float
    displaced_pnl_at_exit: float
    displaced_realized_r: float
    counterfactual_final_pnl: float
    counterfactual_final_r: float
    counterfactual_outcome: str  # 'WOULD_HAVE_WON', 'WOULD_HAVE_LOST'
    displacing_symbol: str
    displacing_setup: str
    displacing_ev_r: float
    displacing_realized_pnl: float
    displacing_realized_r: float
    net_r_delta: float


def load_candles(
    db_path: str, symbol: str, timeframe: str, start_ms: int, end_ms: int
) -> list[dict[str, Any]]:
    """Loads candles with lookback padding before start_ms."""
    # Lookback padding: 120 hours (5 days)
    pad_ms = 120 * 3600 * 1000
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT timestamp, open, high, low, close, volume
        FROM candles
        WHERE symbol = ? AND timeframe = ? AND timestamp >= ? AND timestamp <= ?
        ORDER BY timestamp ASC
        """,
        (symbol, timeframe, start_ms - pad_ms, end_ms + (48 * 3600 * 1000)),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "timestamp": int(r[0]),
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
            "volume": float(r[5]),
        }
        for r in rows
    ]


class ReplayPortfolioEngine:
    def __init__(
        self,
        policy_name: str,
        initial_equity: float = 100_000.0,
        max_positions: int = 3,
        use_displacement: bool = False,
        displacement_ev_hurdle_r: float = 0.10,
    ) -> None:
        self.policy_name = policy_name
        self.initial_equity = initial_equity
        self.equity = initial_equity
        self.max_positions = max_positions
        self.use_displacement = use_displacement
        self.displacement_ev_hurdle_r = displacement_ev_hurdle_r

        self.active_positions: dict[str, Position] = {}  # symbol -> Position
        self.closed_positions: list[Position] = []
        self.displacements: list[DisplacementRecord] = []
        self.equity_curve: list[tuple[int, float]] = []
        self.rejected_signals_count = 0

    def get_portfolio_risk_utilization(self) -> float:
        total_risk = sum(p.risk_budget_usd for p in self.active_positions.values())
        return total_risk / max(1.0, self.equity)

    def process_bar_exits(self, current_ts: int, candle_map: dict[str, dict[str, Any]]) -> None:
        """Evaluates active positions for SL / TP / Timeout exits on the current bar."""
        to_close = []
        for sym, pos in list(self.active_positions.items()):
            c = candle_map.get(sym)
            if not c:
                continue

            pos.holding_bars += 1
            high = c["high"]
            low = c["low"]
            cfg = ASSET_CONFIGS.get(sym, AssetFrictionConfig(2.0, 2.0))

            # Pro-rate funding fee (1h bar = 1/8 of 8h funding rate)
            funding_fee = pos.notional_usd * (cfg.funding_rate_8h / 8.0)
            pos.funding_paid_usd += funding_fee
            self.equity -= funding_fee

            hit_sl = False
            hit_tp = False

            if pos.direction == "LONG":
                if low <= pos.stop_loss:
                    hit_sl = True
                if high >= pos.take_profit:
                    hit_tp = True
            else:  # SHORT
                if high >= pos.stop_loss:
                    hit_sl = True
                if low <= pos.take_profit:
                    hit_tp = True

            # Ambiguity handling: if both SL and TP touched on same bar, assume pessimistic SL hit
            if hit_sl:
                exit_price = pos.stop_loss
                reason = "SL"
            elif hit_tp:
                exit_price = pos.take_profit
                reason = "TP"
            elif pos.holding_bars >= 120:  # Timeout after 5 days (120 hours)
                exit_price = c["close"]
                reason = "TIMEOUT"
            else:
                continue

            # Apply exit friction
            half_spread_frac = cfg.half_spread_bps / 10000.0
            slippage_frac = cfg.slippage_bps / 10000.0
            taker_fee_frac = cfg.taker_fee_bps / 10000.0

            if pos.direction == "LONG":
                effective_exit = exit_price * (1.0 - half_spread_frac - slippage_frac)
                gross_pnl = (effective_exit - pos.entry_price) * pos.size_units
            else:
                effective_exit = exit_price * (1.0 + half_spread_frac + slippage_frac)
                gross_pnl = (pos.entry_price - effective_exit) * pos.size_units

            exit_fee = (effective_exit * pos.size_units) * taker_fee_frac
            pos.fees_paid_usd += exit_fee
            pos.slippage_paid_usd += (exit_price * pos.size_units) * (
                half_spread_frac + slippage_frac
            )

            net_pnl = gross_pnl - exit_fee
            # True net trade PnL incorporates all transaction fees and accrued funding
            true_trade_net_pnl = gross_pnl - pos.fees_paid_usd - pos.funding_paid_usd
            pos.realized_pnl_usd = true_trade_net_pnl
            pos.realized_r = true_trade_net_pnl / max(1.0, pos.risk_budget_usd)
            pos.exit_timestamp = current_ts
            pos.exit_price = effective_exit
            pos.exit_reason = reason
            pos.status = "CLOSED"

            self.equity += net_pnl
            self.closed_positions.append(pos)
            to_close.append(sym)

        for sym in to_close:
            del self.active_positions[sym]

    def try_open_position(
        self,
        current_ts: int,
        symbol: str,
        direction: str,
        setup_type: str,
        confluence_score: float,
        net_ev_r: float,
        rr: float,
        entry_price_ideal: float,
        stop_loss: float,
        take_profit: float,
        kelly_fraction: float,
        next_bar_open: float,
        future_candles: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Executes a trade on the subsequent bar open with realistic execution frictions."""
        # Check if already active in this symbol
        if symbol in self.active_positions:
            return False

        cfg = ASSET_CONFIGS.get(symbol, AssetFrictionConfig(2.0, 2.0))
        half_spread_frac = cfg.half_spread_bps / 10000.0
        slippage_frac = cfg.slippage_bps / 10000.0
        taker_fee_frac = cfg.taker_fee_bps / 10000.0

        # Next open fill with execution friction
        if direction == "LONG":
            fill_price = next_bar_open * (1.0 + half_spread_frac + slippage_frac)
        else:
            fill_price = next_bar_open * (1.0 - half_spread_frac - slippage_frac)

        stop_dist_pct = abs(fill_price - stop_loss) / max(fill_price, 1e-4)
        if stop_dist_pct < 0.003:  # Too tight stop, skip to avoid excessive leverage
            return False

        # Half-Kelly position sizing
        risk_budget = self.equity * min(0.015, max(0.005, kelly_fraction))
        notional_usd = min(self.equity * 0.95, risk_budget / stop_dist_pct)
        size_units = notional_usd / fill_price

        entry_fee = notional_usd * taker_fee_frac
        self.equity -= entry_fee

        new_pos = Position(
            position_id=f"{symbol}_{current_ts}",
            symbol=symbol,
            direction=direction,
            setup_type=setup_type,
            confluence_score=confluence_score,
            net_ev_r=net_ev_r,
            risk_reward_ratio=rr,
            entry_bar_idx=0,
            entry_timestamp=current_ts,
            entry_price=fill_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            size_units=size_units,
            notional_usd=notional_usd,
            risk_budget_usd=risk_budget,
            opened_at_equity=self.equity,
            fees_paid_usd=entry_fee,
            slippage_paid_usd=notional_usd * (half_spread_frac + slippage_frac),
        )

        # Capacity check
        if len(self.active_positions) < self.max_positions:
            self.active_positions[symbol] = new_pos
            return True

        # Capacity reached: evaluate displacement if Policy B
        if not self.use_displacement:
            self.rejected_signals_count += 1
            return False

        # Find position with lowest Net EV
        lowest_sym = min(
            self.active_positions.keys(), key=lambda s: self.active_positions[s].net_ev_r
        )
        lowest_pos = self.active_positions[lowest_sym]

        ev_delta = net_ev_r - lowest_pos.net_ev_r
        if ev_delta < self.displacement_ev_hurdle_r:
            self.rejected_signals_count += 1
            return False

        # Perform Displacement: Close lowest_pos immediately at current market price
        del self.active_positions[lowest_sym]

        # Close displaced position
        displaced_cfg = ASSET_CONFIGS.get(lowest_sym, AssetFrictionConfig(2.0, 2.0))
        d_spread = displaced_cfg.half_spread_bps / 10000.0
        d_slip = displaced_cfg.slippage_bps / 10000.0
        d_taker = displaced_cfg.taker_fee_bps / 10000.0

        d_exit_raw = next_bar_open  # close at current bar open
        if lowest_pos.direction == "LONG":
            d_exit = d_exit_raw * (1.0 - d_spread - d_slip)
            d_gross = (d_exit - lowest_pos.entry_price) * lowest_pos.size_units
        else:
            d_exit = d_exit_raw * (1.0 + d_spread + d_slip)
            d_gross = (lowest_pos.entry_price - d_exit) * lowest_pos.size_units

        d_fee = (d_exit * lowest_pos.size_units) * d_taker
        lowest_pos.fees_paid_usd += d_fee
        d_net = d_gross - d_fee

        true_displaced_net_pnl = d_gross - lowest_pos.fees_paid_usd - lowest_pos.funding_paid_usd
        lowest_pos.realized_pnl_usd = true_displaced_net_pnl
        lowest_pos.realized_r = true_displaced_net_pnl / max(1.0, lowest_pos.risk_budget_usd)
        lowest_pos.exit_timestamp = current_ts
        lowest_pos.exit_price = d_exit
        lowest_pos.exit_reason = "DISPLACED"
        lowest_pos.status = "CLOSED"

        self.equity += d_net
        self.closed_positions.append(lowest_pos)

        # Open displacing position
        self.active_positions[symbol] = new_pos

        # Trace counterfactual outcome of displaced position
        cf_r, cf_pnl, cf_outcome = self._eval_counterfactual(lowest_pos, future_candles or [])

        self.displacements.append(
            DisplacementRecord(
                timestamp=current_ts,
                displaced_symbol=lowest_pos.symbol,
                displaced_setup=lowest_pos.setup_type,
                displaced_ev_r=lowest_pos.net_ev_r,
                displaced_pnl_at_exit=d_net,
                displaced_realized_r=lowest_pos.realized_r,
                counterfactual_final_pnl=cf_pnl,
                counterfactual_final_r=cf_r,
                counterfactual_outcome=cf_outcome,
                displacing_symbol=new_pos.symbol,
                displacing_setup=new_pos.setup_type,
                displacing_ev_r=new_pos.net_ev_r,
                displacing_realized_pnl=0.0,  # updated later
                displacing_realized_r=0.0,
                net_r_delta=0.0,
            )
        )
        return True

    def _eval_counterfactual(
        self, pos: Position, remaining_candles: list[dict[str, Any]]
    ) -> tuple[float, float, str]:
        """Calculates what would have happened if the displaced position had been held to TP/SL."""
        for c in remaining_candles:
            high = c["high"]
            low = c["low"]
            if pos.direction == "LONG":
                if low <= pos.stop_loss:
                    return -1.0, -pos.risk_budget_usd, "WOULD_HAVE_LOST"
                if high >= pos.take_profit:
                    return (
                        pos.risk_reward_ratio,
                        pos.risk_budget_usd * pos.risk_reward_ratio,
                        "WOULD_HAVE_WON",
                    )
            else:
                if high >= pos.stop_loss:
                    return -1.0, -pos.risk_budget_usd, "WOULD_HAVE_LOST"
                if low <= pos.take_profit:
                    return (
                        pos.risk_reward_ratio,
                        pos.risk_budget_usd * pos.risk_reward_ratio,
                        "WOULD_HAVE_WON",
                    )
        return 0.0, 0.0, "TIMEOUT_UNDETERMINED"


def run_window_simulation(
    db_path: str,
    window_name: str,
    start_dt_str: str,
    end_dt_str: str,
) -> dict[str, Any]:
    """Runs a complete synchronized chronological simulation of Policy A and Policy B across BTC, ETH, SOL."""
    start_ms = int(datetime.fromisoformat(start_dt_str).replace(tzinfo=UTC).timestamp() * 1000)
    end_ms = int(datetime.fromisoformat(end_dt_str).replace(tzinfo=UTC).timestamp() * 1000)

    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    candles_1h: dict[str, list[dict[str, Any]]] = {}
    candles_4h: dict[str, list[dict[str, Any]]] = {}
    ts_4h: dict[str, list[int]] = {}

    for sym in symbols:
        c1 = load_candles(db_path, sym, "1h", start_ms, end_ms)
        c4 = load_candles(db_path, sym, "4h", start_ms, end_ms)
        candles_1h[sym] = c1
        candles_4h[sym] = c4
        ts_4h[sym] = [c["timestamp"] for c in c4]

    # Find common 1h timestamps within [start_ms, end_ms]
    common_ts_set = set(
        c["timestamp"] for c in candles_1h["BTC/USDT"] if start_ms <= c["timestamp"] <= end_ms
    )
    for sym in symbols[1:]:
        common_ts_set.intersection_update(
            c["timestamp"] for c in candles_1h[sym] if start_ms <= c["timestamp"] <= end_ms
        )

    sorted_timeline = sorted(list(common_ts_set))
    if not sorted_timeline:
        return {"error": f"No common timestamps found for {window_name}"}

    # Map timestamps to candle index for O(1) retrieval
    c1h_idx_map: dict[str, dict[int, int]] = {
        sym: {c["timestamp"]: idx for idx, c in enumerate(candles_1h[sym])} for sym in symbols
    }

    port_a = ReplayPortfolioEngine(policy_name="Policy A (FCFS)", use_displacement=False)
    port_b = ReplayPortfolioEngine(policy_name="Policy B (Displacement)", use_displacement=True)

    total_steps = len(sorted_timeline) - 1
    t0 = time.time()

    for _step, curr_ts in enumerate(sorted_timeline[:-1]):
        # Current bar candles for exit processing
        bar_candle_map = {sym: candles_1h[sym][c1h_idx_map[sym][curr_ts]] for sym in symbols}

        port_a.process_bar_exits(curr_ts, bar_candle_map)
        port_b.process_bar_exits(curr_ts, bar_candle_map)

        port_a.equity_curve.append((curr_ts, port_a.equity))
        port_b.equity_curve.append((curr_ts, port_b.equity))

        # Evaluate signals across all 3 assets
        signals_this_bar = []
        for sym in symbols:
            idx = c1h_idx_map[sym][curr_ts]
            sub_1h = candles_1h[sym][max(0, idx - 60) : idx + 1]

            # 4H MTF context
            idx_4h = bisect.bisect_right(ts_4h[sym], curr_ts)
            sub_4h = candles_4h[sym][max(0, idx_4h - 30) : idx_4h]
            tf_map = {"1h": sub_1h, "4h": sub_4h}

            out = sky_orchestrator.analyze_market(
                symbol=sym,
                timeframe="1h",
                candles=sub_1h,
                candles_by_tf=tf_map,
                simulated_now_ms=curr_ts,
            )

            if out.decision in (DecisionAction.LONG, DecisionAction.SHORT) and out.setup_qualified:
                next_open = candles_1h[sym][idx + 1]["open"]
                future_c = candles_1h[sym][idx + 1 : idx + 120]
                signals_this_bar.append((sym, out, next_open, future_c))

        # Sort incoming signals by Net EV descending
        signals_this_bar.sort(key=lambda s: s[1].net_ev_r, reverse=True)

        for sym, out, next_open, future_c in signals_this_bar:
            dossier = out.explanation_dossier
            direction = out.decision.value
            setup_type = dossier.get("setup_type", "UNKNOWN")
            confluence = dossier.get("confluence_score", 75.0)
            net_ev = out.net_ev_r
            rr = dossier.get("risk_reward_ratio", 2.0)
            entry_p = dossier.get("entry_price", next_open)
            sl = dossier.get("invalidation_sl", next_open * 0.98)
            tp = dossier.get("target_tp", next_open * 1.04)
            kelly = out.kelly_fraction

            port_a.try_open_position(
                current_ts=curr_ts,
                symbol=sym,
                direction=direction,
                setup_type=setup_type,
                confluence_score=confluence,
                net_ev_r=net_ev,
                rr=rr,
                entry_price_ideal=entry_p,
                stop_loss=sl,
                take_profit=tp,
                kelly_fraction=kelly,
                next_bar_open=next_open,
            )

            port_b.try_open_position(
                current_ts=curr_ts,
                symbol=sym,
                direction=direction,
                setup_type=setup_type,
                confluence_score=confluence,
                net_ev_r=net_ev,
                rr=rr,
                entry_price_ideal=entry_p,
                stop_loss=sl,
                take_profit=tp,
                kelly_fraction=kelly,
                next_bar_open=next_open,
                future_candles=future_c,
            )

    # Final mark-to-market settlement of any active positions at period close
    final_ts = sorted_timeline[-1]
    final_bar_map = {sym: candles_1h[sym][c1h_idx_map[sym][final_ts]] for sym in symbols}
    for port in (port_a, port_b):
        for sym, pos in list(port.active_positions.items()):
            c = final_bar_map.get(sym)
            if not c:
                continue
            cfg = ASSET_CONFIGS.get(sym, AssetFrictionConfig(2.0, 2.0))
            half_spread_frac = cfg.half_spread_bps / 10000.0
            slippage_frac = cfg.slippage_bps / 10000.0
            taker_fee_frac = cfg.taker_fee_bps / 10000.0
            exit_p = c["close"]

            if pos.direction == "LONG":
                eff_exit = exit_p * (1.0 - half_spread_frac - slippage_frac)
                gross_pnl = (eff_exit - pos.entry_price) * pos.size_units
            else:
                eff_exit = exit_p * (1.0 + half_spread_frac + slippage_frac)
                gross_pnl = (pos.entry_price - eff_exit) * pos.size_units

            exit_fee = (eff_exit * pos.size_units) * taker_fee_frac
            pos.fees_paid_usd += exit_fee
            pos.slippage_paid_usd += (exit_p * pos.size_units) * (half_spread_frac + slippage_frac)

            true_net_pnl = gross_pnl - pos.fees_paid_usd - pos.funding_paid_usd
            pos.realized_pnl_usd = true_net_pnl
            pos.realized_r = true_net_pnl / max(1.0, pos.risk_budget_usd)
            pos.exit_timestamp = final_ts
            pos.exit_price = eff_exit
            pos.exit_reason = "PERIOD_END_SETTLEMENT"
            pos.status = "CLOSED"

            port.equity += gross_pnl - exit_fee
            port.closed_positions.append(pos)
            del port.active_positions[sym]

    elapsed = time.time() - t0

    # Calculate final displacement deltas
    for disp in port_b.displacements:
        # Match displacing trade outcome from closed positions
        for p in port_b.closed_positions:
            if p.symbol == disp.displacing_symbol and p.entry_timestamp == disp.timestamp:
                disp.displacing_realized_pnl = p.realized_pnl_usd
                disp.displacing_realized_r = p.realized_r
                disp.net_r_delta = disp.displacing_realized_r - disp.counterfactual_final_r
                break

    def compile_stats(port: ReplayPortfolioEngine) -> dict[str, Any]:
        trades = port.closed_positions
        n_trades = len(trades)
        wins = [t for t in trades if t.realized_pnl_usd > 0]
        losses = [t for t in trades if t.realized_pnl_usd <= 0]
        n_wins = len(wins)
        n_losses = len(losses)
        win_rate = (n_wins / n_trades) if n_trades > 0 else 0.0

        gross_profit = sum(t.realized_pnl_usd for t in wins)
        gross_loss = abs(sum(t.realized_pnl_usd for t in losses))
        profit_factor = (
            (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        )

        total_return_pct = ((port.equity - port.initial_equity) / port.initial_equity) * 100.0

        # Maximum Drawdown calculation
        peak = port.initial_equity
        max_dd_pct = 0.0
        for _, eq in port.equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100.0
            if dd > max_dd_pct:
                max_dd_pct = dd

        total_fees = sum(t.fees_paid_usd for t in trades)
        total_slippage = sum(t.slippage_paid_usd for t in trades)
        total_funding = sum(t.funding_paid_usd for t in trades)

        avg_r = (sum(t.realized_r for t in trades) / n_trades) if n_trades > 0 else 0.0
        avg_holding = (sum(t.holding_bars for t in trades) / n_trades) if n_trades > 0 else 0.0

        # Asset breakdown
        asset_breakdown = {}
        for sym in symbols:
            s_trades = [t for t in trades if t.symbol == sym]
            s_wins = [t for t in s_trades if t.realized_pnl_usd > 0]
            asset_breakdown[sym] = {
                "trades": len(s_trades),
                "win_rate": (len(s_wins) / len(s_trades)) if s_trades else 0.0,
                "pnl_usd": sum(t.realized_pnl_usd for t in s_trades),
                "avg_r": (sum(t.realized_r for t in s_trades) / len(s_trades)) if s_trades else 0.0,
            }

        # Setup breakdown
        setup_breakdown = {}
        for t in trades:
            st = t.setup_type
            if st not in setup_breakdown:
                setup_breakdown[st] = {"trades": 0, "wins": 0, "pnl_usd": 0.0, "total_r": 0.0}
            setup_breakdown[st]["trades"] += 1
            if t.realized_pnl_usd > 0:
                setup_breakdown[st]["wins"] += 1
            setup_breakdown[st]["pnl_usd"] += t.realized_pnl_usd
            setup_breakdown[st]["total_r"] += t.realized_r

        for _st, data in setup_breakdown.items():
            data["win_rate"] = (data["wins"] / data["trades"]) if data["trades"] else 0.0
            data["avg_r"] = (data["total_r"] / data["trades"]) if data["trades"] else 0.0

        return {
            "initial_equity": port.initial_equity,
            "final_equity": round(port.equity, 2),
            "net_pnl_usd": round(port.equity - port.initial_equity, 2),
            "total_return_pct": round(total_return_pct, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "profit_factor": round(profit_factor, 3),
            "win_rate_pct": round(win_rate * 100.0, 2),
            "trade_count": n_trades,
            "win_count": n_wins,
            "loss_count": n_losses,
            "average_r": round(avg_r, 3),
            "average_holding_hours": round(avg_holding, 1),
            "total_fees_usd": round(total_fees, 2),
            "total_slippage_usd": round(total_slippage, 2),
            "total_funding_usd": round(total_funding, 2),
            "rejected_signals": port.rejected_signals_count,
            "asset_attribution": asset_breakdown,
            "setup_attribution": setup_breakdown,
            "equity_curve": port.equity_curve,
            "closed_positions": [asdict(t) for t in trades],
        }

    return {
        "window_name": window_name,
        "date_range": f"{start_dt_str} to {end_dt_str}",
        "bars_analyzed": total_steps,
        "execution_time_sec": round(elapsed, 2),
        "policy_a": compile_stats(port_a),
        "policy_b": compile_stats(port_b),
        "displacements_count": len(port_b.displacements),
        "displacements_detail": [asdict(d) for d in port_b.displacements],
    }


def main() -> None:
    db_path = str(PROJECT_ROOT / "data" / "market_data.db")
    results_path = PROJECT_ROOT / "research" / "production_orchestrator_replay_results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("SKY PRODUCTION ORCHESTRATOR HISTORICAL REPLAY")
    print("Evaluating 12-Stage SMC & Expectancy Engine across Non-Overlapping Windows")
    print("=" * 70)

    windows = [
        ("Window 1 (2026 YTD)", "2026-01-01T00:00:00", "2026-10-14T00:00:00"),
        ("Window 2 (2025 OOS)", "2025-01-01T00:00:00", "2025-12-31T23:00:00"),
        ("Window 3 (2024 OOS)", "2024-01-01T00:00:00", "2024-12-31T23:00:00"),
    ]

    all_window_results = []
    for name, start_dt, end_dt in windows:
        print(f"\n[*] Launching {name}: {start_dt[:10]} to {end_dt[:10]}...")
        res = run_window_simulation(db_path, name, start_dt, end_dt)
        all_window_results.append(res)

        p_a = res["policy_a"]
        p_b = res["policy_b"]
        print(f"    Completed in {res['execution_time_sec']}s ({res['bars_analyzed']} bars).")
        print(
            f"    Policy A (FCFS): Return: {p_a['total_return_pct']:+.2f}% | "
            f"Trades: {p_a['trade_count']} | WR: {p_a['win_rate_pct']:.1f}% | "
            f"PF: {p_a['profit_factor']:.2f} | MaxDD: {p_a['max_drawdown_pct']:.2f}% | "
            f"Avg R: {p_a['average_r']:+.2f}R | Fees: ${p_a['total_fees_usd']:.1f}"
        )
        print(
            f"    Policy B (Arb): Return: {p_b['total_return_pct']:+.2f}% | "
            f"Trades: {p_b['trade_count']} | WR: {p_b['win_rate_pct']:.1f}% | "
            f"PF: {p_b['profit_factor']:.2f} | MaxDD: {p_b['max_drawdown_pct']:.2f}% | "
            f"Avg R: {p_b['average_r']:+.2f}R | Displacements: {res['displacements_count']}"
        )

    # Save to JSON
    with open(results_path, "w") as f:
        json.dump(all_window_results, f, indent=2)
    print(f"\n[+] Detailed evaluation results saved to {results_path}")


if __name__ == "__main__":
    main()
