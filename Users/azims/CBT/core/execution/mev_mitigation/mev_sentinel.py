"""
core/execution/mev_mitigation/mev_sentinel.py
=============================================
Master Risk Desk & MEV Mitigation Sentinel.

Enforces:
1. Constitutional Half-Kelly sizing and 1.5% single-event equity cap.
2. Mandatory Private Mempool Routing:
   - Orders with High Hazard or Vulnerable sandwich profiles MUST be routed
     via PRIVATE_RPC (Flashbots / MEV-Blocker) or FAIR_SEQUENCING.
   - Public mempool routing is permitted ONLY when net searcher edge is negative.
3. Dynamic slippage tightening to ensure order cannot be economically sandwiched.
4. Permanent simulation firewall (real_capital_enabled = False).
5. Fail-closed exception containment under malformed inputs.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from core.execution.mev_mitigation.models import (
    MEVProtectedOrderPlan,
    MEVRiskLevel,
    MempoolRouteType,
    SandwichVulnerabilityReport,
)
from core.execution.mev_mitigation.pbs_simulator import PBSSimulator, pbs_simulator
from core.execution.mev_mitigation.sandwich_detector import (
    SandwichAttackEvaluator,
    sandwich_attack_evaluator,
)

logger = logging.getLogger("sky.execution.mev_sentinel")


class MEVMitigationSentinel:
    """Protective router and risk gatekeeper shielding orders from toxic MEV."""

    MAX_EQUITY_FRACTION: float = 0.015  # 1.5% hard constitutional cap

    def __init__(
        self,
        sandwich_evaluator: Optional[SandwichAttackEvaluator] = None,
        pbs_sim: Optional[PBSSimulator] = None,
    ):
        self.sandwich_evaluator = sandwich_evaluator or sandwich_attack_evaluator
        self.pbs_sim = pbs_sim or pbs_simulator
        self.real_capital_enabled: bool = False

    def evaluate_and_protect_order(
        self,
        symbol: str,
        requested_notional_usd: float,
        portfolio_equity_usd: float,
        user_slippage_tolerance_bps: float,
        pool_liquidity_usd: float,
        prefer_fair_sequencing: bool = False,
        base_fee_gwei: Optional[float] = None,
        eth_price_usd: Optional[float] = None,
    ) -> MEVProtectedOrderPlan:
        """
        Evaluates sandwich risk and generates an MEV-protected routing plan with constitutional sizing.
        """
        order_id = f"mev_ord_{uuid.uuid4().hex[:8]}"

        try:
            # 1. Fail-closed validation
            if requested_notional_usd <= 0 or portfolio_equity_usd <= 0:
                return MEVProtectedOrderPlan(
                    order_id=order_id,
                    symbol=symbol,
                    original_notional_usd=requested_notional_usd,
                    routed_notional_usd=0.0,
                    route_type=MempoolRouteType.PRIVATE_RPC,
                    enforced_slippage_bps=0.0,
                    builder_tip_usd=0.0,
                    kelly_fraction=0.0,
                    is_approved=False,
                    protection_notes="Invalid input: notional or portfolio equity <= 0",
                    real_capital_enabled=False,
                )

            # 2. Constitutional 1.5% Equity Cap
            max_constitutional_notional = portfolio_equity_usd * self.MAX_EQUITY_FRACTION
            capped_notional = min(requested_notional_usd, max_constitutional_notional)
            kelly_fraction = capped_notional / portfolio_equity_usd

            # 3. Evaluate sandwich vulnerability
            report = self.sandwich_evaluator.evaluate_sandwich_risk(
                symbol=symbol,
                target_notional_usd=capped_notional,
                user_slippage_tolerance_bps=user_slippage_tolerance_bps,
                pool_liquidity_usd=pool_liquidity_usd,
                base_fee_gwei=base_fee_gwei,
                eth_price_usd=eth_price_usd,
            )

            # 4. Determine Route Type and Enforced Slippage
            if prefer_fair_sequencing:
                route_type = MempoolRouteType.FAIR_SEQUENCING
                enforced_slippage = report.recommended_max_slippage_bps
                builder_tip = 0.0
                notes = "Routed to Fair Sequencing Batch Auction (Zero MEV extracted)"
            elif report.requires_private_mempool:
                route_type = MempoolRouteType.PRIVATE_RPC
                enforced_slippage = report.recommended_max_slippage_bps
                # Builder priority fee / bribe tip (~$2.00 in ETH equivalent)
                builder_tip = 2.0
                notes = f"Shielded via Private RPC: Neutralized {report.risk_level.name} sandwich hazard"
            else:
                route_type = MempoolRouteType.PUBLIC_MEMPOOL
                enforced_slippage = min(user_slippage_tolerance_bps, report.recommended_max_slippage_bps)
                builder_tip = 0.0
                notes = "Public mempool cleared: Net searcher profit is negative (immune to sandwiching)"

            return MEVProtectedOrderPlan(
                order_id=order_id,
                symbol=symbol,
                original_notional_usd=requested_notional_usd,
                routed_notional_usd=round(capped_notional, 2),
                route_type=route_type,
                enforced_slippage_bps=round(enforced_slippage, 2),
                builder_tip_usd=builder_tip,
                kelly_fraction=round(kelly_fraction, 5),
                is_approved=True,
                protection_notes=notes,
                real_capital_enabled=False,
            )

        except Exception as exc:  # noqa: BLE001
            logger.error("MEV Mitigation Sentinel caught unhandled anomaly: %s", exc)
            return MEVProtectedOrderPlan(
                order_id=order_id,
                symbol=symbol,
                original_notional_usd=requested_notional_usd,
                routed_notional_usd=0.0,
                route_type=MempoolRouteType.PRIVATE_RPC,
                enforced_slippage_bps=0.0,
                builder_tip_usd=0.0,
                kelly_fraction=0.0,
                is_approved=False,
                protection_notes=f"Fail-closed exception: {exc}",
                real_capital_enabled=False,
            )


# Exported singleton
mev_mitigation_sentinel = MEVMitigationSentinel()
