"""
core/arbitrage/ev_engine.py
===========================
Deterministic Net-Expected-Value (Net-EV) Engine with Multi-Scenario Stress Testing.

Formula:
Net EV(Q) = Gross Edge(Q)
            - entry_fees(Q)
            - exit_fees(Q)
            - orderbook_slippage(Q)
            - hedge_cost(Q)
            - expected_latency_adverse_move(Q)
            - funding_cashflow_cost(Q)
            - borrow_cost(Q)
            - safety_buffer(Q)

Scenarios:
- Base Net EV: Median execution latency, nominal slippage, expected funding cashflow.
- Conservative Net EV: P95 latency, 1.5x slippage, conservative funding lower bound.
- Stress Net EV: P99 latency, 2.5x slippage, adverse funding shock, basis widening shock.

Invariant:
Never reports gross opportunity as executable profit.
Opportunities with Base Net EV <= 0 can NEVER be classified as QUALIFIED.
"""

from __future__ import annotations

import logging
from typing import Dict, Tuple

from core.arbitrage.models import (
    EVCostBreakdown,
    ExecutableSpread,
    FundingRateRecord,
    MultiScenarioEV,
    Venue,
)

logger = logging.getLogger("ai_quant_sentinel.arbitrage.ev_engine")

MODEL_VERSION = "EVM_v20.1_PROD"

# Standard institutional VIP0/default fee schedules (in basis points)
VENUE_TAKER_FEES_BPS: Dict[Venue, float] = {
    Venue.BINANCE_SPOT: 10.0,   # 0.10%
    Venue.BINANCE_PERP: 5.0,    # 0.05%
    Venue.BYBIT_LINEAR: 5.5,    # 0.055%
    Venue.OKX_PERP: 5.0,        # 0.05%
    Venue.OKX_SPOT: 10.0,       # 0.10%
}

ANNUAL_BORROW_RATE_SPOT: float = 0.08  # 8% annual for spot margin borrowing


