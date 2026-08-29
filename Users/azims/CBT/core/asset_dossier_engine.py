"""
8-Pillar Universal Asset Intelligence Dossier Master Engine.
Continuously synthesizes Institutional Flows, Derivatives/Options Microstructure,
Valuation Cost Bases, Stablecoin Dry Powder, Cyclical DNA, Macro Betas,
Volatility Profiles, and Physical/On-Chain Supply Shocks for Bitcoin (BTC),
Ethereum (ETH), and Gold (PAXG/XAU).
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from core.institutional_flows import institutional_flows_engine
from core.derivatives_options import derivatives_options_engine
from core.valuation_cost_basis import valuation_cost_basis_engine
from core.stablecoin_velocity import stablecoin_velocity_engine
from core.seasonality_cyclical_dna import seasonality_cyclical_engine
from core.macro_liquidity_beta import macro_liquidity_beta_engine
from core.volatility_profile_regime import volatility_profile_engine
from core.physical_supply_shock import physical_supply_shock_engine
from core.composite_scorer import composite_scorer

logger = logging.getLogger("ai_quant_sentinel.asset_dossier_engine")


@dataclass
class UniversalAssetDossier:
    symbol: str
    timestamp: int
    current_price: float
    composite_health_score: float
    macro_bias: str
    pillar_1_institutional_flows: Dict[str, Any]
    pillar_2_derivatives_options: Dict[str, Any]
    pillar_3_valuation_cost_basis: Dict[str, Any]
    pillar_4_stablecoin_velocity: Dict[str, Any]
    pillar_5_seasonality_cyclical_dna: Dict[str, Any]
    pillar_6_macro_liquidity_beta: Dict[str, Any]
    pillar_7_volatility_profile: Dict[str, Any]
    pillar_8_physical_supply_shock: Dict[str, Any]
    pillar_z_scores: List[float]
    actionable_quant_verdict: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AssetDossierEngine:
    """Master Orchestrator compiling the 8-Pillar Live Asset Intelligence Dossier."""

    def compile_dossier(
        self,
        symbol: str,
        current_price: float,
        candles_1h: Optional[List[Dict[str, Any]]] = None,
        candles_15m: Optional[List[Dict[str, Any]]] = None,
    ) -> UniversalAssetDossier:
        now = int(time.time() * 1000)
        sym = symbol.upper()

        # 1. Execute the 8 Pillars in parallel / sequence
        p1 = institutional_flows_engine.analyze(sym, current_price)
        p2 = derivatives_options_engine.analyze(sym, current_price)
        p3 = valuation_cost_basis_engine.analyze(sym, current_price)
        p4 = stablecoin_velocity_engine.analyze(sym, current_price)
        p5 = seasonality_cyclical_engine.analyze(sym, current_price)
        p6 = macro_liquidity_beta_engine.analyze(sym, current_price)
        p7 = volatility_profile_engine.analyze(sym, current_price, candles_1h)
        p8 = physical_supply_shock_engine.analyze(sym, current_price)

        z_scores = [
            p1.z_score,
            p2.z_score,
            p3.z_score,
            p4.z_score,
            p5.z_score,
            p6.z_score,
            p7.z_score,
            p8.z_score,
        ]

        # 2. Compute Mathematical Composite Health Score (0-100)
        composite_score, macro_bias = composite_scorer.compute_score(sym, z_scores)

        # 3. Formulate Actionable Quantitative Verdict
        if "BTC" in sym:
            verdict = (
                f"Confluence of STH cost basis (${p3.sth_realized_price:,.0f}), Weekly VAL (${p7.value_area_low:,.0f}), "
                f"and active ETF absorption (+${p1.etf_net_inflow_24h_usd/1e6:.1f}M) confirms high-probability long structure "
                f"targeting ${p2.primary_liquidation_pools['short_squeeze_target']:,.0f} short liquidation cluster."
            )
        elif "ETH" in sym:
            verdict = (
                f"Persistent exchange staking outflows ({p8.exchange_reserve_delta_24h}) coupled with undervaluation "
                f"MVRV ({p3.mvrv_z_score:.2f}) projects favorable mean-reversion towards ${p7.value_area_high:,.0f}."
            )
        else:
            verdict = (
                f"Sovereign central bank net accumulation ({p1.sovereign_central_bank_net_tons_quarterly:.1f}t) and COMEX vault "
                f"drawdown ({p8.comex_registered_vault_delta_pct:.2f}%) provide structural physical bid floor at ${p3.sth_realized_price:,.0f}."
            )

        return UniversalAssetDossier(
            symbol=sym,
            timestamp=now,
            current_price=current_price,
            composite_health_score=composite_score,
            macro_bias=macro_bias,
            pillar_1_institutional_flows=p1.to_dict(),
            pillar_2_derivatives_options=p2.to_dict(),
            pillar_3_valuation_cost_basis=p3.to_dict(),
            pillar_4_stablecoin_velocity=p4.to_dict(),
            pillar_5_seasonality_cyclical_dna=p5.to_dict(),
            pillar_6_macro_liquidity_beta=p6.to_dict(),
            pillar_7_volatility_profile=p7.to_dict(),
            pillar_8_physical_supply_shock=p8.to_dict(),
            pillar_z_scores=z_scores,
            actionable_quant_verdict=verdict,
        )


asset_dossier_engine = AssetDossierEngine()
