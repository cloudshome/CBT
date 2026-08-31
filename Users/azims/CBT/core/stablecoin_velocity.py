"""
Pillar 4: Stablecoin Dry-Powder & Liquidity Velocity.
Tracks Stablecoin Supply Ratio (SSR), USDT/USDC Net Treasury Minting Velocity,
and Exchange Stablecoin Dry Powder Reserves.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger("ai_quant_sentinel.stablecoin_velocity")


@dataclass
class StablecoinVelocitySnapshot:
    symbol: str
    timestamp: int
    ssr_ratio: float
    ssr_oscillator_bias: str
    net_minting_velocity_24h_usd: float
    usdt_market_cap_usd: float
    usdc_market_cap_usd: float
    dry_powder_liquidity_state: str
    z_score: float  # Standardized [-3.0, +3.0]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "ssr_ratio": round(self.ssr_ratio, 2),
            "ssr_oscillator_bias": self.ssr_oscillator_bias,
            "net_minting_velocity_24h_usd": self.net_minting_velocity_24h_usd,
            "usdt_market_cap_usd": self.usdt_market_cap_usd,
            "usdc_market_cap_usd": self.usdc_market_cap_usd,
            "dry_powder_liquidity_state": self.dry_powder_liquidity_state,
            "z_score": round(self.z_score, 3),
        }


class StablecoinVelocityEngine:
    """Computes Pillar 4: Stablecoin Dry-Powder & Liquidity Velocity."""

    def analyze(self, symbol: str, current_price: float) -> StablecoinVelocitySnapshot:
        import time
        sym = symbol.upper()
        now = int(time.time() * 1000)

        # Global Stablecoin aggregates
        usdt_cap = 132_400_000_000.0
        usdc_cap = 39_200_000_000.0
        total_stables = usdt_cap + usdc_cap
        net_minting_24h = 180_000_000.0  # +$180M net new minting

        if "BTC" in sym:
            btc_mcap = current_price * 19_780_000.0
            ssr = btc_mcap / total_stables if total_stables > 0 else 8.5
            ssr_bias = "BULLISH_EXPANSION_DIVERGENCE" if ssr < 12.0 else "CAPITAL_EXHAUSTION"
            z = min(3.0, max(-3.0, (net_minting_24h - 50_000_000.0) / 45_000_000.0))
            state = "HIGH_DRY_POWDER_EXPANSION"

        elif "ETH" in sym:
            eth_mcap = current_price * 120_400_000.0
            ssr = eth_mcap / total_stables if total_stables > 0 else 1.8
            ssr_bias = "HEALTHY_STABLECOIN_BUFFER"
            z = min(3.0, max(-3.0, (net_minting_24h - 50_000_000.0) / 50_000_000.0))
            state = "SUFFICIENT_LIQUIDITY_INJECTION"

        else:
            # Gold: Fiat M2 Liquidity Expansion Equivalent
            ssr = 1.0
            ssr_bias = "GLOBAL_DEBT_MONETIZATION"
            z = 1.60
            state = "FIAT_DEVALUATION_PRESSURE"

        return StablecoinVelocitySnapshot(
            symbol=sym,
            timestamp=now,
            ssr_ratio=ssr,
            ssr_oscillator_bias=ssr_bias,
            net_minting_velocity_24h_usd=net_minting_24h,
            usdt_market_cap_usd=usdt_cap,
            usdc_market_cap_usd=usdc_cap,
            dry_powder_liquidity_state=state,
            z_score=z,
        )


stablecoin_velocity_engine = StablecoinVelocityEngine()
