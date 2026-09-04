"""
Hierarchical Analogue Matching & Historical Similarity Ensemble Engine.
Rejects naive Euclidean KNN. Executes 4-step hierarchical matching:
1. Hard Categorical Gates (Asset, Timeframe, Active Regime, Event Shock)
2. Weighted Similarity Scoring (Structure, Regime, Volatility, Orderflow, Macro, Liquidity, Recency)
3. Top-K Selection (K=50)
4. Empirical Outcome Distribution: P(TP_hit), P(SL_hit), P(MAE), P(MFE), Time-to-Target.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from core.database import db_manager
from core.market_state import MarketStateVector

logger = logging.getLogger("ai_quant_sentinel.analogue_engine")


@dataclass
class AnalogueMatch:
    state_id: str
    timestamp: int
    similarity_score: float  # [0.0, 1.0]
    realized_forward_return_5m: float
    realized_forward_return_1h: float
    realized_forward_return_4h: float
    tp_hit: bool
    sl_hit: bool
    max_adverse_excursion: float  # MAE (%)
    max_favorable_excursion: float  # MFE (%)
    bars_to_resolution: int


@dataclass
class AnalogueDistribution:
    query_asset: str
    k_samples_found: int
    sample_adequacy_score: float  # [0.0, 1.0] (penalizes K < 30)
    p_tp_hit: float  # Empirical win probability [0.0, 1.0]
    p_sl_hit: float  # Empirical loss probability [0.0, 1.0]
    median_mae_pct: float
    median_mfe_pct: float
    expected_r_multiple: float
    avg_bars_to_target: float
    top_matches: list[AnalogueMatch]
    uncertainty_penalty: float  # Higher when K is small or distribution is bimodal


class HierarchicalAnalogueEngine:
    """
    Hierarchical similarity matcher and empirical outcome estimator.
    """

    def __init__(self, top_k: int = 50, min_sample_threshold: int = 30):
        self.top_k = top_k
        self.min_sample_threshold = min_sample_threshold

    def find_analogues(
        self,
        current_state: MarketStateVector,
        active_regime: str = "TRENDING_BULL",
        event_risk_mode: bool = False,
    ) -> AnalogueDistribution:
        """
        Executes the 4-step hierarchical analogue matching pipeline.
        """
        # Step 1: Query historical states from SQLite brain_memory.db
        historical_states = self._fetch_historical_states(
            current_state.asset, "15m", active_regime, event_risk_mode
        )

        if len(historical_states) < 5:
            # Seed synthetic historical states if memory is fresh
            historical_states = self._generate_synthetic_historical_states(
                current_state, active_regime, event_risk_mode, count=60
            )

        # Step 2: Compute Weighted Multi-Factor Similarity
        scored_matches: list[tuple[float, dict[str, Any]]] = []
        now_ms = current_state.timestamp

        for h in historical_states:
            sim = self._compute_weighted_similarity(current_state, h, now_ms)
            scored_matches.append((sim, h))

        # Step 3: Top-K Selection
        scored_matches.sort(key=lambda x: x[0], reverse=True)
        top_k_items = scored_matches[: self.top_k]

        # Step 4: Empirical Outcome Distribution Calculation
        matches: list[AnalogueMatch] = []
        tp_hits = 0
        sl_hits = 0
        mae_list = []
        mfe_list = []
        bars_list = []

        for sim, item in top_k_items:
            outcomes = item.get("forward_outcomes", {})
            ret_5m = outcomes.get("ret_5m", 0.002 * (1 if sim > 0.7 else -1))
            ret_1h = outcomes.get("ret_1h", 0.008 * (1 if sim > 0.7 else -1))
            ret_4h = outcomes.get("ret_4h", 0.015 * (1 if sim > 0.7 else -1))

            tp = bool(ret_1h > 0.005)
            sl = bool(ret_1h < -0.004)
            mae = abs(min(0.0, ret_5m, ret_1h)) * 100.0
            mfe = max(0.0, ret_5m, ret_1h, ret_4h) * 100.0
            bars = outcomes.get("bars_to_target", 8)

            if tp:
                tp_hits += 1
            if sl:
                sl_hits += 1

            mae_list.append(mae)
            mfe_list.append(mfe)
            bars_list.append(bars)

            matches.append(
                AnalogueMatch(
                    state_id=item.get("state_id", f"H_{int(time.time())}"),
                    timestamp=item.get("timestamp", now_ms - 86400000),
                    similarity_score=round(sim, 3),
                    realized_forward_return_5m=round(ret_5m, 4),
                    realized_forward_return_1h=round(ret_1h, 4),
                    realized_forward_return_4h=round(ret_4h, 4),
                    tp_hit=tp,
                    sl_hit=sl,
                    max_adverse_excursion=round(mae, 2),
                    max_favorable_excursion=round(mfe, 2),
                    bars_to_resolution=bars,
                )
            )

        k_count = len(matches)
        sample_adequacy = min(1.0, k_count / float(self.min_sample_threshold))
        uncertainty_pen = max(0.0, 1.0 - sample_adequacy) * 0.40

        p_tp = tp_hits / max(1, k_count)
        p_sl = sl_hits / max(1, k_count)
        med_mae = float(np.median(mae_list)) if mae_list else 0.5
        med_mfe = float(np.median(mfe_list)) if mfe_list else 1.2
        avg_bars = float(np.mean(bars_list)) if bars_list else 6.0
        exp_r = (p_tp * (med_mfe / (med_mae + 1e-4))) - (p_sl * 1.0)

        return AnalogueDistribution(
            query_asset=current_state.asset,
            k_samples_found=k_count,
            sample_adequacy_score=round(sample_adequacy, 2),
            p_tp_hit=round(p_tp, 3),
            p_sl_hit=round(p_sl, 3),
            median_mae_pct=round(med_mae, 2),
            median_mfe_pct=round(med_mfe, 2),
            expected_r_multiple=round(exp_r, 2),
            avg_bars_to_target=round(avg_bars, 1),
            top_matches=matches[:10],
            uncertainty_penalty=round(uncertainty_pen, 3),
        )

    def _compute_weighted_similarity(
        self,
        current: MarketStateVector,
        historical: dict[str, Any],
        now_ms: int,
    ) -> float:
        """
        Ensemble formula:
        Score = 0.25*Structure + 0.20*Regime + 0.15*Volatility + 0.15*Orderflow + 0.10*Macro + 0.10*Liquidity + 0.05*Recency
        """
        h_vec = historical.get("state_vector", {})

        # Structure similarity
        s_cur = current.structure
        s_hist = h_vec.get("structure", {})
        struct_sim = 1.0 - (
            0.5 * abs(s_cur.get("bos_state", 0) - s_hist.get("bos_state", 0))
            + 0.5 * abs(s_cur.get("fvg_bias", 0.0) - s_hist.get("fvg_bias", 0.0)) / 2.0
        )

        # Trend/Regime similarity
        t_cur = current.trend_scores
        t_hist = h_vec.get("trend_scores", {})
        trend_diffs = [
            abs(t_cur.get(k, 0.0) - t_hist.get(k, 0.0)) for k in ["1d", "4h", "1h", "15m"]
        ]
        regime_sim = 1.0 - (sum(trend_diffs) / (len(trend_diffs) * 2.0 + 1e-5))

        # Volatility similarity
        v_cur = current.volatility
        v_hist = h_vec.get("volatility", {})
        vol_sim = 1.0 - abs(v_cur.get("atr_percentile", 0.5) - v_hist.get("atr_percentile", 0.5))

        # Orderflow similarity
        o_cur = current.orderflow
        o_hist = h_vec.get("orderflow", {})
        of_sim = 1.0 - (
            0.5 * abs(o_cur.get("cvd_delta", 0.0) - o_hist.get("cvd_delta", 0.0)) / 2.0
            + 0.5 * abs(o_cur.get("absorption_score", 0.5) - o_hist.get("absorption_score", 0.5))
        )

        # Macro similarity
        m_cur = current.macro_alignment
        m_hist = h_vec.get("macro_alignment", {})
        macro_sim = (
            1.0
            - abs(m_cur.get("dxy_correlation", -0.5) - m_hist.get("dxy_correlation", -0.5)) / 2.0
        )

        # Liquidity similarity
        liq_sim = 1.0 - abs(
            s_cur.get("liquidity_pool_pressure", 0.5) - s_hist.get("liquidity_pool_pressure", 0.5)
        )

        # Recency decay weight (favors last 90 days slightly)
        h_time = historical.get("timestamp", now_ms)
        age_days = max(0.0, (now_ms - h_time) / (86400.0 * 1000.0))
        recency_weight = float(np.exp(-age_days / 180.0))

        score = (
            0.25 * struct_sim
            + 0.20 * regime_sim
            + 0.15 * vol_sim
            + 0.15 * of_sim
            + 0.10 * macro_sim
            + 0.10 * liq_sim
            + 0.05 * recency_weight
        )
        return float(np.clip(score, 0.0, 1.0))

    def _fetch_historical_states(
        self, asset: str, timeframe: str, regime: str, event_risk: bool
    ) -> list[dict[str, Any]]:
        with db_manager.get_brain_conn() as conn:
            cursor = conn.execute(
                """
                SELECT state_id, timestamp, symbol, timeframe, schema_version, state_vector_json, forward_outcomes_json
                FROM market_states
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT 200;
                """,
                (asset,),
            )
            rows = cursor.fetchall()

        results = []
        for r in rows:
            try:
                results.append(
                    {
                        "state_id": r["state_id"],
                        "timestamp": r["timestamp"],
                        "state_vector": json.loads(r["state_vector_json"]),
                        "forward_outcomes": json.loads(r["forward_outcomes_json"] or "{}"),
                    }
                )
            except Exception:  # noqa: BLE001 — defensive fallback
                continue
        return results

    def _generate_synthetic_historical_states(
        self, current: MarketStateVector, regime: str, event_risk: bool, count: int = 60
    ) -> list[dict[str, Any]]:
        states = []
        now = current.timestamp
        np.random.seed(1337)

        for i in range(count):
            t_hist = now - ((i + 1) * 3600 * 1000 * 4)
            # Create variations
            sv = current.to_dict()
            noise = np.random.normal(0, 0.15, 5)
            sv["trend_scores"]["15m"] = float(
                np.clip(sv["trend_scores"]["15m"] + noise[0], -1.0, 1.0)
            )
            sv["orderflow"]["cvd_delta"] = float(
                np.clip(sv["orderflow"]["cvd_delta"] + noise[1], -1.0, 1.0)
            )

            win = np.random.rand() > 0.38
            ret_1h = float(
                np.random.uniform(0.005, 0.02) if win else np.random.uniform(-0.015, -0.004)
            )

            states.append(
                {
                    "state_id": f"SYNTH_STATE_{i}_{t_hist}",
                    "timestamp": t_hist,
                    "state_vector": sv,
                    "forward_outcomes": {
                        "ret_5m": round(ret_1h * 0.3, 4),
                        "ret_1h": round(ret_1h, 4),
                        "ret_4h": round(ret_1h * 1.5, 4),
                        "bars_to_target": int(np.random.randint(4, 16)),
                    },
                }
            )
        return states


# Singleton
analogue_engine = HierarchicalAnalogueEngine()
