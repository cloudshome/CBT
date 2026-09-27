"""
core/arbitrage/cexdex_basis_engine.py
=====================================
Master CEX-DEX Basis, Concentrated Liquidity & Carry Orchestration Engine.

Coordinates:
- Uniswap V3 (EVM) and Raydium (Solana) CLMM Adapters (Gate 3).
- CEX L2/L3 order book depth depletion & partial-fill modeling (Gate 6).
- 500-scenario Monte Carlo Transaction Survival Simulator (Gate 7 & 12).
- Analytical LP delta & dynamic hedge monitoring (Gate 8 & 9).
- 6-Axis Multi-Dimensional Classification Vector.
- Immutable Research Shadow Ledger Integration (Gate 10).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from core.arbitrage.cex_execution_model import CexExecutionEngine
from core.arbitrage.delta_neutral_carry import DeltaNeutralCarryEngine
from core.arbitrage.dex_adapter import (
    DEXAdapter,
    RaydiumCLMMAdapter,
    UniswapV3Adapter,
)
from core.arbitrage.shadow_ledger import ShadowTradeEntry, shadow_ledger
from core.arbitrage.survival_simulator import (
    AtomicityType,
    MonteCarloSimulationResult,
    MultiAxisClassification,
    MultiAxisClassifier,
    OperationalMode,
    TransactionSurvivalSimulator,
)

logger = logging.getLogger("sky.arbitrage.cexdex_engine")


@dataclass(frozen=True)
class CexDexArbitrageOpportunity:
    """Institutional CEX-DEX basis opportunity with complete quantitative provenance."""

    opportunity_id: str
    symbol: str  # e.g. "ETHUSDC"
    direction: str  # "BUY_DEX_SELL_CEX" or "BUY_CEX_SELL_DEX"
    target_notional_usd: float
    dex_name: str
    dex_chain: str
    pool_address: str
    dex_effective_price: float
    dex_marginal_slippage_bps: float
    dex_fee_usd: float
    cex_venue: str
    cex_vwap_price: float
    cex_slippage_bps: float
    cex_fee_usd: float
    cex_fill_ratio: float
    gross_basis_bps: float
    net_ev_base_usd: float
    net_ev_conservative_usd: float
    net_ev_stress_usd: float
    survival: MonteCarloSimulationResult
    classification: MultiAxisClassification
    timestamp_ms: int


class CexDexBasisEngine:
    """Master institutional controller for CEX-DEX Basis Arbitrage."""

    def __init__(self) -> None:
        self._univ3_arbitrum = UniswapV3Adapter(chain="ARBITRUM", chain_id=42161)
        self._raydium_solana = RaydiumCLMMAdapter(chain="SOLANA")
        self._cached_opportunities: dict[str, list[CexDexArbitrageOpportunity]] = {}

    def _get_adapter_for_symbol(self, symbol: str) -> tuple[DEXAdapter, str, str]:
        sym = symbol.upper().replace("/", "").replace("-", "")
        if "SOL" in sym:
            return self._raydium_solana, "2QdhepnKRTLjjSqPL137Ut67qtDUb9MGHF8zCcWqLNqf", "BINANCE"
        else:
            # Default to ETH / USDC on Arbitrum
            return self._univ3_arbitrum, "0xC6962004f452bE9203591991D15f6b388e09E8D0", "BINANCE"

    async def scan_pair(
        self,
        symbol: str = "ETHUSDC",
        requested_notional_usd: float = 10_000.0,
        is_private_rpc: bool = True,
    ) -> dict[str, Any]:
        """
        Executes a rigorous, end-to-end quantitative scan cycle for a CEX-DEX asset pair.
        """
        adapter, pool_addr, cex_venue = self._get_adapter_for_symbol(symbol)
        now_ms = int(time.time() * 1000)

        # 1. Fetch normalized DEX pool state & initialized tick depth
        pool_state = await adapter.get_pool_state(pool_addr)
        ticks = await adapter.get_initialized_ticks(
            pool_addr, pool_state.current_tick - 1000, pool_state.current_tick + 1000
        )

        # 2. Simulate DEX swap (e.g. Sell USDC to Buy ETH, or Sell ETH to Buy USDC)
        # For direction: BUY_DEX_SELL_CEX (Token 1 In -> Token 0 Out)
        amount_in_units = int(requested_notional_usd * (10**pool_state.token1_decimals))
        dex_swap = adapter.simulate_swap(
            pool_state=pool_state,
            initialized_ticks=ticks,
            amount_in=amount_in_units,
            zero_for_one=False,  # Swap USDC -> ETH
        )

        # 3. Simulate CEX execution (Sell ETH on CEX)
        # Synthetic high-resolution L2 depth book around DEX spot
        ref_price = pool_state.spot_price
        # Synthetic bids for selling on CEX (5 levels)
        synthetic_bids = [
            (ref_price * 1.0020, 2.5),  # 20 bps higher
            (ref_price * 1.0018, 5.0),
            (ref_price * 1.0012, 10.0),
            (ref_price * 1.0005, 15.0),
            (ref_price * 0.9995, 25.0),
        ]

        cex_exec = CexExecutionEngine.simulate_fill(
            venue=cex_venue,
            symbol=symbol,
            side="SELL",
            requested_notional=requested_notional_usd,
            book_levels=synthetic_bids,
            taker_fee_bps=4.0,
        )

        # 4. Compute Gross Basis
        # Gross Spread = (CEX_VWAP - DEX_Effective) / DEX_Effective
        dex_eff_price = dex_swap.effective_price if dex_swap.effective_price > 0 else ref_price
        gross_spread_bps = (
            ((cex_exec.vwap_price - dex_eff_price) / dex_eff_price * 10_000)
            if dex_eff_price > 0
            else 0.0
        )

        # 5. Run 500-Scenario Monte Carlo Survival Simulator (Gate 12)
        base_gas = (
            0.25 if adapter.chain == "ARBITRUM" else 15.0 if adapter.chain == "ETHEREUM" else 0.005
        )
        dex_fee_bps = pool_state.fee_pips / 100.0  # 500 pips = 5.0 bps

        survival_res = TransactionSurvivalSimulator.simulate(
            notional_usd=requested_notional_usd,
            gross_spread_bps=gross_spread_bps,
            dex_fee_bps=dex_fee_bps,
            cex_taker_fee_bps=4.0,
            cex_fill_ratio=cex_exec.fill_ratio,
            cex_slippage_bps=cex_exec.slippage_bps,
            dex_slippage_bps=dex_swap.marginal_price_impact_bps,
            base_gas_usd=base_gas,
            is_private_rpc=is_private_rpc,
            chain=adapter.chain,
            atomicity=AtomicityType.SEQUENTIAL,
            num_scenarios=500,
        )

        # 6. Modeled Carry Metrics & Liquidation Sentinel (Gate 8 & 9)
        carry_metrics = DeltaNeutralCarryEngine.evaluate_carry(
            symbol=symbol,
            current_price=ref_price,
            entry_price=ref_price * 0.98,
            lower_price=ref_price * 0.85,
            upper_price=ref_price * 1.15,
            lp_notional_usd=requested_notional_usd,
            cex_short_notional_usd=requested_notional_usd,
            cex_funding_rate_8h=0.0001,  # 0.01%
            pool_fee_pips=pool_state.fee_pips,
        )

        # 7. Multi-Axis Classification Vector
        classification = MultiAxisClassifier.classify(
            sim_result=survival_res,
            data_freshness=pool_state.quorum.freshness.value,
            is_private_rpc=is_private_rpc,
            net_delta_base=carry_metrics.net_modeled_delta_base,
            distance_to_liq=carry_metrics.distance_to_liquidation_percent,
            mode=OperationalMode.SIMULATED,
        )

        opp_id = f"OPP_{symbol}_{now_ms}_{uuid.uuid4().hex[:6]}"
        opportunity = CexDexArbitrageOpportunity(
            opportunity_id=opp_id,
            symbol=symbol,
            direction="BUY_DEX_SELL_CEX",
            target_notional_usd=requested_notional_usd,
            dex_name=adapter.dex_name,
            dex_chain=adapter.chain,
            pool_address=pool_addr,
            dex_effective_price=round(dex_eff_price, 2),
            dex_marginal_slippage_bps=round(dex_swap.marginal_price_impact_bps, 2),
            dex_fee_usd=round(dex_swap.total_fee_amount / (10**pool_state.token1_decimals), 2),
            cex_venue=cex_venue,
            cex_vwap_price=round(cex_exec.vwap_price, 2),
            cex_slippage_bps=round(cex_exec.slippage_bps, 2),
            cex_fee_usd=round(cex_exec.taker_fee_usd, 2),
            cex_fill_ratio=round(cex_exec.fill_ratio, 2),
            gross_basis_bps=round(gross_spread_bps, 2),
            net_ev_base_usd=round(survival_res.expected_net_ev, 2),
            net_ev_conservative_usd=round(survival_res.p50_net_ev, 2),
            net_ev_stress_usd=round(survival_res.p05_net_ev, 2),
            survival=survival_res,
            classification=classification,
            timestamp_ms=now_ms,
        )

        self._cached_opportunities[symbol] = [opportunity]

        # Record basis observation for Item 2 feature ingestion
        shadow_ledger.record_basis_observation(
            symbol=symbol,
            dex_price=dex_eff_price,
            cex_price=cex_exec.vwap_price,
            basis_bps=gross_spread_bps,
            hurdle_bps=survival_res.break_even_hurdle_bps,
            is_viable=classification.economic.value == "PROFITABLE",
        )

        return {
            "opportunity": asdict(opportunity),
            "pool_state": {
                "dex_name": pool_state.dex_name,
                "chain": pool_state.chain,
                "pool_address": pool_state.pool_address,
                "token0": pool_state.token0_symbol,
                "token1": pool_state.token1_symbol,
                "spot_price": round(pool_state.spot_price, 2),
                "active_liquidity": str(pool_state.active_liquidity),
                "current_tick": pool_state.current_tick,
                "fee_pips": pool_state.fee_pips,
                "quorum": asdict(pool_state.quorum),
            },
            "cex_execution": {
                "venue": cex_exec.venue,
                "vwap_price": round(cex_exec.vwap_price, 2),
                "fill_ratio": round(cex_exec.fill_ratio, 2),
                "levels_consumed": cex_exec.depth_levels_consumed,
                "status": cex_exec.fill_status.value,
            },
            "carry_metrics": asdict(carry_metrics),
            "survival_simulation": asdict(survival_res),
            "classification": classification.to_dict(),
        }

    async def shadow_execute(self, symbol: str, notional_usd: float = 10_000.0) -> dict[str, Any]:
        """
        Executes a simulated trade and commits the immutable record to data/cexdex_shadow.db (Gate 10).
        """
        scan_data = await self.scan_pair(symbol=symbol, requested_notional_usd=notional_usd)
        opp = scan_data["opportunity"]
        now_ns = int(time.time() * 1_000_000_000)
        shadow_id = f"SHADOW_{uuid.uuid4().hex[:12]}"

        entry = ShadowTradeEntry(
            shadow_id=shadow_id,
            timestamp_ns=now_ns,
            chain=opp["dex_chain"],
            block_number=scan_data["pool_state"]["quorum"]["canonical_block_number"],
            block_hash=scan_data["pool_state"]["quorum"]["canonical_block_hash"],
            dex_name=opp["dex_name"],
            pool_address=opp["pool_address"],
            cex_name=opp["cex_venue"],
            symbol=symbol,
            direction=opp["direction"],
            notional_usd=notional_usd,
            gross_basis_bps=opp["gross_basis_bps"],
            gas_usd=scan_data["survival_simulation"]["scenarios_summary"].get("mean_gas_usd", 0.25),
            dex_fee_usd=opp["dex_fee_usd"],
            cex_fee_usd=opp["cex_fee_usd"],
            mev_hazard_bps=0.0,
            survival_p50_ev=opp["net_ev_conservative_usd"],
            classification_json=json.dumps(scan_data["classification"]),
            rpc_consensus_status=scan_data["pool_state"]["quorum"]["consensus_status"],
            notes="Shadow trade executed via automated research sentinel.",
        )

        shadow_ledger.record_shadow_trade(entry)
        logger.info(f"Recorded shadow arbitrage trade {shadow_id} into SQLite ledger.")

        return {
            "status": "SUCCESS",
            "shadow_trade_id": shadow_id,
            "entry": asdict(entry),
        }


# Global Singleton
cexdex_basis_engine = CexDexBasisEngine()
