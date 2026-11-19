"""core/strategies — Production Trading Strategies Package."""

from core.strategies.p2_risk_parity import (
    AssetMetrics,
    TodayDeskSnapshot,
    evaluate_p2_rp_snapshot,
    format_today_desk_briefing,
    load_candles_for_p2_rp,
)

__all__ = [
    "AssetMetrics",
    "TodayDeskSnapshot",
    "evaluate_p2_rp_snapshot",
    "format_today_desk_briefing",
    "load_candles_for_p2_rp",
]