class DeterministicEVEngine:
    """Computes deterministic expected value across multi-variable cost models."""

    def __init__(
        self,
        safety_buffer_bps: float = 4.0,
        expected_hold_hours: float = 8.0,
        latency_drift_bps_per_sec: float = 1.5,
    ) -> None:
        self.safety_buffer_bps = safety_buffer_bps
        self.expected_hold_hours = expected_hold_hours
        self.latency_drift_bps_per_sec = latency_drift_bps_per_sec

    def evaluate_multi_scenario_ev(
        self,
        spread: ExecutableSpread,
        funding_records: Dict[Venue, FundingRateRecord],
        basis_volatility_bps: float = 2.5,
        execution_latency_ms: float = 65.0,
    ) -> MultiScenarioEV:
        """Computes Base, Conservative, and Stress Net EV for the given executable spread."""
        notional = spread.notional_usd

        # -------------------------------------------------------------
        # 1. Base Scenario
        # -------------------------------------------------------------
        base_breakdown = self._compute_single_scenario(
            spread=spread,
            funding_records=funding_records,
            basis_volatility_bps=basis_volatility_bps,
            latency_ms=execution_latency_ms,
            slippage_multiplier=1.0,
            funding_haircut=1.0,
            stress_basis_shock_bps=0.0,
        )

        # -------------------------------------------------------------
        # 2. Conservative Scenario (P95 latency, 1.5x slippage, 15% funding haircut)
        # -------------------------------------------------------------
        cons_breakdown = self._compute_single_scenario(
            spread=spread,
            funding_records=funding_records,
            basis_volatility_bps=basis_volatility_bps * 1.3,
            latency_ms=execution_latency_ms * 2.5,  # ~160ms P95
            slippage_multiplier=1.5,
            funding_haircut=0.85,
            stress_basis_shock_bps=1.5,
        )

        # -------------------------------------------------------------
        # 3. Stress Scenario (P99 latency, 2.5x slippage, funding reversal shock)
        # -------------------------------------------------------------
        stress_breakdown = self._compute_single_scenario(
            spread=spread,
            funding_records=funding_records,
            basis_volatility_bps=basis_volatility_bps * 2.0,
            latency_ms=execution_latency_ms * 5.0,  # ~325ms P99
            slippage_multiplier=2.5,
            funding_haircut=0.50,
            stress_basis_shock_bps=4.0,
        )

        return MultiScenarioEV(
            base_net_ev_usd=base_breakdown.net_ev_usd,
            base_net_ev_bps=base_breakdown.net_ev_bps,
            conservative_net_ev_usd=cons_breakdown.net_ev_usd,
            conservative_net_ev_bps=cons_breakdown.net_ev_bps,
            stress_net_ev_usd=stress_breakdown.net_ev_usd,
            stress_net_ev_bps=stress_breakdown.net_ev_bps,
            cost_breakdown=base_breakdown,
        )

    def _compute_single_scenario(
        self,
        spread: ExecutableSpread,
        funding_records: Dict[Venue, FundingRateRecord],
        basis_volatility_bps: float,
        latency_ms: float,
        slippage_multiplier: float,
        funding_haircut: float,
        stress_basis_shock_bps: float,
    ) -> EVCostBreakdown:
        notional = spread.notional_usd

        # A. Fees: Entry and Expected Round-Trip Exit
        long_fee_rate = VENUE_TAKER_FEES_BPS.get(spread.long_venue, 10.0) / 10000.0
        short_fee_rate = VENUE_TAKER_FEES_BPS.get(spread.short_venue, 10.0) / 10000.0

        entry_fee_long = notional * long_fee_rate
        entry_fee_short = notional * short_fee_rate
        exit_fee_long = notional * long_fee_rate
        exit_fee_short = notional * short_fee_rate

        # B. Slippage cost from crossing the book relative to mid price
        # Slippage Long: (vwap_long - mid)
        mid = spread.mid_price_reference
        slip_long_bps = max(0.0, ((spread.vwap_long_ask - mid) / mid) * 10000.0)
        slip_short_bps = max(0.0, ((mid - spread.vwap_short_bid) / mid) * 10000.0)

        slip_long_usd = notional * (slip_long_bps / 10000.0) * slippage_multiplier
        slip_short_usd = notional * (slip_short_bps / 10000.0) * slippage_multiplier

        # C. Latency adverse drift: models price move during cross-exchange order transit
        latency_sec = latency_ms / 1000.0
        latency_adverse_bps = latency_sec * self.latency_drift_bps_per_sec
        latency_cost_usd = notional * (latency_adverse_bps / 10000.0)

        # D. Asynchronous Hedge Cost: basis volatility risk during the execution window
        # Time to complete both legs ~ latency * 2
        async_window_hours = (latency_sec * 2.0) / 3600.0
        hedge_drift_bps = basis_volatility_bps * (async_window_hours**0.5) + stress_basis_shock_bps
        hedge_cost_usd = notional * (hedge_drift_bps / 10000.0)

        # E. Sign-Aware Funding Cashflow
        # Long leg pays long_rate, short leg receives short_rate
        long_f_rec = funding_records.get(spread.long_venue)
        short_f_rec = funding_records.get(spread.short_venue)

        long_f_rate = long_f_rec.funding_rate if long_f_rec else 0.0
        short_f_rate = short_f_rec.funding_rate if short_f_rec else 0.0

        # Net cashflow: (+ if we receive, - if we pay)
        net_funding_rate = (short_f_rate - long_f_rate) * funding_haircut
        funding_cashflow_usd = notional * net_funding_rate

        # F. Borrow Cost (if shorting on spot venue, margin interest applies)
        is_spot_short = spread.short_venue in (Venue.BINANCE_SPOT, Venue.OKX_SPOT)
        if is_spot_short:
            borrow_cost_usd = notional * (ANNUAL_BORROW_RATE_SPOT * (self.expected_hold_hours / 8760.0))
        else:
            borrow_cost_usd = 0.0

        # G. Safety Buffer
        safety_buffer_usd = notional * (self.safety_buffer_bps / 10000.0)

        # H. Gross Edge: Executable spread + Funding Cashflow
        gross_spread_usd = spread.gross_spread_usd
        total_gross_edge_usd = gross_spread_usd + funding_cashflow_usd

        # Total Costs to deduct
        total_costs_usd = (
            entry_fee_long
            + entry_fee_short
            + exit_fee_long
            + exit_fee_short
            + slip_long_usd
            + slip_short_usd
            + hedge_cost_usd
            + latency_cost_usd
            + borrow_cost_usd
            + safety_buffer_usd
        )

        net_ev_usd = total_gross_edge_usd - total_costs_usd
        net_ev_bps = (net_ev_usd / notional) * 10000.0 if notional > 0 else 0.0

        return EVCostBreakdown(
            gross_edge_usd=total_gross_edge_usd,
            entry_fee_long_usd=entry_fee_long,
            entry_fee_short_usd=entry_fee_short,
            expected_exit_fee_long_usd=exit_fee_long,
            expected_exit_fee_short_usd=exit_fee_short,
            orderbook_slippage_long_usd=slip_long_usd,
            orderbook_slippage_short_usd=slip_short_usd,
            hedge_cost_usd=hedge_cost_usd,
            latency_cost_usd=latency_cost_usd,
            funding_cashflow_usd=funding_cashflow_usd,
            borrow_cost_usd=borrow_cost_usd,
            safety_buffer_usd=safety_buffer_usd,
            net_ev_usd=net_ev_usd,
            net_ev_bps=net_ev_bps,
            model_version=MODEL_VERSION,
        )


# Global singleton
ev_engine = DeterministicEVEngine()
