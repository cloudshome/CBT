"""
core/arbitrage/funding_matrix.py
================================
Sign-Aware Cross-Venue Funding Rate Matrix & Cashflow Projection Engine.

Institutional Principles:
- Funding economics are strictly SIGN-AWARE based on leg direction:
    Long Perp Leg: Cashflow = -F_long * Notional
    Short Perp Leg: Cashflow = +F_short * Notional
    Net Cashflow = (F_short - F_long) * Notional
- Never assumes funding is symmetric or risk-free.
- Incorporates funding uncertainty estimation and payment timing countdowns.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Tuple

from core.arbitrage.models import (
    FundingEstimate,
    FundingMatrixEntry,
    FundingRateRecord,
    Venue,
)

logger = logging.getLogger("ai_quant_sentinel.arbitrage.funding_matrix")


class FundingMatrixEngine:
    """Computes pairwise cross-venue funding rate divergence and directional cashflow yields."""

    def __init__(self, min_divergence_bps: float = 2.0) -> None:
        self.min_divergence_bps = min_divergence_bps

    def compute_funding_matrix(
        self, records: List[FundingRateRecord]
    ) -> List[FundingMatrixEntry]:
        """Evaluates all pairwise perpetual funding combinations for a given asset."""
        now_ms = int(time.time() * 1000)
        matrix: List[FundingMatrixEntry] = []

        # Deduplicate records by venue + symbol
        venue_records: Dict[Venue, FundingRateRecord] = {r.venue: r for r in records}
        venues = list(venue_records.keys())

        for i in range(len(venues)):
            for j in range(i + 1, len(venues)):
                v_a, v_b = venues[i], venues[j]
                rec_a, rec_b = venue_records[v_a], venue_records[v_b]

                if rec_a.canonical_symbol != rec_b.canonical_symbol:
                    continue

                r_a = rec_a.funding_rate
                r_b = rec_b.funding_rate

                # Directional assignment:
                # If r_b > r_a: Long v_a (pays r_a, or receives if neg), Short v_b (receives r_b) -> net edge = r_b - r_a
                # If r_a > r_b: Long v_b, Short v_a -> net edge = r_a - r_b
                if r_b >= r_a:
                    proposed_long = v_a
                    proposed_short = v_b
                    edge = r_b - r_a
                else:
                    proposed_long = v_b
                    proposed_short = v_a
                    edge = r_a - r_b

                divergence_bps = edge * 10000.0

                # Annualized divergence assuming 3 standard 8h payments per day
                intervals_per_day = 24.0 / max(rec_a.interval_hours, 1)
                annualized_pct = edge * intervals_per_day * 365.0 * 100.0

                # Time to next payment
                next_payment_ms = min(rec_a.next_funding_time_ms, rec_b.next_funding_time_ms)
                time_to_funding_sec = max(0.0, (next_payment_ms - now_ms) / 1000.0)

                # Estimated capture: scaled down if rollover is far or rate is unstable
                # If time_to_funding < 1 hour, confidence is high; if 7 hours away, rates can drift
                stability_factor = max(0.5, 1.0 - (time_to_funding_sec / (8.0 * 3600.0)) * 0.4)
                estimated_capture_bps = divergence_bps * stability_factor

                freshness_ms = float(
                    max(now_ms - rec_a.local_receipt_ms, now_ms - rec_b.local_receipt_ms)
                )

                pair_id = f"{v_a.value}::{v_b.value}::{rec_a.canonical_symbol}"

                entry = FundingMatrixEntry(
                    pair_id=pair_id,
                    canonical_symbol=rec_a.canonical_symbol,
                    venue_a=v_a,
                    venue_b=v_b,
                    rate_a=r_a,
                    rate_b=r_b,
                    raw_divergence=r_a - r_b,
                    raw_divergence_bps=divergence_bps,
                    annualized_divergence_pct=annualized_pct,
                    time_to_funding_sec=time_to_funding_sec,
                    estimated_capture_bps=estimated_capture_bps,
                    confidence=round(stability_factor, 3),
                    data_freshness_ms=freshness_ms,
                    proposed_long_leg=proposed_long,
                    proposed_short_leg=proposed_short,
                )
                matrix.append(entry)

        # Sort matrix by descending capture yield
        matrix.sort(key=lambda m: m.estimated_capture_bps, reverse=True)
        return matrix

    def estimate_funding_uncertainty(
        self, record: FundingRateRecord
    ) -> FundingEstimate:
        """Models funding rate volatility and worst-case cashflow expectations."""
        now_ms = int(time.time() * 1000)
        time_to_pay_sec = max(0.0, (record.next_funding_time_ms - now_ms) / 1000.0)

        # Proximity weighting: closer to payment = less rate drift
        hours_to_pay = time_to_pay_sec / 3600.0
        drift_sigma_bps = hours_to_pay * 0.35  # ~0.35 bps drift per hour remaining
        current_bps = record.funding_rate * 10000.0

        # Worst-case cashflow scenario: adverse shift of 1.96 sigma
        worst_case_bps = current_bps - (1.96 * drift_sigma_bps)
        confidence = max(0.5, min(1.0, 1.0 - (hours_to_pay / 8.0) * 0.5))

        return FundingEstimate(
            venue=record.venue,
            symbol=record.symbol,
            current_rate=record.funding_rate,
            predicted_rate=record.funding_rate,
            confidence=round(confidence, 3),
            time_to_payment_sec=time_to_pay_sec,
            expected_cashflow_bps=current_bps,
            worst_case_cashflow_bps=worst_case_bps,
            source_timestamp_ms=record.local_receipt_ms,
        )

    def calculate_directional_funding_cashflow(
        self,
        long_venue: Venue,
        short_venue: Venue,
        notional_usd: float,
        funding_records: Dict[Venue, FundingRateRecord],
    ) -> Tuple[float, float, float]:
        """
        Calculates exact signed funding cashflows for a designated two-leg hedge:
        Returns: (long_cashflow_usd, short_cashflow_usd, net_cashflow_usd)
        """
        long_rec = funding_records.get(long_venue)
        short_rec = funding_records.get(short_venue)

        # Spot legs do not pay or receive funding
        long_rate = long_rec.funding_rate if long_rec else 0.0
        short_rate = short_rec.funding_rate if short_rec else 0.0

        # Long leg pays positive rate, receives negative rate
        long_cashflow_usd = -long_rate * notional_usd
        # Short leg receives positive rate, pays negative rate
        short_cashflow_usd = short_rate * notional_usd

        net_cashflow_usd = long_cashflow_usd + short_cashflow_usd
        return long_cashflow_usd, short_cashflow_usd, net_cashflow_usd


# Global singleton
funding_matrix_engine = FundingMatrixEngine()
