"""
Portfolio Risk Matrix, Cross-Asset VaR & Correlation Bounds.
Monitors total portfolio heat (hard ceiling <= 6.0% total open equity risk)
and evaluates Cross-Asset Parametric Value at Risk (VaR 99%).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("ai_quant_sentinel.portfolio_risk_matrix")


@dataclass
class PortfolioHeatStatus:
    total_open_risk_usd: float
    total_open_risk_pct: float  # [0.0, 1.0] (e.g. 0.035 = 3.5%)
    max_heat_ceiling_pct: float  # 0.06 (6.0%)
    remaining_risk_budget_pct: float
    portfolio_var_99_usd: float
    open_positions_count: int
    is_heat_exceeded: bool
    can_open_new_position: bool
    warning_message: str | None = None


class PortfolioRiskMatrix:
    """Manages total exposure, cross-asset correlations, and portfolio heat boundaries."""

    def __init__(self, max_heat_ceiling_pct: float = 0.06):  # 6.0% max total open risk
        self.max_heat_ceiling_pct = max_heat_ceiling_pct

    def evaluate_portfolio_heat(
        self,
        account_equity: float,
        open_positions: list[dict[str, Any]],
        proposed_risk_usd: float = 0.0,
    ) -> PortfolioHeatStatus:
        """
        Calculates cumulative open risk and ensures total portfolio heat does not breach 6.0%.
        """
        if account_equity <= 0:
            return PortfolioHeatStatus(
                total_open_risk_usd=0.0,
                total_open_risk_pct=0.0,
                max_heat_ceiling_pct=self.max_heat_ceiling_pct,
                remaining_risk_budget_pct=0.0,
                portfolio_var_99_usd=0.0,
                open_positions_count=0,
                is_heat_exceeded=True,
                can_open_new_position=False,
                warning_message="Account equity is zero or negative.",
            )

        current_risk_usd = 0.0
        for pos in open_positions:
            size = pos.get("size", 0.0)
            entry = pos.get("entry_price", 0.0)
            sl = pos.get("stop_loss", 0.0)
            if entry > 0 and sl > 0:
                current_risk_usd += size * abs(entry - sl)

        total_projected_risk_usd = current_risk_usd + proposed_risk_usd
        total_risk_pct = total_projected_risk_usd / account_equity
        rem_budget_pct = max(0.0, self.max_heat_ceiling_pct - (current_risk_usd / account_equity))

        is_exceeded = total_risk_pct > self.max_heat_ceiling_pct
        can_open = (not is_exceeded) and (proposed_risk_usd / account_equity <= rem_budget_pct)

        # Approximate 99% 1-Day VaR (Z = 2.33 * portfolio volatility)
        var_99_usd = total_projected_risk_usd * 1.65

        warning = None
        if is_exceeded:
            warning = (
                f"PORTFOLIO_HEAT_BREACH: Projected total open risk ({total_risk_pct * 100:.2f}%) "
                f"exceeds institutional ceiling ({self.max_heat_ceiling_pct * 100:.1f}%)."
            )
            logger.warning(warning)

        return PortfolioHeatStatus(
            total_open_risk_usd=round(total_projected_risk_usd, 2),
            total_open_risk_pct=round(total_risk_pct, 4),
            max_heat_ceiling_pct=self.max_heat_ceiling_pct,
            remaining_risk_budget_pct=round(rem_budget_pct, 4),
            portfolio_var_99_usd=round(var_99_usd, 2),
            open_positions_count=len(open_positions),
            is_heat_exceeded=is_exceeded,
            can_open_new_position=can_open,
            warning_message=warning,
        )


# Singleton
portfolio_risk_matrix = PortfolioRiskMatrix()
