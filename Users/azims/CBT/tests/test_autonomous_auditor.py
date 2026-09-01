"""
Unit tests for core/autonomous_auditor.py.
Verifies trade telemetry logging, automated loss autopsy dispatch,
regime-conditional expectancy drift audits, and strategy quarantine circuit breakers.
"""

import pytest
from core.autonomous_auditor import (
    AutonomousRiskAuditor,
    autonomous_risk_auditor,
    SystemAuditHealthReport,
    TradeTelemetryRecord,
)


def test_autonomous_auditor_empty_health():
    auditor = AutonomousRiskAuditor()
    report = auditor.audit_system_health()
    assert isinstance(report, SystemAuditHealthReport)
    assert report.total_trades_logged == 0
    assert report.governance_status == "HEALTHY_OPTIMAL"


def test_autonomous_auditor_record_trade_and_loss_autopsy():
    auditor = AutonomousRiskAuditor(burn_in_start_time_ms=1000)

    # Winning trade
    rec_win = auditor.record_trade(
        trade_id="t_01",
        symbol="BTC/USDT",
        side="BUY",
        entry_price=60000.0,
        exit_price=61500.0,
        qty=1.0,
        entry_time_ms=1000,
        exit_time_ms=61000,
        market_regime="TRENDING_BULL",
        risk_per_trade_usd=500.0,
    )
    assert rec_win.realized_pnl_usd > 0
    assert rec_win.r_multiple > 0
    assert rec_win.loss_autopsy_triggered is False

    # Losing trade (should trigger automated loss autopsy)
    rec_loss = auditor.record_trade(
        trade_id="t_02",
        symbol="BTC/USDT",
        side="BUY",
        entry_price=60000.0,
        exit_price=59000.0,
        qty=1.0,
        entry_time_ms=70000,
        exit_time_ms=120000,
        market_regime="TRENDING_BULL",
        risk_per_trade_usd=500.0,
    )
    assert rec_loss.realized_pnl_usd < 0
    assert rec_loss.loss_autopsy_triggered is True
    assert rec_loss.autopsy_category is not None


def test_autonomous_auditor_regime_drift_and_quarantine_trip():
    auditor = AutonomousRiskAuditor(drift_sigma_threshold=2.0, min_trades_for_audit=4)

    # Log 6 severe losing trades in RANGING_COMPRESSION regime to induce expectancy drift
    for i in range(6):
        auditor.record_trade(
            trade_id=f"t_loss_{i}",
            symbol="ETH/USDT",
            side="BUY",
            entry_price=3000.0,
            exit_price=2800.0,
            qty=2.0,
            entry_time_ms=1000 + i * 10000,
            exit_time_ms=2000 + i * 10000,
            market_regime="RANGING_COMPRESSION",
            risk_per_trade_usd=100.0,
        )

    report = auditor.audit_system_health()
    assert report.total_trades_logged == 6
    assert report.cumulative_pnl_usd < 0
    assert report.quarantine_circuit_tripped is True
    assert report.governance_status == "CIRCUIT_BREAKER_QUARANTINED"
    assert "RANGING_COMPRESSION" in report.regime_expectancy_breakdown
    assert report.regime_expectancy_breakdown["RANGING_COMPRESSION"].is_edge_intact is False
