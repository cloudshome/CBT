"""
SKY Live Simulation Burn-In & Autonomous Risk Auditor Engine.

Monitors continuous paper execution telemetry, triggers automated event-driven
loss autopsies on stop-outs, and executes regime-conditional expectancy
drift audits with automatic strategy quarantine circuit breakers.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from core.loss_autopsy import loss_autopsy_engine, LossAutopsyReport
from core.audit_bus import audit_bus

logger = logging.getLogger("sky.autonomous_auditor")


@dataclass
class TradeTelemetryRecord:
    trade_id: str
    symbol: str
    side: str                          # "BUY" or "SELL"
    entry_price: float
    exit_price: float
    qty: float
    realized_pnl_usd: float
    r_multiple: float
    entry_time_ms: int
    exit_time_ms: int
    duration_sec: int
    market_regime_at_entry: str        # "TRENDING_BULL", "TRENDING_BEAR", "RANGING_COMPRESSION", "HIGH_VOLATILITY_EXPANSION"
    entry_slippage_bps: float
    exit_slippage_bps: float
    loss_autopsy_triggered: bool = False
    autopsy_category: Optional[str] = None


@dataclass
class RegimeExpectancyMetrics:
    regime: str
    trade_count: int
    win_rate_pct: float
    profit_factor: float
    average_r_multiple: float
    net_pnl_usd: float
    baseline_expectancy: float
    current_expectancy: float
    drift_sigma: float
    is_edge_intact: bool


@dataclass
class SystemAuditHealthReport:
    timestamp_ms: int
    total_trades_logged: int
    active_burn_in_hours: float
    cumulative_pnl_usd: float
    peak_drawdown_pct: float
    overall_win_rate_pct: float
    overall_profit_factor: float
    regime_expectancy_breakdown: Dict[str, RegimeExpectancyMetrics]
    cusum_drift_score: float
    quarantine_circuit_tripped: bool
    governance_status: str             # "HEALTHY_OPTIMAL", "REGIME_DEGRADATION_WARNING", "CIRCUIT_BREAKER_QUARANTINED"
    recent_autopsies: List[Dict[str, Any]]
    narrative: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AutonomousRiskAuditor:
    """
    24/7 telemetry monitor, automated loss autopsy dispatcher,
    and regime-conditional expectancy drift auditor.
    """

    def __init__(
        self,
        drift_sigma_threshold: float = 2.5,
        min_trades_for_audit: int = 5,
        burn_in_start_time_ms: Optional[int] = None,
    ):
        self.drift_sigma_threshold = drift_sigma_threshold
        self.min_trades_for_audit = min_trades_for_audit
        self.burn_in_start_time_ms = burn_in_start_time_ms or int(time.time() * 1000)
        self._trade_ledger: List[TradeTelemetryRecord] = []
        self._recent_autopsies: List[Dict[str, Any]] = []

    def record_trade(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        qty: float,
        entry_time_ms: int,
        exit_time_ms: int,
        market_regime: str = "TRENDING_BULL",
        risk_per_trade_usd: float = 100.0,
        entry_slippage_bps: float = 1.0,
        exit_slippage_bps: float = 1.0,
    ) -> TradeTelemetryRecord:
        """
        Logs completed paper trade, computes PnL and R-multiple, and dispatches automated autopsy if loss.
        """
        # Calculate Realized PnL
        if side.upper() in ["BUY", "LONG"]:
            pnl_usd = (exit_price - entry_price) * qty
        else:
            pnl_usd = (entry_price - exit_price) * qty

        # Subtract slippage
        notional = entry_price * qty
        slip_cost = notional * ((entry_slippage_bps + exit_slippage_bps) / 10000.0)
        pnl_usd -= slip_cost

        r_mult = pnl_usd / max(1.0, risk_per_trade_usd)
        duration_sec = max(1, int((exit_time_ms - entry_time_ms) / 1000))

        rec = TradeTelemetryRecord(
            trade_id=trade_id,
            symbol=symbol,
            side=side,
            entry_price=round(entry_price, 4),
            exit_price=round(exit_price, 4),
            qty=round(qty, 4),
            realized_pnl_usd=round(pnl_usd, 2),
            r_multiple=round(r_mult, 3),
            entry_time_ms=entry_time_ms,
            exit_time_ms=exit_time_ms,
            duration_sec=duration_sec,
            market_regime_at_entry=market_regime,
            entry_slippage_bps=round(entry_slippage_bps, 2),
            exit_slippage_bps=round(exit_slippage_bps, 2),
        )

        # Automated Forensic Loss Autopsy Dispatch
        if pnl_usd < 0:
            autopsy_report = self._dispatch_loss_autopsy(rec)
            rec.loss_autopsy_triggered = True
            rec.autopsy_category = autopsy_report.loss_category.value
            self._recent_autopsies.append(autopsy_report.to_dict())
            if len(self._recent_autopsies) > 50:
                self._recent_autopsies.pop(0)

        self._trade_ledger.append(rec)
        return rec

    def audit_system_health(self, timestamp_ms: Optional[int] = None) -> SystemAuditHealthReport:
        """
        Runs comprehensive regime-conditional expectancy drift audit and evaluates circuit breakers.
        """
        now = timestamp_ms or int(time.time() * 1000)
        burn_in_hours = max(0.01, (now - self.burn_in_start_time_ms) / (1000.0 * 3600.0))

        if not self._trade_ledger:
            return self._empty_audit_report(now, burn_in_hours)

        total_trades = len(self._trade_ledger)
        pnls = [t.realized_pnl_usd for t in self._trade_ledger]
        cum_pnl = float(sum(pnls))

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0

        gross_profit = sum(wins) if wins else 1e-4
        gross_loss = abs(sum(losses)) if losses else 1e-4
        profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else 1.0

        # Max Drawdown
        equity = 10000.0 + np.cumsum([0.0] + pnls)
        peak = np.maximum.accumulate(equity)
        dd = (equity - peak) / peak
        max_dd_pct = float(abs(np.min(dd))) * 100.0 if len(dd) > 0 else 0.0

        # Regime-Conditional Breakdown & CUSUM Expectancy Drift
        regime_breakdown = self._compute_regime_expectancy()
        cusum_score, circuit_tripped = self._evaluate_cusum_drift(regime_breakdown)

        if circuit_tripped:
            status = "CIRCUIT_BREAKER_QUARANTINED"
            narrative = f"CRITICAL: Expectancy drift exceeded threshold (CUSUM score: {cusum_score:.2f} sigma). System quarantined."
            audit_bus.emit_event(
                event_type="STRATEGY_QUARANTINE_TRIPPED",
                symbol="PORTFOLIO",
                reason=f"CUSUM expectancy drift {cusum_score:.2f} exceeded threshold",
                severity="CRITICAL",
                details={"cusum_score": cusum_score, "cumulative_pnl": cum_pnl},
            )
        elif any(not r.is_edge_intact for r in regime_breakdown.values()):
            status = "REGIME_DEGRADATION_WARNING"
            narrative = f"WARNING: Edge degradation detected in 1 or more regimes. Profit Factor: {profit_factor:.2f}."
        else:
            status = "HEALTHY_OPTIMAL"
            narrative = f"All regime expectancies intact. Win Rate: {win_rate:.1f}%, Profit Factor: {profit_factor:.2f}, Drawdown: {max_dd_pct:.2f}%."

        return SystemAuditHealthReport(
            timestamp_ms=now,
            total_trades_logged=total_trades,
            active_burn_in_hours=round(burn_in_hours, 2),
            cumulative_pnl_usd=round(cum_pnl, 2),
            peak_drawdown_pct=round(max_dd_pct, 2),
            overall_win_rate_pct=round(win_rate, 1),
            overall_profit_factor=round(profit_factor, 2),
            regime_expectancy_breakdown=regime_breakdown,
            cusum_drift_score=round(cusum_score, 2),
            quarantine_circuit_tripped=circuit_tripped,
            governance_status=status,
            recent_autopsies=self._recent_autopsies[-10:],
            narrative=narrative,
        )

    def _compute_regime_expectancy(self) -> Dict[str, RegimeExpectancyMetrics]:
        all_regimes = ["TRENDING_BULL", "TRENDING_BEAR", "RANGING_COMPRESSION", "HIGH_VOLATILITY_EXPANSION"]
        regime_trades: Dict[str, List[TradeTelemetryRecord]] = {r: [] for r in all_regimes}

        for t in self._trade_ledger:
            reg = t.market_regime_at_entry if t.market_regime_at_entry in regime_trades else "TRENDING_BULL"
            regime_trades[reg].append(t)

        metrics: Dict[str, RegimeExpectancyMetrics] = {}
        for reg, trades in regime_trades.items():
            if not trades:
                metrics[reg] = RegimeExpectancyMetrics(
                    regime=reg,
                    trade_count=0,
                    win_rate_pct=0.0,
                    profit_factor=1.0,
                    average_r_multiple=0.0,
                    net_pnl_usd=0.0,
                    baseline_expectancy=0.35,  # Historical prior 0.35R
                    current_expectancy=0.35,
                    drift_sigma=0.0,
                    is_edge_intact=True,
                )
                continue

            r_mults = [t.r_multiple for t in trades]
            pnls = [t.realized_pnl_usd for t in trades]
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p < 0]

            win_rate = (len(wins) / len(trades) * 100.0) if trades else 0.0
            gp = sum(wins) if wins else 1e-4
            gl = abs(sum(losses)) if losses else 1e-4
            pf = float(gp / gl) if gl > 0 else 1.0

            avg_r = float(np.mean(r_mults))
            baseline = 0.35  # Expected 0.35R
            std_r = float(np.std(r_mults)) if len(r_mults) > 1 else 1.0

            # Drift in standard deviations: (Baseline - Current) / (std / sqrt(N))
            if len(r_mults) >= self.min_trades_for_audit:
                se = std_r / math.sqrt(len(r_mults))
                drift = max(0.0, (baseline - avg_r) / max(1e-4, se))
                is_intact = avg_r > 0.0 and drift < self.drift_sigma_threshold
            else:
                drift = 0.0
                is_intact = True

            metrics[reg] = RegimeExpectancyMetrics(
                regime=reg,
                trade_count=len(trades),
                win_rate_pct=round(win_rate, 1),
                profit_factor=round(pf, 2),
                average_r_multiple=round(avg_r, 3),
                net_pnl_usd=round(float(sum(pnls)), 2),
                baseline_expectancy=baseline,
                current_expectancy=round(avg_r, 3),
                drift_sigma=round(drift, 2),
                is_edge_intact=is_intact,
            )

        return metrics

    def _evaluate_cusum_drift(self, regime_breakdown: Dict[str, RegimeExpectancyMetrics]) -> Tuple[float, bool]:
        drifts = [m.drift_sigma for m in regime_breakdown.values() if m.trade_count >= self.min_trades_for_audit]
        if not drifts:
            return 0.0, False

        max_drift = max(drifts)
        tripped = max_drift >= self.drift_sigma_threshold
        return max_drift, tripped

    def _dispatch_loss_autopsy(self, rec: TradeTelemetryRecord) -> LossAutopsyReport:
        """
        Triggers forensic root-cause analysis via LossAutopsyEngine.
        """
        report = loss_autopsy_engine.conduct_autopsy(
            trade_id=rec.trade_id,
            symbol=rec.symbol,
            entry_price=rec.entry_price,
            exit_price=rec.exit_price,
            direction="LONG" if rec.side.upper() in ["BUY", "LONG"] else "SHORT",
            pnl_usd=rec.realized_pnl_usd,
            slippage_bps=rec.entry_slippage_bps + rec.exit_slippage_bps,
        )
        audit_bus.emit_event(
            event_type="LOSS_AUTOPSY_DISPATCHED",
            symbol=rec.symbol,
            reason=f"Automated forensic triage for trade {rec.trade_id} ({report.loss_category.value})",
            severity="WARNING",
            details={"trade_id": rec.trade_id, "loss_category": str(report.loss_category.value), "pnl": rec.realized_pnl_usd},
        )
        return report

    def _empty_audit_report(self, now: int, burn_in_hours: float) -> SystemAuditHealthReport:
        return SystemAuditHealthReport(
            timestamp_ms=now,
            total_trades_logged=0,
            active_burn_in_hours=round(burn_in_hours, 2),
            cumulative_pnl_usd=0.0,
            peak_drawdown_pct=0.0,
            overall_win_rate_pct=0.0,
            overall_profit_factor=1.0,
            regime_expectancy_breakdown={},
            cusum_drift_score=0.0,
            quarantine_circuit_tripped=False,
            governance_status="HEALTHY_OPTIMAL",
            recent_autopsies=[],
            narrative="No telemetry trade records logged yet.",
        )


autonomous_risk_auditor = AutonomousRiskAuditor()
