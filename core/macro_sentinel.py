"""
Global Macro Sentinel & US Session Vital Monitor.
Tracks US Dollar Index (DXY), 10-Year Treasury Yields (^TNX), WTI Crude, Gold (XAU),
and computes the Global Risk Index (GRI) and macro risk environment.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

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
    global_risk_index: float  # [0.0, 100.0] (0 = Extreme Panic, 100 = Max Euphoria)
    macro_regime: (
        str  # "RISK_ON_EXPANSION", "RISK_OFF_FLIGHT_TO_SAFETY", "DOLLAR_SQUEEZE", "NEUTRAL"
    )
    summary_banner: str
    vix: float = 15.20
    fear_and_greed: float = 68.0

    @property
    def dxy(self) -> float:
        return self.dxy_price

    @property
    def dxy_index(self) -> float:
        return self.dxy_price

    @property
    def us10y(self) -> float:
        return self.us10y_yield

    @property
    def gold(self) -> float:
        return self.gold_price

    @property
    def regime(self) -> str:
        return self.macro_regime

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


class MacroSentinel:
    """Monitors macroeconomic drivers across traditional and digital markets."""

    def get_macro_snapshot(self) -> MacroVitalSnapshot:
        """
        Retrieves real-time or synthetic calibrated snapshot of global macro vitals.
        Pulls directly from core/macro_live_collector.py SQLite cache with calibrated fallbacks.
        """
        now = int(time.time() * 1000)

        # Pull from live macro collector cache
        from core.macro_live_collector import macro_live_collector

        dxy_rec = macro_live_collector.get_indicator("DXY") or {}
        us10y_rec = macro_live_collector.get_indicator("US10Y") or {}
        wti_rec = macro_live_collector.get_indicator("WTI_CRUDE") or {}
        gold_rec = macro_live_collector.get_indicator("GOLD") or {}
        vix_rec = macro_live_collector.get_indicator("VIX") or {}
        fng_rec = macro_live_collector.get_indicator("FEAR_AND_GREED") or {}

        dxy = float(dxy_rec.get("value", 104.18))
        dxy_chg = float(dxy_rec.get("change_pct", -0.22))
        us10y = float(us10y_rec.get("value", 4.26))
        us10y_chg = float(us10y_rec.get("change_pct", -0.04))
        wti = float(wti_rec.get("value", 73.80))
        wti_chg = float(wti_rec.get("change_pct", 0.45))
        gold = float(gold_rec.get("value", 2678.50))
        gold_chg = float(gold_rec.get("change_pct", 0.68))
        vix = float(vix_rec.get("value", 15.20))
        fng = float(fng_rec.get("value", 68.0))

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
            vix=vix,
            fear_and_greed=fng,
        )


# Singleton
macro_sentinel = MacroSentinel()
