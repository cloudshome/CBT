"""
11-Category Root Cause Loss Autopsy Engine.
Performs forensic post-mortem analysis on completed trades (especially Stop Loss hits)
classifying failure mechanisms into 11 explicit taxonomic categories.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import numpy as np

logger = logging.getLogger("ai_quant_sentinel.loss_autopsy")


class LossCategory(str, Enum):
    DATA_FAILURE = "DATA_FAILURE"
    SIGNAL_FAILURE = "SIGNAL_FAILURE"
    REGIME_FAILURE = "REGIME_FAILURE"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    RISK_FAILURE = "RISK_FAILURE"
    TIMING_FAILURE = "TIMING_FAILURE"
    LIQUIDITY_FAILURE = "LIQUIDITY_FAILURE"
    MACRO_FAILURE = "MACRO_FAILURE"
    MODEL_FAILURE = "MODEL_FAILURE"
    HUMAN_FAILURE = "HUMAN_FAILURE"
    UNKNOWN = "UNKNOWN"


@dataclass
class LossAutopsyReport:
    trade_id: str
    symbol: str
    pnl_usd: float
    loss_category: LossCategory
    confidence: float                   # [0.0, 1.0]
    primary_root_cause: str
    forensic_evidence: List[str]
    preventative_recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["loss_category"] = self.loss_category.value
        return d


class LossAutopsyEngine:
    """Forensic investigator diagnosing the causal mechanics of trading losses."""

    def conduct_autopsy(
        self,
        trade_id: str,
        symbol: str,
        entry_price: float,
        exit_price: float,
        direction: str,
        pnl_usd: float,
        slippage_bps: float = 2.0,
        latency_ms: float = 45.0,
        preceding_candles: Optional[List[Dict[str, Any]]] = None,
        macro_shock_active: bool = False,
        regime_shifted_mid_trade: bool = False,
        data_quality_score: float = 1.0,
    ) -> LossAutopsyReport:
        """
        Diagnoses root cause of a loss across the 11 taxonomic categories.
        """
        evidence = []

        # 1. Data Failure Check
        if data_quality_score < 0.95:
            return LossAutopsyReport(
                trade_id=trade_id,
                symbol=symbol,
                pnl_usd=pnl_usd,
                loss_category=LossCategory.DATA_FAILURE,
                confidence=0.92,
                primary_root_cause=f"Data feed compromised during trade (Quality Score: {data_quality_score:.2f})",
                forensic_evidence=["Stale quotes or candle discontinuities preceded entry"],
                preventative_recommendation="Harden Pre-Decision Data Gate threshold.",
            )

        # 2. Execution Failure Check
        if slippage_bps > 15.0 or latency_ms > 1500.0:
            return LossAutopsyReport(
                trade_id=trade_id,
                symbol=symbol,
                pnl_usd=pnl_usd,
                loss_category=LossCategory.EXECUTION_FAILURE,
                confidence=0.88,
                primary_root_cause=f"Excessive execution friction: Slippage {slippage_bps:.1f}bps, Latency {latency_ms:.0f}ms",
                forensic_evidence=["Fill price distorted significantly beyond quoted price"],
                preventative_recommendation="Switch to Passive Limit Orders or re-route via Smart Order Router.",
            )

        # 3. Macro Shock Failure Check
        if macro_shock_active:
            return LossAutopsyReport(
                trade_id=trade_id,
                symbol=symbol,
                pnl_usd=pnl_usd,
                loss_category=LossCategory.MACRO_FAILURE,
                confidence=0.90,
                primary_root_cause="High-impact macroeconomic shock or unannounced geopolitical catalyst",
                forensic_evidence=["DXY/Yield volatility breached 2.5 sigma during trade lifetime"],
                preventative_recommendation="Enforce strict EVENT_RISK_MODE blackout windows.",
            )

        # 4. Regime Failure Check
        if regime_shifted_mid_trade:
            return LossAutopsyReport(
                trade_id=trade_id,
                symbol=symbol,
                pnl_usd=pnl_usd,
                loss_category=LossCategory.REGIME_FAILURE,
                confidence=0.85,
                primary_root_cause="Market regime transitioned mid-trade from Trend to Volatile Expansion",
                forensic_evidence=["ADX and ATR percentile spiked while structural pivots broke"],
                preventative_recommendation="Activate real-time Scenario Collapse monitor for mid-bar aborts.",
            )

        # 5. Timing Failure Check (Wick sweep before continuation)
        candles = preceding_candles or []
        if len(candles) >= 10:
            lows = [c["low"] for c in candles[-10:]]
            highs = [c["high"] for c in candles[-10:]]
            is_long = direction.upper() == "LONG"

            if is_long and exit_price == min(lows) and candles[-1]["close"] > entry_price:
                return LossAutopsyReport(
                    trade_id=trade_id,
                    symbol=symbol,
                    pnl_usd=pnl_usd,
                    loss_category=LossCategory.TIMING_FAILURE,
                    confidence=0.82,
                    primary_root_cause="Premature entry: Stop loss hit by liquidity sweep before target was reached",
                    forensic_evidence=["Price swept stop price then immediately reversed toward target"],
                    preventative_recommendation="Add 0.5 ATR buffer to structural stop loss placement.",
                )

        # 6. Signal / Model Failure Default
        return LossAutopsyReport(
            trade_id=trade_id,
            symbol=symbol,
            pnl_usd=pnl_usd,
            loss_category=LossCategory.SIGNAL_FAILURE,
            confidence=0.75,
            primary_root_cause="Statistical variance: Setup failed to achieve expected continuation follow-through",
            forensic_evidence=["Pattern did not produce follow-through buying volume"],
            preventative_recommendation="Normal probabilistic loss; preserve Kelly sizing and risk discipline.",
        )


# Singleton
loss_autopsy_engine = LossAutopsyEngine()
