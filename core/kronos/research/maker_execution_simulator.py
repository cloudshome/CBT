"""
core/kronos/research/maker_execution_simulator.py
=================================================
Milestone K10 Phase 3: Grade-E1 Passive Maker Execution & Adverse Selection Simulator.
Simulates passive limit order queue priority, fill probability, post-fill adverse
selection markouts (1, 5, 12 bars), and unfilled order opportunity costs using OHLCV data.

Epistemic Guardrail:
This engine is certified strictly as "Grade-E1: Queue Approximation via OHLCV".
It explicitly does NOT claim Level 2/Level 3 tick-level matching engine fidelity.
Reports adverse selection price drift to prevent illusionary maker fee alpha.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np

ExecutionGrade = Literal["E1"]  # Grade-E1 Queue Approximation via OHLCV
FillStatus = Literal["FILLED", "PARTIALLY_FILLED", "UNFILLED"]


@dataclass(frozen=True)
class SimulatedMakerOrder:
    order_id: str
    bar_index: int
    timestamp: int
    side: Literal["BUY", "SELL"]
    limit_price: float
    order_size: float
    status: FillStatus
    fill_price: float
    fill_volume: float
    # Adverse selection markouts in basis points
    markout_1_bar_bps: float | None
    markout_5_bar_bps: float | None
    markout_12_bar_bps: float | None
    # Opportunity cost if unfilled (bps)
    unfilled_opp_cost_bps: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MakerSimulationReport:
    execution_evidence_grade: ExecutionGrade
    total_orders_placed: int
    orders_filled: int
    orders_partially_filled: int
    orders_unfilled: int
    fill_rate_pct: float
    mean_adverse_selection_1_bar_bps: float
    mean_adverse_selection_5_bar_bps: float
    mean_adverse_selection_12_bar_bps: float
    mean_unfilled_opportunity_cost_bps: float
    maker_fee_bps: float
    gross_maker_pnl_bps: float
    net_maker_pnl_bps: float
    is_maker_advantageous_over_taker: bool
    taker_reference_net_bps: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_evidence_grade": self.execution_evidence_grade,
            "total_orders_placed": self.total_orders_placed,
            "orders_filled": self.orders_filled,
            "orders_partially_filled": self.orders_partially_filled,
            "orders_unfilled": self.orders_unfilled,
            "fill_rate_pct": round(self.fill_rate_pct, 4),
            "mean_adverse_selection_1_bar_bps": round(self.mean_adverse_selection_1_bar_bps, 2),
            "mean_adverse_selection_5_bar_bps": round(self.mean_adverse_selection_5_bar_bps, 2),
            "mean_adverse_selection_12_bar_bps": round(self.mean_adverse_selection_12_bar_bps, 2),
            "mean_unfilled_opportunity_cost_bps": round(self.mean_unfilled_opportunity_cost_bps, 2),
            "maker_fee_bps": self.maker_fee_bps,
            "gross_maker_pnl_bps": round(self.gross_maker_pnl_bps, 2),
            "net_maker_pnl_bps": round(self.net_maker_pnl_bps, 2),
            "is_maker_advantageous_over_taker": self.is_maker_advantageous_over_taker,
            "taker_reference_net_bps": round(self.taker_reference_net_bps, 2),
        }


class MakerExecutionSimulator:
    """
    Grade-E1 Passive Maker Simulator using OHLCV bar dynamics.
    Evaluates realistic maker fills and adverse selection drag.
    """

    GRADE: ExecutionGrade = "E1"

    def __init__(
        self,
        maker_fee_bps: float = 2.0,
        taker_fee_bps: float = 6.0,
        half_spread_bps: float = 2.5,
        slippage_bps: float = 2.0,
        queue_participation_rate: float = 0.15,
    ):
        self.maker_fee_bps = maker_fee_bps
        self.taker_fee_bps = taker_fee_bps
        self.half_spread_bps = half_spread_bps
        self.slippage_bps = slippage_bps
        self.queue_participation_rate = queue_participation_rate

    def simulate_execution(
        self,
        timestamps: np.ndarray | list[int],
        open_prices: np.ndarray | list[float],
        high_prices: np.ndarray | list[float],
        low_prices: np.ndarray | list[float],
        close_prices: np.ndarray | list[float],
        volumes: np.ndarray | list[float],
        signals: np.ndarray | list[int],  # 1 for BUY, -1 for SELL, 0 for HOLD
    ) -> tuple[list[SimulatedMakerOrder], MakerSimulationReport]:
        """
        Executes chronological passive maker simulation on bar sequence.
        Signals at bar t determine limit orders evaluated on bar t+1.
        """
        ts = np.asarray(timestamps, dtype=np.int64)
        o = np.asarray(open_prices, dtype=np.float64)
        h = np.asarray(high_prices, dtype=np.float64)
        lows = np.asarray(low_prices, dtype=np.float64)
        c = np.asarray(close_prices, dtype=np.float64)
        v = np.asarray(volumes, dtype=np.float64)
        sig = np.asarray(signals, dtype=np.int32)
        n = len(c)

        if not (len(ts) == len(o) == len(h) == len(lows) == len(c) == len(v) == len(sig)):
            raise ValueError("All OHLCV and signal arrays must have identical length")

        orders: list[SimulatedMakerOrder] = []
        taker_pnl_bps = 0.0
        maker_gross_pnl_bps = 0.0

        for t in range(n - 13):  # Leave room for 12-bar markout
            if sig[t] == 0:
                continue

            side: Literal["BUY", "SELL"] = "BUY" if sig[t] > 0 else "SELL"
            current_close = c[t]
            spread_offset = current_close * (self.half_spread_bps / 10000.0)

            # Limit order placed passively inside or at touch
            if side == "BUY":
                limit_price = current_close - spread_offset
            else:
                limit_price = current_close + spread_offset

            # Evaluation happens on next bar (t+1)
            next_l = lows[t + 1]
            next_h = h[t + 1]

            # Assess fill condition using OHLCV envelope
            is_filled = False
            is_partial = False
            fill_volume = 0.0

            if side == "BUY":
                if next_l > limit_price:
                    # Price never reached limit
                    status: FillStatus = "UNFILLED"
                elif next_l < limit_price:
                    # Traded through limit - full fill
                    status = "FILLED"
                    is_filled = True
                    fill_volume = 1.0
                else:
                    # Touched exactly at low - partial queue fill depending on volume
                    status = "PARTIALLY_FILLED"
                    is_partial = True
                    fill_volume = 0.5
            else:  # SELL
                if next_h < limit_price:
                    status = "UNFILLED"
                elif next_h > limit_price:
                    status = "FILLED"
                    is_filled = True
                    fill_volume = 1.0
                else:
                    status = "PARTIALLY_FILLED"
                    is_partial = True
                    fill_volume = 0.5

            # Calculate markouts if filled, or opportunity cost if unfilled
            m1, m5, m12 = None, None, None
            opp_cost = None

            if is_filled or is_partial:
                fill_price = limit_price
                # Calculate adverse selection drift at t+2, t+6, t+13
                # For BUY: (P_future - fill_price) / fill_price * 10000
                # For SELL: (fill_price - P_future) / fill_price * 10000
                direction = 1.0 if side == "BUY" else -1.0
                m1 = float(direction * ((c[t + 2] - fill_price) / fill_price) * 10000.0)
                m5 = float(direction * ((c[t + 6] - fill_price) / fill_price) * 10000.0)
                m12 = float(direction * ((c[t + 13] - fill_price) / fill_price) * 10000.0)

                # Horizon return (e.g. 5-bar hold) for gross PnL
                trade_ret_bps = m5 * fill_volume
                maker_gross_pnl_bps += trade_ret_bps
            else:
                fill_price = 0.0
                # Opportunity cost: move over 5 bars that was missed
                direction = 1.0 if side == "BUY" else -1.0
                opp_cost = float(direction * ((c[t + 6] - current_close) / current_close) * 10000.0)

            # Taker reference comparison (assumes 100% fill at close + slip)
            taker_fill_price = (
                current_close * (1.0 + (self.half_spread_bps + self.slippage_bps) / 10000.0)
                if side == "BUY"
                else current_close * (1.0 - (self.half_spread_bps + self.slippage_bps) / 10000.0)
            )
            direction = 1.0 if side == "BUY" else -1.0
            taker_gross = float(
                direction * ((c[t + 6] - taker_fill_price) / taker_fill_price) * 10000.0
            )
            taker_roundtrip_fee = 2.0 * self.taker_fee_bps
            taker_pnl_bps += taker_gross - taker_roundtrip_fee

            orders.append(
                SimulatedMakerOrder(
                    order_id=f"MKO_{t}_{side}",
                    bar_index=t,
                    timestamp=int(ts[t]),
                    side=side,
                    limit_price=limit_price,
                    order_size=1.0,
                    status=status,
                    fill_price=fill_price,
                    fill_volume=fill_volume,
                    markout_1_bar_bps=m1,
                    markout_5_bar_bps=m5,
                    markout_12_bar_bps=m12,
                    unfilled_opp_cost_bps=opp_cost,
                )
            )

        # Aggregate report
        total_orders = len(orders)
        if total_orders == 0:
            return orders, MakerSimulationReport(
                execution_evidence_grade=self.GRADE,
                total_orders_placed=0,
                orders_filled=0,
                orders_partially_filled=0,
                orders_unfilled=0,
                fill_rate_pct=0.0,
                mean_adverse_selection_1_bar_bps=0.0,
                mean_adverse_selection_5_bar_bps=0.0,
                mean_adverse_selection_12_bar_bps=0.0,
                mean_unfilled_opportunity_cost_bps=0.0,
                maker_fee_bps=self.maker_fee_bps,
                gross_maker_pnl_bps=0.0,
                net_maker_pnl_bps=0.0,
                is_maker_advantageous_over_taker=False,
                taker_reference_net_bps=0.0,
            )

        n_filled = sum(1 for o in orders if o.status == "FILLED")
        n_partial = sum(1 for o in orders if o.status == "PARTIALLY_FILLED")
        n_unfilled = sum(1 for o in orders if o.status == "UNFILLED")
        fill_rate = (n_filled + 0.5 * n_partial) / total_orders

        # Markout averages
        filled_orders = [o for o in orders if o.status in ("FILLED", "PARTIALLY_FILLED")]
        unfilled_orders = [o for o in orders if o.status == "UNFILLED"]

        m1_vals = [o.markout_1_bar_bps for o in filled_orders if o.markout_1_bar_bps is not None]
        m5_vals = [o.markout_5_bar_bps for o in filled_orders if o.markout_5_bar_bps is not None]
        m12_vals = [o.markout_12_bar_bps for o in filled_orders if o.markout_12_bar_bps is not None]
        opp_vals = [
            o.unfilled_opp_cost_bps for o in unfilled_orders if o.unfilled_opp_cost_bps is not None
        ]

        mean_m1 = float(np.mean(m1_vals)) if m1_vals else 0.0
        mean_m5 = float(np.mean(m5_vals)) if m5_vals else 0.0
        mean_m12 = float(np.mean(m12_vals)) if m12_vals else 0.0
        mean_opp = float(np.mean(opp_vals)) if opp_vals else 0.0

        # Maker roundtrip fee (entry maker + exit maker/taker)
        maker_cost_bps = (n_filled + n_partial) * (2.0 * self.maker_fee_bps)
        net_maker_pnl_bps = maker_gross_pnl_bps - maker_cost_bps

        is_advantageous = net_maker_pnl_bps > taker_pnl_bps and net_maker_pnl_bps > 0.0

        report = MakerSimulationReport(
            execution_evidence_grade=self.GRADE,
            total_orders_placed=total_orders,
            orders_filled=n_filled,
            orders_partially_filled=n_partial,
            orders_unfilled=n_unfilled,
            fill_rate_pct=fill_rate,
            mean_adverse_selection_1_bar_bps=mean_m1,
            mean_adverse_selection_5_bar_bps=mean_m5,
            mean_adverse_selection_12_bar_bps=mean_m12,
            mean_unfilled_opportunity_cost_bps=mean_opp,
            maker_fee_bps=self.maker_fee_bps,
            gross_maker_pnl_bps=maker_gross_pnl_bps,
            net_maker_pnl_bps=net_maker_pnl_bps,
            is_maker_advantageous_over_taker=is_advantageous,
            taker_reference_net_bps=taker_pnl_bps,
        )

        return orders, report
