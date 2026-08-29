"""
Phase 11: Multi-Timeframe Context Engine.
Synthesizes a hierarchical context stack across 1D, 4H, 1H, 15m, 5m, and 1m.
Derives HTF Trend Context, MTF Pullback/Liquidity State, and LTF Structural Triggers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import numpy as np

from core.sky_intelligence.types import MultiTimeframeContext

logger = logging.getLogger("sky_intelligence.multi_timeframe")


class MultiTimeframeEngine:
    """
    Hierarchical Multi-Timeframe Engine.
    """

    def compile_mtf_context(
        self,
        candles_by_tf: Dict[str, List[Dict[str, Any]]],
    ) -> MultiTimeframeContext:
        """
        Builds the 6-timeframe context stack and computes composite alignment score.
        """
        # 1D Trend
        c_1d = candles_by_tf.get("1d", [])
        trend_1d = self._eval_tf_trend(c_1d)

        # 4H Trend
        c_4h = candles_by_tf.get("4h", [])
        trend_4h = self._eval_tf_trend(c_4h)

        # 1H State
        c_1h = candles_by_tf.get("1h", [])
        state_1h = self._eval_tf_trend(c_1h)

        # 15m State
        c_15m = candles_by_tf.get("15m", [])
        state_15m = self._eval_tf_trend(c_15m)

        # 5m Trigger
        c_5m = candles_by_tf.get("5m", [])
        trigger_5m = self._eval_tf_trigger(c_5m)

        # 1m Trigger
        c_1m = candles_by_tf.get("1m", [])
        trigger_1m = self._eval_tf_trigger(c_1m)

        # Evaluate Confluence & Stack Alignment
        bull_votes = sum(
            1 for s in [trend_1d, trend_4h, state_1h, state_15m, trigger_5m, trigger_1m] if "BULL" in s
        )
        bear_votes = sum(
            1 for s in [trend_1d, trend_4h, state_1h, state_15m, trigger_5m, trigger_1m] if "BEAR" in s
        )

        if bull_votes >= 4 and bear_votes <= 1:
            stack = "BULLISH_CONFLUENT"
            confluence = 70.0 + (bull_votes * 5.0)
        elif bear_votes >= 4 and bull_votes <= 1:
            stack = "BEARISH_CONFLUENT"
            confluence = 70.0 + (bear_votes * 5.0)
        else:
            stack = "MIXED_CONFLICT"
            confluence = 40.0

        import time
        now_ts = int(time.time() * 1000)

        return MultiTimeframeContext(
            timestamp=now_ts,
            htf_1d_trend=trend_1d,
            htf_4h_trend=trend_4h,
            mtf_1h_state=state_1h,
            mtf_15m_state=state_15m,
            ltf_5m_trigger=trigger_5m,
            ltf_1m_trigger=trigger_1m,
            confluence_score=round(min(100.0, confluence), 1),
            stack_alignment=stack,
        )

    def _eval_tf_trend(self, candles: List[Dict[str, Any]]) -> str:
        if len(candles) < 20:
            return "NEUTRAL_INSUFFICIENT_DATA"
        closes = [float(c["close"]) for c in candles]
        ema20 = float(np.mean(closes[-20:]))
        ema50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else ema20
        curr_close = closes[-1]

        if curr_close > ema20 and ema20 >= ema50:
            return "BULLISH_EXPANSION"
        elif curr_close < ema20 and ema20 <= ema50:
            return "BEARISH_EXPANSION"
        elif curr_close < ema20 and ema20 > ema50:
            return "BULLISH_PULLBACK"
        elif curr_close > ema20 and ema20 < ema50:
            return "BEARISH_PULLBACK"
        return "RANGING_NEUTRAL"

    def _eval_tf_trigger(self, candles: List[Dict[str, Any]]) -> str:
        if len(candles) < 5:
            return "NEUTRAL"
        last = candles[-1]
        op = float(last["open"])
        cl = float(last["close"])
        hi = float(last["high"])
        lo = float(last["low"])
        rng = max(hi - lo, 0.0001)

        if cl > op and (cl - lo) / rng >= 0.75:
            return "BULLISH_DISPLACEMENT_TRIGGER"
        elif cl < op and (hi - cl) / rng >= 0.75:
            return "BEARISH_DISPLACEMENT_TRIGGER"
        return "NEUTRAL_CONSOLIDATION"


# Global singleton instance
multi_timeframe_engine = MultiTimeframeEngine()
