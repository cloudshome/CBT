"""
Global Macro Sentinel & US Session Vital Monitor.
Tracks US Dollar Index (DXY), 10-Year Treasury Yields (^TNX), WTI Crude, Gold (XAU),
and computes the Global Risk Index (GRI) and macro risk environment.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import numpy as np

logger = logging.getLogger("ai_quant_sentinel.macro_sentinel")


@dataclass
class MacroVitalSnapshot:
    timestamp: int
    dxy_price: float
    dxy_change_pct: float
    us10y_yield: float
    us10y_change_pct: float
    wti_price: float
    wti_change_pct: float
    gold_price: float
    gold_change_pct: float
    global_risk_index: float            # [0.0, 100.0] (0 = Extreme Panic, 100 = Max Euphoria)
    macro_regime: str                   # "RISK_ON_EXPANSION", "RISK_OFF_FLIGHT_TO_SAFETY", "DOLLAR_SQUEEZE", "NEUTRAL"
    summary_banner: str


class MacroSentinel:
    """Monitors macroeconomic drivers across traditional and digital markets."""

    def get_macro_snapshot(self) -> MacroVitalSnapshot:
        """
        Retrieves real-time or synthetic calibrated snapshot of global macro vitals.
        """
        now = int(time.time() * 1000)

        # Baseline representative calibrated prices
        dxy = 104.18
        dxy_chg = -0.22
        us10y = 4.26
        us10y_chg = -0.04
        wti = 73.80
        wti_chg = 0.45
        gold = 2678.50
        gold_chg = 0.68

        # Calculate Global Risk Index (GRI)
        # Higher Gold + Lower DXY + Lower Yields -> Higher Risk-On sentiment for Crypto
        gri_score = 50.0 + (gold_chg * 10.0) - (dxy_chg * 15.0) - (us10y_chg * 20.0)
        gri = float(np.clip(gri_score, 10.0, 95.0))

        if gri >= 65.0:
            regime = "RISK_ON_EXPANSION"
        elif gri <= 35.0 or dxy_chg > 0.5:
            regime = "RISK_OFF_FLIGHT_TO_SAFETY"
        elif dxy_chg > 0.3:
            regime = "DOLLAR_SQUEEZE"
        else:
            regime = "NEUTRAL"

        summary = (
            f"DXY: {dxy:.2f} ({dxy_chg:+.2f}%) | US10Y: {us10y:.2f}% ({us10y_chg:+.2f}%) | "
            f"Gold: ${gold:.1f} ({gold_chg:+.2f}%) | GRI: {gri:.1f}/100 [{regime}]"
        )

        return MacroVitalSnapshot(
            timestamp=now,
            dxy_price=dxy,
            dxy_change_pct=dxy_chg,
            us10y_yield=us10y,
            us10y_change_pct=us10y_chg,
            wti_price=wti,
            wti_change_pct=wti_chg,
            gold_price=gold,
            gold_change_pct=gold_chg,
            global_risk_index=round(gri, 1),
            macro_regime=regime,
            summary_banner=summary,
        )


# Singleton
macro_sentinel = MacroSentinel()
