"""
core/screener/radar_executor.py
===============================
Dedicated Execution Engine for the $2,000 Alpha Opportunity Radar Satellite Desk.

Institutional Invariants:
1. Isolated Capital: Strictly bound to $2,000 satellite allocation (book_id="RADAR_ALPHA").
   Never touches or impairs the $10,000 Main Sovereign Desk.
2. Anti-Shitcoin Liquidity Hurdle: Strictly requires minimum $20M 24h volume and Binance Futures eligibility.
3. Asymmetric Sizing: 1.0% ($20.00) max risk per trade, max 2 concurrent active positions.
4. Two-Way Execution:
   - Early Momentum / Pre-Breakout -> LONG
   - Parabolic Blow-Off Exhaustion (+50% to +100% pump, 5x+ RVOL) -> SHORT
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from core.portfolio_shadow import portfolio_shadow
from core.screener.opportunity_hunter import opportunity_hunter

logger = logging.getLogger("sky.screener.radar_executor")


class RadarAlphaExecutor:
    """Executes high-conviction momentum and exhaustion setups on the $2,000 Alpha Radar Book."""

    def __init__(
        self,
        allocated_capital_usd: float = 2000.0,
        max_open_positions: int = 2,
        risk_per_trade_usd: float = 20.0,
        min_24h_volume_usd: float = 20_000_000.0,
        min_market_attention: float = 80.0,
    ) -> None:
        self.allocated_capital_usd = allocated_capital_usd
        self.max_open_positions = max_open_positions
        self.risk_per_trade_usd = risk_per_trade_usd
        self.min_24h_volume_usd = min_24h_volume_usd
        self.min_market_attention = min_market_attention
        self.book_id = "RADAR_ALPHA"
        self.is_auto_pilot: bool = True
        self._last_scan_ms: int = 0
        self.recent_log: list[dict[str, Any]] = []

    def get_desk_summary(self) -> dict[str, Any]:
        """Returns the isolated accounting and live state of the $2,000 Alpha Radar Desk."""
        accounting = portfolio_shadow.get_portfolio_accounting(
            starting_capital=self.allocated_capital_usd, book_id=self.book_id
        )
        open_pos = portfolio_shadow.get_open_positions(book_id=self.book_id)

        return {
            "desk_name": "Alpha Opportunity Radar Desk",
            "book_id": self.book_id,
            "allocated_capital_usd": self.allocated_capital_usd,
            "virtual_equity_usd": accounting.get("virtual_equity", self.allocated_capital_usd),
            "settled_cash_usd": accounting.get("settled_cash", self.allocated_capital_usd),
            "realized_pnl_usd": accounting.get("total_realized_pnl", 0.0),
            "unrealized_pnl_usd": accounting.get("total_unrealized_pnl", 0.0),
            "win_rate_pct": accounting.get("win_rate_pct", 0.0),
            "profit_factor": accounting.get("profit_factor", 0.0),
            "open_positions_count": len(open_pos),
            "max_open_positions": self.max_open_positions,
            "risk_per_trade_usd": self.risk_per_trade_usd,
            "min_volume_hurdle_usd": self.min_24h_volume_usd,
            "auto_pilot_enabled": self.is_auto_pilot,
            "open_positions": open_pos,
            "last_scan_ms": self._last_scan_ms,
            "recent_activity": self.recent_log[-10:],
        }

    async def evaluate_radar_candidates(self) -> list[dict[str, Any]]:
        """
        Filters OpportunityHunter candidates through strict institutional liquidity & geometry hurdles.
        Returns executable candidate proposals for the $2,000 book.
        """
        try:
            opps = await opportunity_hunter.scan_market()
        except Exception as e:
            logger.warning(f"RadarAlphaExecutor scan error: {e}")
            return []

        candidates: list[dict[str, Any]] = []

        for opp in opps:
            # Hurdle 1: Must be Binance Futures eligible (guarantees shorting & deep book liquidity)
            if not opp.futures_eligible:
                continue

            # Hurdle 2: Strict Volume Floor ($20M minimum 24h volume - filters out dead microcaps)
            if opp.quote_volume_24h_usd < self.min_24h_volume_usd:
                continue

            # Hurdle 3: High Market Attention (RVOL + Volume Acceleration >= 80)
            if opp.market_attention_score < self.min_market_attention:
                continue

            cur_px = float(opp.current_price or 0.0)
            if cur_px <= 0:
                continue

            cat = opp.opportunity_category.value
            direction = opp.recommended_direction.upper() if opp.recommended_direction in ("LONG", "SHORT") else "LONG"
            thesis = opp.primary_rationale

            # Directional Classification:
            # Exhaustion / breakdown -> SHORT
            # Momentum / compression / reclaim -> LONG
            if cat in ("BLOW_OFF_EXHAUSTION", "BEARISH_CONTINUATION"):
                direction = "SHORT"
            elif cat in ("EMERGING_MOMENTUM", "CONFIRMED_BREAKOUT", "PRE_BREAKOUT_COMPRESSION", "CAPITULATION_RECOVERY"):
                direction = "LONG"
            else:
                continue

            # Invalidation / Stop-Loss Geometry Calculation
            sl = float(opp.invalidation_level or 0.0)
            if direction == "LONG":
                # Valid SL must be below entry price
                if sl <= 0 or sl >= cur_px or ((cur_px - sl) / cur_px) > 0.08:
                    sl = round(cur_px * 0.965, 6)  # 3.5% conservative structural SL
                tp = round(cur_px + (cur_px - sl) * 2.2, 6)  # 2.2R target
            else:
                # Valid SL must be above entry price for SHORT
                if sl <= 0 or sl <= cur_px or ((sl - cur_px) / cur_px) > 0.08:
                    sl = round(cur_px * 1.035, 6)  # 3.5% conservative structural SL
                tp = round(cur_px - (sl - cur_px) * 2.2, 6)  # 2.2R target
                if tp <= 0:
                    tp = round(cur_px * 0.5, 6)

            stop_dist = abs(cur_px - sl)
            if stop_dist <= 0:
                continue

            # Fixed Dollar Risk Sizing: Risk exactly $20.00 (1% of $2,000 book)
            units = round(self.risk_per_trade_usd / stop_dist, 4)
            if units <= 0:
                continue

            candidates.append(
                {
                    "symbol": opp.symbol,
                    "direction": direction,
                    "category": cat,
                    "entry_price": cur_px,
                    "stop_loss": sl,
                    "take_profit": tp,
                    "size": units,
                    "risk_usd": round(units * stop_dist, 2),
                    "notional_usd": round(units * cur_px, 2),
                    "volume_24h_usd": opp.quote_volume_24h_usd,
                    "rvol": opp.relative_volume_ratio,
                    "attention_score": opp.market_attention_score,
                    "thesis": f"Alpha Radar [{cat}]: {thesis[:100]}",
                }
            )

        # Sort by Market Attention Score DESC
        candidates.sort(key=lambda c: c["attention_score"], reverse=True)
        return candidates

    async def execute_top_candidate(self, candidate: dict[str, Any]) -> str | None:
        """Deploys a qualified Radar opportunity into the $2,000 Alpha Book."""
        sym = candidate["symbol"]
        direction = candidate["direction"]
        units = candidate["size"]
        entry_px = candidate["entry_price"]
        sl = candidate["stop_loss"]
        tp = candidate["take_profit"]
        reason = candidate["thesis"]

        try:
            pos_id = portfolio_shadow.open_position(
                symbol=sym,
                direction=direction,
                size=units,
                entry_price=entry_px,
                stop_loss=sl,
                take_profit=tp,
                entry_reason=reason,
                enforce_atomic_limits=True,
                max_open_limit=self.max_open_positions,
                max_risk_usd=self.risk_per_trade_usd * 1.25,
                prevent_duplicate_symbol=True,
                book_id=self.book_id,
            )
            self._record_activity(
                sym,
                "EXECUTE",
                f"Opened {direction} on $2,000 Alpha Desk (Risk: ${candidate['risk_usd']:.2f}, Vol: ${candidate['volume_24h_usd']/1e6:.1f}M)",
            )
            logger.info(
                f"[RADAR_ALPHA] Successfully executed {direction} {sym} on $2,000 Alpha Book: {pos_id}"
            )
            return pos_id
        except Exception as e:
            logger.info(f"[RADAR_ALPHA] Candidate deployment rejected: {e}")
            return None

    def _record_activity(self, symbol: str, action: str, details: str) -> None:
        self.recent_log.append(
            {
                "timestamp_ms": int(time.time() * 1000),
                "symbol": symbol,
                "action": action,
                "details": details,
            }
        )
        if len(self.recent_log) > 50:
            self.recent_log = self.recent_log[-50:]


# Singleton Executor Instance
radar_alpha_executor = RadarAlphaExecutor()
