"""
core/execution/liquidity_surface/toxic_flow.py
=============================================
Volume-Synchronized Probability of Toxicity (VPIN) & Hawkes Process Intensity.

Microstructure Formulations:
1. VPIN (Easley, Lopez de Prado, O'Hara):
   VPIN = (sum_{tau=1}^N |V_tau^B - V_tau^S|) / (N * V)
   where V is the fixed volume bucket size and N is the rolling window of buckets.
2. Hawkes Process Self-Excitation:
   lambda(t) = mu + sum_{t_i < t} alpha * exp(-beta * (t - t_i))
   Measures clustering of trades and predatory quote sweeps.
3. Adverse Selection Hazard:
   Probability that counterparty has private superior alpha, leading to post-trade adverse drift.

Constitutional Invariant:
- real_capital_enabled = False strictly maintained.
"""

from __future__ import annotations

import collections
import math
import time
from typing import Deque, List, Optional, Tuple

from core.execution.liquidity_surface.models import (
    ToxicFlowAssessment,
    ToxicityRegime,
)


class HighFrequencyToxicFlowDetector:
    """Detects high-frequency informed flow, quote sweeps, and toxic inventory cascades."""

    def __init__(
        self,
        bucket_volume: float = 10.0,      # Fixed volume per bucket (e.g., 10 BTC)
        num_buckets: int = 50,             # Rolling window N
        hawkes_alpha: float = 0.8,         # Branching ratio
        hawkes_beta: float = 1.2,          # Decay rate
        hawkes_mu: float = 0.5,            # Baseline intensity
    ):
        self.bucket_volume = bucket_volume
        self.num_buckets = num_buckets
        self.hawkes_alpha = hawkes_alpha
        self.hawkes_beta = hawkes_beta
        self.hawkes_mu = hawkes_mu
        self.real_capital_enabled: bool = False

        # State tracking
        self._current_bucket_buy_vol: float = 0.0
        self._current_bucket_sell_vol: float = 0.0
        self._current_bucket_total: float = 0.0
        self._completed_bucket_imbalances: Deque[float] = collections.deque(maxlen=self.num_buckets)
        self._recent_trade_timestamps: Deque[float] = collections.deque(maxlen=200)

    def process_trade(
        self,
        price: float,
        size: float,
        timestamp_ms: int,
        is_buyer_maker: bool,
    ) -> Optional[float]:
        """
        Ingests a single trade tick, updates Hawkes arrival history, and fills VPIN volume buckets.
        Returns latest VPIN value if at least 1 bucket has completed, else None.
        """
        t_sec = timestamp_ms / 1000.0
        self._recent_trade_timestamps.append(t_sec)

        # Buyer maker means buyer provided liquidity, so seller was aggressor (sell volume)
        buy_vol = 0.0 if is_buyer_maker else size
        sell_vol = size if is_buyer_maker else 0.0

        remaining_size = size
        while remaining_size > 0:
            space_in_bucket = self.bucket_volume - self._current_bucket_total
            fill_amount = min(remaining_size, space_in_bucket)
            
            frac = fill_amount / size if size > 0 else 0.0
            self._current_bucket_buy_vol += buy_vol * frac
            self._current_bucket_sell_vol += sell_vol * frac
            self._current_bucket_total += fill_amount
            remaining_size -= fill_amount

            # If bucket is filled, record imbalance and reset
            if self._current_bucket_total >= self.bucket_volume:
                imbalance = abs(self._current_bucket_buy_vol - self._current_bucket_sell_vol)
                self._completed_bucket_imbalances.append(imbalance)
                self._current_bucket_buy_vol = 0.0
                self._current_bucket_sell_vol = 0.0
                self._current_bucket_total = 0.0

        return self.compute_vpin()

    def compute_vpin(self) -> float:
        """
        Calculates current VPIN across completed volume buckets.
        Returns value in [0.0, 1.0].
        """
        if not self._completed_bucket_imbalances:
            return 0.25  # Neutral benign default

        total_imbalance = sum(self._completed_bucket_imbalances)
        total_denom = len(self._completed_bucket_imbalances) * self.bucket_volume
        if total_denom <= 0:
            return 0.25

        vpin = total_imbalance / total_denom
        return max(0.0, min(1.0, vpin))

    def compute_hawkes_intensity(self, current_time_ms: int) -> float:
        """
        Evaluates self-exciting Hawkes intensity at current_time_ms:
        lambda(t) = mu + sum_{t_i < t} alpha * exp(-beta * (t - t_i))
        """
        now_sec = current_time_ms / 1000.0
        intensity = self.hawkes_mu

        for t_i in self._recent_trade_timestamps:
            delta = now_sec - t_i
            if 0 < delta < 30.0:  # 30-second memory cutoff
                intensity += self.hawkes_alpha * math.exp(-self.hawkes_beta * delta)

        return intensity

    def assess_toxicity(self, symbol: str, current_time_ms: int) -> ToxicFlowAssessment:
        """
        Generates full microstructure toxicity assessment and regime classification.
        """
        vpin = self.compute_vpin()
        hawkes_intensity = self.compute_hawkes_intensity(current_time_ms)

        # Adverse selection composite risk: blends VPIN and normalized Hawkes intensity
        hawkes_norm = min(1.0, hawkes_intensity / 5.0)
        adverse_selection_risk = (0.7 * vpin) + (0.3 * hawkes_norm)

        # Classify regime
        if vpin >= 0.85 or adverse_selection_risk >= 0.85:
            regime = ToxicityRegime.EXTREME_ADVERSE
            is_toxic = True
            action = "HALT_AGGRESSIVE_EXECUTION_SWITCH_TO_DARK_OR_PASSIVE"
        elif vpin >= 0.65 or adverse_selection_risk >= 0.65:
            regime = ToxicityRegime.TOXIC
            is_toxic = True
            action = "WIDEN_MAKER_SPREADS_AND_SCALE_DOWN_SIZE"
        elif vpin >= 0.35:
            regime = ToxicityRegime.MODERATE
            is_toxic = False
            action = "STANDARD_EXECUTION_SCHEDULE"
        else:
            regime = ToxicityRegime.BENIGN
            is_toxic = False
            action = "FAVORABLE_FLOW_TIGHT_SPREAD_OPPORTUNITY"

        return ToxicFlowAssessment(
            symbol=symbol,
            timestamp_ms=current_time_ms,
            vpin=round(vpin, 4),
            regime=regime,
            hawkes_intensity=round(hawkes_intensity, 4),
            adverse_selection_risk=round(adverse_selection_risk, 4),
            is_toxic=is_toxic,
            recommended_action=action,
            real_capital_enabled=False,
        )


# Exported singleton
toxic_flow_detector = HighFrequencyToxicFlowDetector()
