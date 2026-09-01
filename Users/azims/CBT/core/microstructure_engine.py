"""
SKY Institutional Microstructure & Order Flow Alpha Engine.

Provides deep order book analysis, continuous flow toxicity (VPIN),
Kyle's Lambda price impact regression, slope elasticity (dQ/dP),
and institutional footprint/iceberg detection.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger("sky.microstructure_engine")


@dataclass
class DepthTierMetrics:
    tier: str                          # "L1", "L5", "L10", "L20", "L50"
    imbalance: float                   # [-1.0, 1.0] (Positive = Bid Heavy)
    bid_volume: float
    ask_volume: float
    bid_notional_usd: float
    ask_notional_usd: float


@dataclass
class SlopeElasticityResult:
    bid_slope: float                   # dQ/dP on bid side (liquidity density)
    ask_slope: float                   # dQ/dP on ask side
    elasticity_ratio: float            # bid_slope / ask_slope (>1.0 = Bids absorb harder)
    book_stiffness: str                # "RIGID_BIDS", "RIGID_ASKS", "BALANCED_ELASTIC", "THIN_FRAGILE"


@dataclass
class FlowToxicityResult:
    vpin: float                        # [0.0, 1.0] Volume-Synchronized Probability of Toxicity
    kyles_lambda: float                # Price impact per unit of aggressive flow ($/unit)
    hasbrouck_impact: float            # Cumulative permanent price impact estimate (bps)
    informed_trader_ratio: float       # Estimate of informed vs noise flow
    toxicity_regime: str               # "BENIGN_FLOW", "INFORMED_ACCUMULATION", "INFORMED_DISTRIBUTION", "CASCADE_TOXIC_RISK"


@dataclass
class IcebergFootprint:
    price_level: float
    side: str                          # "BID" or "ASK"
    visible_qty: float
    estimated_hidden_qty: float
    absorption_ratio: float            # Executed / Visible
    confidence: float                  # [0.0, 1.0]
    timestamp_ms: int


@dataclass
class MicrostructureAnalysis:
    symbol: str
    timestamp_ms: int
    mid_price: float
    micro_price: float
    micro_price_delta_bps: float
    spread_bps: float
    depth_tiers: Dict[str, DepthTierMetrics]
    slope_elasticity: SlopeElasticityResult
    flow_toxicity: FlowToxicityResult
    detected_icebergs: List[IcebergFootprint]
    sweep_absorption_score: float      # [0.0, 1.0]
    institutional_bias: str            # "BULLISH_ABSORPTION", "BEARISH_DISTRIBUTION", "SWEEP_TRAP", "NEUTRAL"
    narrative: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MicrostructureEngine:
    """
    Evaluates institutional microstructure, depth dynamics, slope elasticity,
    continuous flow toxicity, and footprint anomalies.
    """

    def __init__(
        self,
        vpin_bucket_size: float = 100.0,
        vpin_num_buckets: int = 50,
    ):
        self.vpin_bucket_size = vpin_bucket_size
        self.vpin_num_buckets = vpin_num_buckets
        self._trade_buckets: List[Tuple[float, float]] = []  # [(buy_vol, sell_vol)]

    def analyze(
        self,
        bids: List[Tuple[float, float]],  # List of (price, qty)
        asks: List[Tuple[float, float]],  # List of (price, qty)
        recent_trades: Optional[List[Dict[str, Any]]] = None,  # List of {price, qty, is_buyer_maker, timestamp}
        symbol: str = "BTC/USDT",
        timestamp_ms: Optional[int] = None,
    ) -> MicrostructureAnalysis:
        """
        Conducts comprehensive institutional microstructure analysis.
        """
        now = timestamp_ms or int(time.time() * 1000)

        if not bids or not asks:
            return self._empty_analysis(symbol, now)

        # Convert to arrays
        b_arr = np.array(bids, dtype=np.float64)
        a_arr = np.array(asks, dtype=np.float64)

        b_prices, b_sizes = b_arr[:, 0], b_arr[:, 1]
        a_prices, a_sizes = a_arr[:, 0], a_arr[:, 1]

        best_bid = float(b_prices[0])
        best_ask = float(a_prices[0])
        mid_price = (best_bid + best_ask) / 2.0
        spread = max(0.0, best_ask - best_bid)
        spread_bps = (spread / mid_price * 10000.0) if mid_price > 0 else 0.0

        # Microprice calculation: P_micro = (P_bid * Q_ask + P_ask * Q_bid) / (Q_bid + Q_ask)
        l1_denom = b_sizes[0] + a_sizes[0]
        if l1_denom > 0:
            micro_price = float((best_bid * a_sizes[0] + best_ask * b_sizes[0]) / l1_denom)
            micro_delta_bps = float((micro_price - mid_price) / mid_price * 10000.0)
        else:
            micro_price = mid_price
            micro_delta_bps = 0.0

        # 1. Depth Tiers
        depth_tiers = self._compute_depth_tiers(b_prices, b_sizes, a_prices, a_sizes)

        # 2. Slope Elasticity (dQ/dP)
        slope_result = self._compute_slope_elasticity(b_prices, b_sizes, a_prices, a_sizes, mid_price)

        # 3. Flow Toxicity & Kyle's Lambda
        toxicity_result = self._compute_flow_toxicity(recent_trades, mid_price, depth_tiers)

        # 4. Institutional Iceberg & Sweep Detection
        icebergs = self._detect_icebergs(b_prices, b_sizes, a_prices, a_sizes, recent_trades, now)
        sweep_score = self._compute_sweep_absorption_score(depth_tiers, toxicity_result, slope_result)

        # 5. Composite Institutional Bias & Narrative
        bias, narrative = self._synthesize_bias(
            depth_tiers, slope_result, toxicity_result, icebergs, sweep_score, micro_delta_bps
        )

        return MicrostructureAnalysis(
            symbol=symbol,
            timestamp_ms=now,
            mid_price=round(mid_price, 4),
            micro_price=round(micro_price, 4),
            micro_price_delta_bps=round(micro_delta_bps, 2),
            spread_bps=round(spread_bps, 2),
            depth_tiers=depth_tiers,
            slope_elasticity=slope_result,
            flow_toxicity=toxicity_result,
            detected_icebergs=icebergs,
            sweep_absorption_score=round(sweep_score, 3),
            institutional_bias=bias,
            narrative=narrative,
        )

    def _compute_depth_tiers(
        self,
        b_prices: np.ndarray,
        b_sizes: np.ndarray,
        a_prices: np.ndarray,
        a_sizes: np.ndarray,
    ) -> Dict[str, DepthTierMetrics]:
        tiers_config = {"L1": 1, "L5": 5, "L10": 10, "L20": 20, "L50": 50}
        results: Dict[str, DepthTierMetrics] = {}

        for name, depth in tiers_config.items():
            b_sub_p = b_prices[:depth]
            b_sub_s = b_sizes[:depth]
            a_sub_p = a_prices[:depth]
            a_sub_s = a_sizes[:depth]

            b_vol = float(np.sum(b_sub_s))
            a_vol = float(np.sum(a_sub_s))
            b_usd = float(np.sum(b_sub_p * b_sub_s))
            a_usd = float(np.sum(a_sub_p * a_sub_s))

            vol_total = b_vol + a_vol
            imbalance = float((b_vol - a_vol) / vol_total) if vol_total > 0 else 0.0

            results[name] = DepthTierMetrics(
                tier=name,
                imbalance=round(imbalance, 4),
                bid_volume=round(b_vol, 4),
                ask_volume=round(a_vol, 4),
                bid_notional_usd=round(b_usd, 2),
                ask_notional_usd=round(a_usd, 2),
            )

        return results

    def _compute_slope_elasticity(
        self,
        b_prices: np.ndarray,
        b_sizes: np.ndarray,
        a_prices: np.ndarray,
        a_sizes: np.ndarray,
        mid_price: float,
    ) -> SlopeElasticityResult:
        n_b = min(len(b_prices), 20)
        n_a = min(len(a_prices), 20)

        if n_b < 2 or n_a < 2 or mid_price <= 0:
            return SlopeElasticityResult(
                bid_slope=1.0,
                ask_slope=1.0,
                elasticity_ratio=1.0,
                book_stiffness="BALANCED_ELASTIC",
            )

        # Delta P in bps from best quote
        b_delta_p = np.abs((b_prices[:n_b] - b_prices[0]) / mid_price * 10000.0) + 0.1
        a_delta_p = np.abs((a_prices[:n_a] - a_prices[0]) / mid_price * 10000.0) + 0.1

        # Cumulative volume added per price step
        b_cum_q = np.cumsum(b_sizes[:n_b])
        a_cum_q = np.cumsum(a_sizes[:n_a])

        # Slope: dQ / dP (higher = thicker book per bps move)
        bid_slope = float(np.mean(b_cum_q / b_delta_p))
        ask_slope = float(np.mean(a_cum_q / a_delta_p))

        ratio = (bid_slope / ask_slope) if ask_slope > 0 else 1.0

        if ratio > 1.8:
            stiffness = "RIGID_BIDS"
        elif ratio < 0.55:
            stiffness = "RIGID_ASKS"
        elif bid_slope < 0.2 and ask_slope < 0.2:
            stiffness = "THIN_FRAGILE"
        else:
            stiffness = "BALANCED_ELASTIC"

        return SlopeElasticityResult(
            bid_slope=round(bid_slope, 4),
            ask_slope=round(ask_slope, 4),
            elasticity_ratio=round(ratio, 4),
            book_stiffness=stiffness,
        )

    def _compute_flow_toxicity(
        self,
        recent_trades: Optional[List[Dict[str, Any]]],
        mid_price: float,
        depth_tiers: Dict[str, DepthTierMetrics],
    ) -> FlowToxicityResult:
        """
        Calculates continuous VPIN and Kyle's Lambda.
        """
        if not recent_trades or len(recent_trades) < 5:
            # Fallback estimation using depth imbalance and spread
            l10_imb = depth_tiers.get("L10", depth_tiers.get("L1")).imbalance
            vpin_est = float(np.clip(0.35 + abs(l10_imb) * 0.3, 0.05, 0.95))
            kyles_lambda = float(round(0.00015 * (1.0 + abs(l10_imb)), 6))
            hasbrouck = float(round(kyles_lambda * 1000.0 * 10000.0 / max(1.0, mid_price), 2))
            regime = "BENIGN_FLOW" if vpin_est < 0.55 else ("INFORMED_ACCUMULATION" if l10_imb > 0 else "INFORMED_DISTRIBUTION")
            return FlowToxicityResult(
                vpin=round(vpin_est, 3),
                kyles_lambda=kyles_lambda,
                hasbrouck_impact=hasbrouck,
                informed_trader_ratio=round(vpin_est * 0.7, 3),
                toxicity_regime=regime,
            )

        # Parse trade flow
        buy_vols: List[float] = []
        sell_vols: List[float] = []
        price_deltas: List[float] = []
        net_flows: List[float] = []

        prev_price = float(recent_trades[0].get("price", mid_price))
        for t in recent_trades:
            p = float(t.get("price", mid_price))
            q = float(t.get("qty", 1.0))
            is_buyer_maker = t.get("is_buyer_maker", False)  # If buyer is maker, taker is seller

            if is_buyer_maker:
                sell_vols.append(q)
                net_flows.append(-q)
            else:
                buy_vols.append(q)
                net_flows.append(q)

            price_deltas.append(p - prev_price)
            prev_price = p

        # VPIN calculation: sum(|V_buy - V_sell|) / Total_V
        total_buy = sum(buy_vols)
        total_sell = sum(sell_vols)
        total_vol = total_buy + total_sell
        if total_vol > 0:
            vpin = float(np.clip(abs(total_buy - total_sell) / total_vol, 0.05, 0.95))
        else:
            vpin = 0.35

        # Kyle's Lambda: Cov(Delta P, Net Flow) / Var(Net Flow)
        if len(price_deltas) > 3 and np.var(net_flows) > 1e-9:
            cov = float(np.cov(price_deltas, net_flows)[0, 1])
            var_flow = float(np.var(net_flows))
            kyles_lambda = float(max(1e-8, cov / var_flow))
        else:
            kyles_lambda = 0.00012

        hasbrouck = float(round(kyles_lambda * 1000.0 * 10000.0 / max(1.0, mid_price), 2))

        if vpin > 0.75:
            regime = "CASCADE_TOXIC_RISK"
        elif vpin > 0.55:
            regime = "INFORMED_ACCUMULATION" if total_buy > total_sell else "INFORMED_DISTRIBUTION"
        else:
            regime = "BENIGN_FLOW"

        return FlowToxicityResult(
            vpin=round(vpin, 3),
            kyles_lambda=round(kyles_lambda, 6),
            hasbrouck_impact=hasbrouck,
            informed_trader_ratio=round(vpin * 0.75, 3),
            toxicity_regime=regime,
        )

    def _detect_icebergs(
        self,
        b_prices: np.ndarray,
        b_sizes: np.ndarray,
        a_prices: np.ndarray,
        a_sizes: np.ndarray,
        recent_trades: Optional[List[Dict[str, Any]]],
        now: int,
    ) -> List[IcebergFootprint]:
        """
        Detects hidden iceberg absorption where executed trade volume exceeds visible depth.
        """
        icebergs: List[IcebergFootprint] = []
        if not recent_trades:
            return icebergs

        # Aggregate executed volume per price level
        trade_vol_by_price: Dict[float, float] = {}
        for t in recent_trades:
            p = round(float(t.get("price", 0.0)), 2)
            q = float(t.get("qty", 0.0))
            trade_vol_by_price[p] = trade_vol_by_price.get(p, 0.0) + q

        # Check top 5 bid levels
        for p, s in zip(b_prices[:5], b_sizes[:5]):
            p_rounded = round(float(p), 2)
            traded_qty = trade_vol_by_price.get(p_rounded, 0.0)
            if s > 0 and traded_qty >= 2.5 * s:
                icebergs.append(
                    IcebergFootprint(
                        price_level=float(p),
                        side="BID",
                        visible_qty=round(float(s), 4),
                        estimated_hidden_qty=round(traded_qty - float(s), 4),
                        absorption_ratio=round(traded_qty / float(s), 2),
                        confidence=min(0.95, round(0.5 + (traded_qty / float(s)) * 0.1, 2)),
                        timestamp_ms=now,
                    )
                )

        # Check top 5 ask levels
        for p, s in zip(a_prices[:5], a_sizes[:5]):
            p_rounded = round(float(p), 2)
            traded_qty = trade_vol_by_price.get(p_rounded, 0.0)
            if s > 0 and traded_qty >= 2.5 * s:
                icebergs.append(
                    IcebergFootprint(
                        price_level=float(p),
                        side="ASK",
                        visible_qty=round(float(s), 4),
                        estimated_hidden_qty=round(traded_qty - float(s), 4),
                        absorption_ratio=round(traded_qty / float(s), 2),
                        confidence=min(0.95, round(0.5 + (traded_qty / float(s)) * 0.1, 2)),
                        timestamp_ms=now,
                    )
                )

        return icebergs

    def _compute_sweep_absorption_score(
        self,
        depth_tiers: Dict[str, DepthTierMetrics],
        toxicity: FlowToxicityResult,
        slope: SlopeElasticityResult,
    ) -> float:
        l1_imb = depth_tiers.get("L1", depth_tiers.get("L5")).imbalance
        l20_imb = depth_tiers.get("L20", depth_tiers.get("L10")).imbalance

        # Divergence between top of book and deep book indicates aggressive absorption
        divergence = abs(l1_imb - l20_imb)
        score = 0.4 * divergence + 0.3 * toxicity.vpin + 0.3 * min(1.0, abs(slope.elasticity_ratio - 1.0))
        return float(np.clip(score, 0.0, 1.0))

    def _synthesize_bias(
        self,
        depth_tiers: Dict[str, DepthTierMetrics],
        slope: SlopeElasticityResult,
        toxicity: FlowToxicityResult,
        icebergs: List[IcebergFootprint],
        sweep_score: float,
        micro_delta_bps: float,
    ) -> Tuple[str, str]:
        l10_imb = depth_tiers.get("L10", depth_tiers.get("L5")).imbalance
        bid_icebergs = sum(1 for ice in icebergs if ice.side == "BID")
        ask_icebergs = sum(1 for ice in icebergs if ice.side == "ASK")

        if bid_icebergs > ask_icebergs and (l10_imb > 0.2 or micro_delta_bps > 1.5):
            bias = "BULLISH_ABSORPTION"
            narrative = f"Institutional passive bids absorbing sell liquidity (L10 Imbalance: {l10_imb:+.2f}, Micro Delta: {micro_delta_bps:+.1f} bps)."
        elif ask_icebergs > bid_icebergs and (l10_imb < -0.2 or micro_delta_bps < -1.5):
            bias = "BEARISH_DISTRIBUTION"
            narrative = f"Institutional passive asks absorbing buy liquidity (L10 Imbalance: {l10_imb:+.2f}, Micro Delta: {micro_delta_bps:+.1f} bps)."
        elif sweep_score > 0.65:
            bias = "SWEEP_TRAP"
            narrative = f"Elevated liquidity sweep/stop-run dynamic detected (Absorption Score: {sweep_score:.2f}, VPIN: {toxicity.vpin:.2f})."
        else:
            bias = "NEUTRAL"
            narrative = f"Microstructure is balanced with steady two-sided liquidity elasticity ({slope.book_stiffness})."

        return bias, narrative

    def _empty_analysis(self, symbol: str, timestamp_ms: int) -> MicrostructureAnalysis:
        empty_tiers = {
            t: DepthTierMetrics(t, 0.0, 0.0, 0.0, 0.0, 0.0)
            for t in ["L1", "L5", "L10", "L20", "L50"]
        }
        return MicrostructureAnalysis(
            symbol=symbol,
            timestamp_ms=timestamp_ms,
            mid_price=0.0,
            micro_price=0.0,
            micro_price_delta_bps=0.0,
            spread_bps=0.0,
            depth_tiers=empty_tiers,
            slope_elasticity=SlopeElasticityResult(1.0, 1.0, 1.0, "THIN_FRAGILE"),
            flow_toxicity=FlowToxicityResult(0.25, 0.0001, 1.0, 0.2, "BENIGN_FLOW"),
            detected_icebergs=[],
            sweep_absorption_score=0.0,
            institutional_bias="NEUTRAL",
            narrative="No order book data available.",
        )


microstructure_engine = MicrostructureEngine()
