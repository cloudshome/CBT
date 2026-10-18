"""
core/arbitrage/cex_execution_model.py
=====================================
Institutional CEX Execution Realism, Depth Depletion & Partial Fill Engine.

Enforces:
- Gate 6: CEX execution realism modeling order book depth depletion, queue position,
          slippage across multi-level book walks, and partial fill boundaries.
- Rejects naive top-of-book pricing: A $50,000 order is not executable at best bid/ask.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger("sky.arbitrage.cex_execution")


class CexFillStatus(StrEnum):
    """Execution status for CEX market and IOC orders (Gate 6)."""

    COMPLETE_FILL = "COMPLETE_FILL"
    PARTIAL_FILL = "PARTIAL_FILL"
    REJECTED_INSUFFICIENT_DEPTH = "REJECTED_INSUFFICIENT_DEPTH"
    REJECTED_MAX_SLIPPAGE = "REJECTED_MAX_SLIPPAGE"


@dataclass(frozen=True)
class CexLevelFill:
    """Detailed record of an individual order book level consumed."""

    level_index: int
    price: float
    quantity: float
    notional_usd: float
    level_slippage_bps: float


@dataclass(frozen=True)
class CexExecutionResult:
    """Comprehensive outcome of depth-walking CEX order book."""

    venue: str  # "BINANCE", "BYBIT", "HYPERLIQUID"
    symbol: str
    side: str  # "BUY", "SELL"
    requested_notional: float
    filled_notional: float
    unfilled_notional: float
    fill_status: CexFillStatus
    vwap_price: float
    best_price: float
    slippage_bps: float
    taker_fee_usd: float
    depth_levels_consumed: int
    fill_ratio: float
    levels: list[CexLevelFill]


class CexExecutionEngine:
    """
    Simulates realistic market order execution through L2/L3 order book depth.
    Accounts for queue decay, non-linear slippage, and partial fill thresholds.
    """

    @staticmethod
    def simulate_fill(
        venue: str,
        symbol: str,
        side: str,  # "BUY" (walk asks) or "SELL" (walk bids)
        requested_notional: float,
        book_levels: list[tuple[float, float]],  # List of (price, quantity)
        taker_fee_bps: float = 4.0,  # 4.0 bps default taker fee
        max_slippage_bps: float = 50.0,  # 50 bps max acceptable slippage
        queue_fillability_ratio: float = 0.85,  # 85% fillability factor due to queue front-running
    ) -> CexExecutionResult:
        if requested_notional <= 0:
            raise ValueError("requested_notional must be strictly positive.")
        if not book_levels:
            return CexExecutionResult(
                venue=venue,
                symbol=symbol,
                side=side,
                requested_notional=requested_notional,
                filled_notional=0.0,
                unfilled_notional=requested_notional,
                fill_status=CexFillStatus.REJECTED_INSUFFICIENT_DEPTH,
                vwap_price=0.0,
                best_price=0.0,
                slippage_bps=0.0,
                taker_fee_usd=0.0,
                depth_levels_consumed=0,
                fill_ratio=0.0,
                levels=[],
            )

        best_price = book_levels[0][0]
        remaining_notional = requested_notional
        filled_notional = 0.0
        total_quantity = 0.0
        accumulated_cost = 0.0
        levels_detail: list[CexLevelFill] = []
        levels_consumed = 0

        for idx, (px, qty) in enumerate(book_levels):
            if remaining_notional <= 0.0001:
                break

            # Calculate slippage relative to best price
            if side.upper() == "BUY":
                level_slip_bps = max(0.0, (px - best_price) / best_price * 10_000)
            else:
                level_slip_bps = max(0.0, (best_price - px) / best_price * 10_000)

            # Check max slippage constraint
            if level_slip_bps > max_slippage_bps:
                break

            # Apply queue fillability factor (models adverse selection / cancellation)
            effective_qty = qty * queue_fillability_ratio
            level_notional = px * effective_qty

            if remaining_notional <= level_notional:
                # Partial level fill completes the order
                fill_notional = remaining_notional
                fill_qty = fill_notional / px
                remaining_notional = 0.0
            else:
                # Consume entire effective level depth
                fill_notional = level_notional
                fill_qty = effective_qty
                remaining_notional -= fill_notional

            filled_notional += fill_notional
            total_quantity += fill_qty
            accumulated_cost += fill_notional

            levels_detail.append(
                CexLevelFill(
                    level_index=idx,
                    price=px,
                    quantity=fill_qty,
                    notional_usd=fill_notional,
                    level_slippage_bps=level_slip_bps,
                )
            )
            levels_consumed += 1

        if total_quantity <= 0:
            return CexExecutionResult(
                venue=venue,
                symbol=symbol,
                side=side,
                requested_notional=requested_notional,
                filled_notional=0.0,
                unfilled_notional=requested_notional,
                fill_status=CexFillStatus.REJECTED_MAX_SLIPPAGE,
                vwap_price=0.0,
                best_price=best_price,
                slippage_bps=0.0,
                taker_fee_usd=0.0,
                depth_levels_consumed=0,
                fill_ratio=0.0,
                levels=[],
            )

        vwap = accumulated_cost / total_quantity
        if side.upper() == "BUY":
            slippage_bps = max(0.0, (vwap - best_price) / best_price * 10_000)
        else:
            slippage_bps = max(0.0, (best_price - vwap) / best_price * 10_000)

        fill_ratio = filled_notional / requested_notional
        if fill_ratio >= 0.9999:
            status = CexFillStatus.COMPLETE_FILL
        elif fill_ratio > 0.05:
            status = CexFillStatus.PARTIAL_FILL
        else:
            status = CexFillStatus.REJECTED_INSUFFICIENT_DEPTH

        taker_fee_usd = filled_notional * (taker_fee_bps / 10_000)

        return CexExecutionResult(
            venue=venue,
            symbol=symbol,
            side=side,
            requested_notional=requested_notional,
            filled_notional=filled_notional,
            unfilled_notional=remaining_notional,
            fill_status=status,
            vwap_price=vwap,
            best_price=best_price,
            slippage_bps=slippage_bps,
            taker_fee_usd=taker_fee_usd,
            depth_levels_consumed=levels_consumed,
            fill_ratio=fill_ratio,
            levels=levels_detail,
        )
