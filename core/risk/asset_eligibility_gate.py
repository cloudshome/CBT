"""
core/risk/asset_eligibility_gate.py
===================================
Milestone 31: Deterministic Asset Eligibility & Hard Liquidity Gate.

Mandates:
1. Enforces strict Tier-1 Asset Whitelist on Main Sovereign Desk (BTC, ETH, SOL, PAXG, XAU).
2. Deterministic liquidity hurdles: 24h Volume >= $25M, L2 Depth (100 bps) >= $50k, Spread <= 15 bps.
3. Explicit Constitutional Rule: NO AI-generated opportunity score, Mastermind Arbiter,
   or confluence metric may bypass or relax these eligibility gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

TIER1_CORE_WHITELIST = {
    "BTC/USDT",
    "BTCUSDT",
    "ETH/USDT",
    "ETHUSDT",
    "SOL/USDT",
    "SOLUSDT",
    "PAXG/USDT",
    "PAXGUSDT",
    "XAU/USD",
    "XAUUSD",
}

# Tier-1 Canary Eligible Universe (BTC & ETH only for initial live canary)
TIER1_CANARY_WHITELIST = {
    "BTC/USDT",
    "BTCUSDT",
    "ETH/USDT",
    "ETHUSDT",
}

# Assets placed under forward paper observation pending statistical qualification
PAPER_OBSERVATION_SYMBOLS = {
    "SOL/USDT",
    "SOLUSDT",
}

BANNED_MICROCAP_SYMBOLS = {
    "KORU",
    "AKE",
    "DOOD",
    "BMT",
    "MAGMA",
    "IOST",
    "COMP",
    "IRYS",
}


class AssetEligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    REJECTED_NOT_WHITELISTED = "REJECTED_NOT_WHITELISTED"
    REJECTED_TIER1_CANARY_RESTRICTED = "REJECTED_TIER1_CANARY_RESTRICTED"
    REJECTED_INSUFFICIENT_VOLUME = "REJECTED_INSUFFICIENT_VOLUME"
    REJECTED_INSUFFICIENT_DEPTH = "REJECTED_INSUFFICIENT_DEPTH"
    REJECTED_EXCESSIVE_SPREAD = "REJECTED_EXCESSIVE_SPREAD"
    REJECTED_BANNED_MICROCAP = "REJECTED_BANNED_MICROCAP"


@dataclass(frozen=True)
class AssetLiquidityMetrics:
    symbol: str
    volume_24h_usd: float
    order_book_depth_100bps_usd: float
    bid_ask_spread_bps: float
    exchange_count: int = 1


@dataclass(frozen=True)
class AssetEligibilityDecision:
    symbol: str
    status: AssetEligibilityStatus
    is_eligible: bool
    rationale: str
    desk: str = "MAIN_SOVEREIGN"
    ai_override_attempted: bool = False


class DeterministicAssetEligibilityGate:
    """
    Deterministic gatekeeper that evaluates symbol eligibility before any
    order generation, shadow position opening, or execution routing.
    """

    def __init__(
        self,
        min_24h_volume_usd: float = 25_000_000.0,
        min_depth_100bps_usd: float = 50_000.0,
        max_spread_bps: float = 15.0,
    ) -> None:
        self.min_24h_volume_usd = min_24h_volume_usd
        self.min_depth_100bps_usd = min_depth_100bps_usd
        self.max_spread_bps = max_spread_bps

    def evaluate_symbol_eligibility(
        self,
        symbol: str,
        liquidity: AssetLiquidityMetrics | None = None,
        desk: str = "MAIN_SOVEREIGN",
        ai_opportunity_score: float | None = None,
        mtf_alignment: str | None = None,
    ) -> AssetEligibilityDecision:
        clean_sym = symbol.replace("/", "").replace("_", "").upper()
        raw_sym = symbol.upper()

        # Check banned microcaps first
        base_asset = clean_sym.replace("USDT", "").replace("USD", "")
        if base_asset in BANNED_MICROCAP_SYMBOLS or raw_sym in BANNED_MICROCAP_SYMBOLS:
            return AssetEligibilityDecision(
                symbol=symbol,
                status=AssetEligibilityStatus.REJECTED_BANNED_MICROCAP,
                is_eligible=False,
                rationale=f"Asset '{symbol}' is a banned speculative microcap. Pre-trade quarantine enforced.",
                desk=desk,
                ai_override_attempted=bool(ai_opportunity_score is not None),
            )

        # Tier-1 Canary Live Whitelist Check (BTC, ETH, and conditional ALIGNED-only SOL)
        if desk in ("TIER1_CANARY", "CANARY"):
            is_canary_core = any(
                clean_sym == t.replace("/", "").replace("_", "") for t in TIER1_CANARY_WHITELIST
            )
            is_sol = clean_sym in ("SOLUSDT", "SOLUSD")
            mtf_clean = (mtf_alignment or "").strip().upper()

            if is_sol:
                if mtf_clean != "ALIGNED":
                    return AssetEligibilityDecision(
                        symbol=symbol,
                        status=AssetEligibilityStatus.REJECTED_TIER1_CANARY_RESTRICTED,
                        is_eligible=False,
                        rationale=(
                            f"Asset '{symbol}' is restricted to PAPER_ONLY_OBSERVATION: "
                            f"requires mtf_alignment == 'ALIGNED' for Tier-1 Canary execution "
                            f"(currently '{mtf_alignment or 'NONE'}'). Only ALIGNED setups permitted."
                        ),
                        desk=desk,
                        ai_override_attempted=bool(ai_opportunity_score is not None),
                    )
            elif not is_canary_core:
                return AssetEligibilityDecision(
                    symbol=symbol,
                    status=AssetEligibilityStatus.REJECTED_TIER1_CANARY_RESTRICTED,
                    is_eligible=False,
                    rationale=(
                        f"Asset '{symbol}' is restricted to PAPER_ONLY_OBSERVATION. "
                        f"Only BTC, ETH, and ALIGNED SOL are approved for Tier-1 Canary Execution."
                    ),
                    desk=desk,
                    ai_override_attempted=bool(ai_opportunity_score is not None),
                )

        # Main Sovereign Desk Whitelist Check
        if desk == "MAIN_SOVEREIGN":
            is_tier1 = any(
                clean_sym == t.replace("/", "").replace("_", "") for t in TIER1_CORE_WHITELIST
            )
            if not is_tier1:
                return AssetEligibilityDecision(
                    symbol=symbol,
                    status=AssetEligibilityStatus.REJECTED_NOT_WHITELISTED,
                    is_eligible=False,
                    rationale=(
                        f"Asset '{symbol}' is not on the Tier-1 Core Whitelist "
                        f"(BTC, ETH, SOL, PAXG, XAU). Execution on Main Sovereign Desk strictly prohibited."
                    ),
                    desk=desk,
                    ai_override_attempted=bool(ai_opportunity_score is not None),
                )

        # Deterministic Liquidity Metrics Check (if provided)
        if liquidity is not None:
            if liquidity.volume_24h_usd < self.min_24h_volume_usd:
                return AssetEligibilityDecision(
                    symbol=symbol,
                    status=AssetEligibilityStatus.REJECTED_INSUFFICIENT_VOLUME,
                    is_eligible=False,
                    rationale=(
                        f"24h volume (${liquidity.volume_24h_usd:,.2f}) is below minimum "
                        f"institutional hurdle (${self.min_24h_volume_usd:,.2f})."
                    ),
                    desk=desk,
                    ai_override_attempted=bool(ai_opportunity_score is not None),
                )

            if liquidity.order_book_depth_100bps_usd < self.min_depth_100bps_usd:
                return AssetEligibilityDecision(
                    symbol=symbol,
                    status=AssetEligibilityStatus.REJECTED_INSUFFICIENT_DEPTH,
                    is_eligible=False,
                    rationale=(
                        f"L2 order book depth within 100 bps (${liquidity.order_book_depth_100bps_usd:,.2f}) "
                        f"is below minimum depth threshold (${self.min_depth_100bps_usd:,.2f})."
                    ),
                    desk=desk,
                    ai_override_attempted=bool(ai_opportunity_score is not None),
                )

            if liquidity.bid_ask_spread_bps > self.max_spread_bps:
                return AssetEligibilityDecision(
                    symbol=symbol,
                    status=AssetEligibilityStatus.REJECTED_EXCESSIVE_SPREAD,
                    is_eligible=False,
                    rationale=(
                        f"Spread ({liquidity.bid_ask_spread_bps:.1f} bps) exceeds maximum "
                        f"allowed institutional ceiling ({self.max_spread_bps:.1f} bps)."
                    ),
                    desk=desk,
                    ai_override_attempted=bool(ai_opportunity_score is not None),
                )

        return AssetEligibilityDecision(
            symbol=symbol,
            status=AssetEligibilityStatus.ELIGIBLE,
            is_eligible=True,
            rationale="Asset verified on Tier-1 Whitelist with compliant institutional liquidity.",
            desk=desk,
            ai_override_attempted=False,
        )

    def is_tier1_canary_eligible(self, symbol: str, mtf_alignment: str | None = None) -> bool:
        """
        Returns True if symbol is on Tier-1 Canary Whitelist.
        BTC and ETH are unconditionally whitelisted.
        SOL is whitelisted strictly when mtf_alignment == 'ALIGNED'.
        """
        clean_sym = symbol.replace("/", "").replace("_", "").upper()
        if any(clean_sym == t.replace("/", "").replace("_", "") for t in TIER1_CANARY_WHITELIST):
            return True
        if clean_sym in ("SOLUSDT", "SOLUSD"):
            return (mtf_alignment or "").strip().upper() == "ALIGNED"
        return False
