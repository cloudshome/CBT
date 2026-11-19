"""
tests/test_m62_institutional_audit_remediation.py
=================================================
Milestone 62: Institutional Audit Remediation & Hardening Test Suite.

Verifies:
1. Airgap Bypass Injection: asserts ExchangeAuthenticationError in PRODUCTION even with
   PYTEST_CURRENT_TEST=1 and an external mock session.
2. Egress Allowlist Adversarial Matrix: asserts fail-closed PermissionError on unapproved hosts,
   raw IP addresses, and private account endpoints; permits whitelisted public and testnet hosts.
3. Unauthenticated FastAPI Rejection: asserts HTTP 401 when mutating routes are called without X-API-Key.
4. Backtester Lookahead & Accounting Proofs:
   - Same-bar entry touch and stop plunge records LOSS (-1.0R), not NOT_TRIGGERED.
   - Post-ratchet ambiguity (touching both current_stop and target_tp2) asserts conservative sl_touched wins.
   - Blended runner accounting: 35% banked at +1.50R and 65% at +3.10R yields 2.54R, never 3.10R on 100%.
5. Timestamp-Aligned Daily Sharpe Proof: Clustered returns on 2 days across 30 calendar days produce
   strictly lower daily Sharpe than uniformly spaced returns (proving np.linspace distortion is eliminated).
6. Hermes Agent Bridge Hardening: asserts validation rejection on leading '-' flags and oversized queries.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import core.auth as auth_mod
from app import app
from core.cognitive_brain.hermes_agent_bridge import HermesAgentBridge
from core.execution.connectors.base import ExchangeAuthenticationError
from core.execution.connectors.binance_connector import BinanceSpotConnector
from core.execution.connectors.bybit_connector import BybitV5Connector
from core.security.egress_firewall_verifier import OutboundEgressPolicy
from data.backtester import _evaluate
from scripts.research.run_m57_mtf_15m_4h_walk_forward_audit import compute_calendar_day_daily_sharpe

TEST_API_KEY = "sk-m62-remediation-test-key-2026"


# ==============================================================================
# 1. AIRGAP BYPASS INJECTION
# ==============================================================================


@pytest.mark.asyncio
async def test_airgap_bypass_injection_fails_closed(monkeypatch):
    """
    Asserts ExchangeAuthenticationError is raised in PRODUCTION even when
    PYTEST_CURRENT_TEST is set and an external mock session is injected.
    """
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_m62::dummy_test")

    mock_session = MagicMock()
    mock_session.get = AsyncMock()
    mock_session.post = AsyncMock()

    binance_prod = BinanceSpotConnector(
        api_key="mock_key",
        api_secret="mock_secret",
        environment="PRODUCTION",
        session=mock_session,
    )

    with pytest.raises(ExchangeAuthenticationError, match="REAL_CAPITAL_LOCK"):
        await binance_prod.get_balances()

    mock_session.get.assert_not_called()
    mock_session.post.assert_not_called()

    bybit_prod = BybitV5Connector(
        api_key="mock_key",
        api_secret="mock_secret",
        environment="PRODUCTION",
        session=mock_session,
    )

    with pytest.raises(ExchangeAuthenticationError, match="REAL_CAPITAL_LOCK"):
        await bybit_prod.get_balances()


# ==============================================================================
# 2. EGRESS ALLOWLIST ADVERSARIAL MATRIX
# ==============================================================================


def test_egress_allowlist_adversarial_matrix():
    """
    Verifies that OutboundEgressPolicy operates as a strict fail-closed allowlist.
    """
    blocked_matrix = [
        ("POST", "https://api4.binance.com/api/v3/order"),
        ("POST", "https://api-gcp.binance.com/api/v3/order"),
        ("POST", "https://papi.binance.com/papi/v1/order"),
        ("POST", "https://api.bytick.com/v5/order/create"),
        ("POST", "https://api.okx.com/api/v5/trade/order"),
        ("POST", "https://api.coinbase.com/api/v3/brokerage/orders"),
        ("GET", "https://1.2.3.4/api/v3/klines"),
        ("GET", "https://api.binance.com/api/v3/account"),
        ("GET", "https://fapi.binance.com/fapi/v2/account"),
        ("POST", "https://api.binance.com/api/v3/order"),
        ("DELETE", "https://fapi.binance.com/fapi/v1/order"),
    ]

    for method, url in blocked_matrix:
        with pytest.raises(PermissionError, match="EGRESS_FIREWALL_BLOCKED"):
            OutboundEgressPolicy.verify_request(method, url)

    allowed_matrix = [
        ("GET", "https://testnet.binance.vision/api/v3/klines"),
        ("POST", "https://testnet.binance.vision/api/v3/order"),
        ("POST", "https://testnet.binancefuture.com/fapi/v1/order"),
        ("POST", "https://api-testnet.bybit.com/v5/order/create"),
        ("GET", "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT"),
        ("GET", "https://api.binance.com/api/v3/klines?symbol=BTCUSDT"),
        ("GET", "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT"),
        ("POST", "https://api.telegram.org/bot123456:ABC/sendMessage"),
    ]

    for method, url in allowed_matrix:
        allowed, reason = OutboundEgressPolicy.verify_request(method, url)
        assert allowed is True
        assert reason == "ALLOWED_PUBLIC_OR_TESTNET_EGRESS"


# ==============================================================================
# 3. UNAUTHENTICATED FASTAPI REJECTION
# ==============================================================================


def test_unauthenticated_fastapi_rejection(monkeypatch):
    """
    Asserts HTTP 401 when calling newly protected routes without X-API-Key.
    """
    monkeypatch.setattr(auth_mod, "API_KEY", TEST_API_KEY)
    client = TestClient(app)

    routes_to_test = [
        ("/api/mastermind/specialists/deploy", {"symbol": "BTC/USDT"}),
        ("/api/research/share-telegram", {"summary_text": "audit test"}),
        ("/api/v1/hermes/query", {"query": "evaluate setup"}),
        ("/api/v1/hermes/market-critique", {"symbol": "BTC/USDT", "hypothesis": "order flow sweep"}),
        ("/api/risk/half-kelly-calc", {"symbol": "BTC/USDT", "entryPrice": 60000.0, "sl": 59000.0, "tp": 63000.0}),
        ("/api/execution/simulate_impact", {"order_size": 1.0, "mid_price": 60000.0, "order_side": "BUY"}),
        ("/api/execution/sor/route-quote", {"symbol": "BTCUSDT", "side": "BUY", "total_qty": 1.0}),
        ("/api/execution/slicer/almgren-chriss", {"symbol": "BTCUSDT", "total_qty": 1.0, "time_horizon_sec": 300}),
    ]

    for path, payload in routes_to_test:
        resp = client.post(path, json=payload)
        assert resp.status_code == 401, f"Path {path} should require auth, got {resp.status_code}"

    # Verify authorization succeeds with valid X-API-Key
    auth_header = {"X-API-Key": TEST_API_KEY}
    resp_authed = client.post(
        "/api/risk/half-kelly-calc",
        json={"symbol": "BTC/USDT", "entryPrice": 60000.0, "sl": 59000.0, "tp": 63000.0},
        headers=auth_header,
    )
    assert resp_authed.status_code == 200


# ==============================================================================
# 4. BACKTESTER LOOKAHEAD & ACCOUNTING PROOFS
# ==============================================================================


def test_backtester_same_bar_entry_sl_records_loss():
    """
    Synthetic bar where price touches entry AND plunges to sl on the same bar.
    Must record LOSS (-1.0R), NOT NOT_TRIGGERED.
    """
    # BUY plan: entry=100.0, sl=95.0, tp=115.0
    plan = {
        "action": "BUY",
        "entry": 100.0,
        "stop_loss": 95.0,
        "take_profit": 115.0,
        "status": "waiting",
        "type": "Sweep Reversal Buy",
        "confidence": 80,
    }

    # Candle reaches 102.0 high, plunges to 94.0 low (breaching both entry 100 and sl 95)
    # Candle 0 is setup bar, Candle 1 is future test bar
    df = pd.DataFrame(
        {
            "ts": [1000000, 1000000 + 900000],
            "open": [101.0, 101.0],
            "high": [102.0, 102.0],
            "low": [99.0, 94.0],
            "close": [101.0, 94.0],
            "cvd": [0.0, 0.0],
        }
    )
    df.attrs["timeframe"] = "15m"

    gp = _evaluate(
        plan=plan,
        df=df,
        i=0,
        horizon_bars=5,
        progressive_ratchet=True,
    )

    assert gp.outcome == "LOSS", f"Expected LOSS on same-bar stop plunge, got {gp.outcome}"
    assert gp.rr_achieved == -1.0, f"Expected -1.0R, got {gp.rr_achieved}"
    assert gp.ambiguous_bar is True


def test_backtester_post_ratchet_conservative_sl_wins():
    """
    Synthetic bar after stage2_hit=True touching BOTH current_stop and target_tp2.
    Asserts conservative sl_touched wins (PARTIAL_WIN), NOT FULL_WIN.
    """
    # BUY plan: entry=100.0, risk=10.0 (sl=90.0), tp1=115.0 (+1.5R), tp2=131.0 (+3.1R)
    plan = {
        "action": "BUY",
        "entry": 100.0,
        "stop_loss": 90.0,
        "take_profits": [115.0, 131.0],
        "status": "waiting",
        "type": "Sweep Reversal Buy",
        "confidence": 80,
    }

    # Bar 1 hits TP1 (115.0) -> stage2_hit activated, current_stop moved to +0.65R = 106.50
    # Bar 2 is ambiguous: low=105.0 (touches current_stop 106.5) AND high=132.0 (touches tp2 131.0)
    df = pd.DataFrame(
        {
            "ts": [1000000, 1000000 + 900000, 1000000 + 1800000, 1000000 + 2700000],
            "open": [100.0, 100.0, 110.0, 110.0],
            "high": [100.0, 116.0, 132.0, 110.0],
            "low": [100.0, 99.0, 105.0, 110.0],
            "close": [100.0, 114.0, 110.0, 110.0],
            "cvd": [0.0, 0.0, 0.0, 0.0],
        }
    )
    df.attrs["timeframe"] = "15m"

    gp = _evaluate(
        plan=plan,
        df=df,
        i=0,
        horizon_bars=10,
        progressive_ratchet=True,
    )

    assert gp.outcome == "PARTIAL_WIN", f"Expected conservative PARTIAL_WIN, got {gp.outcome}"
    assert gp.rr_achieved != 3.10
    # Reversal RR for M47: 0.35 * 1.50 + 0.65 * 0.65 = 0.525 + 0.4225 = 0.9475R
    assert abs(gp.rr_achieved - 0.9475) < 0.01


def test_backtester_blended_tp2_accounting():
    """
    Synthetic winning runner after stage2_hit=True:
    35% banked at +1.50R, 65% hitting +3.10R.
    Must compute round(0.35 * 1.50 + 0.65 * 3.10, 4) = 2.54R, NEVER 3.10R on 100%.
    """
    plan = {
        "action": "BUY",
        "entry": 100.0,
        "stop_loss": 90.0,
        "take_profits": [115.0, 131.0],
        "status": "waiting",
        "type": "Sweep Reversal Buy",
        "confidence": 80,
    }

    # Bar 1 hits TP1 (+1.5R, 115.0) -> banks 35% at 1.50R, current_stop = 106.50
    # Bar 2 cleanly hits TP2 (+3.1R, 131.0) with low=112.0 safely above 106.50
    df = pd.DataFrame(
        {
            "ts": [1000000, 1000000 + 900000, 1000000 + 1800000],
            "open": [100.0, 100.0, 114.0],
            "high": [100.0, 116.0, 132.0],
            "low": [100.0, 99.0, 112.0],
            "close": [100.0, 114.0, 131.0],
            "cvd": [0.0, 0.0, 0.0],
        }
    )
    df.attrs["timeframe"] = "15m"

    gp = _evaluate(
        plan=plan,
        df=df,
        i=0,
        horizon_bars=5,
        progressive_ratchet=True,
    )

    assert gp.outcome == "FULL_WIN"
    expected_blended = round(0.35 * 1.50 + 0.65 * 3.10, 4)  # 2.54R
    assert gp.rr_achieved == expected_blended, f"Expected {expected_blended}R, got {gp.rr_achieved}R"


# ==============================================================================
# 5. TIMESTAMP-ALIGNED DAILY SHARPE PROOF
# ==============================================================================


def test_timestamp_aligned_daily_sharpe_eliminates_linspace_distortion():
    """
    Proves that clustered returns produce strictly lower Daily Sharpe than uniform spacing.
    Case A (Uniform): 10 trades of +1.0R evenly spaced across 30 days (1 every 3 days).
    Case B (Clustered): 10 trades of +1.0R on only 2 active days (5 trades/day), 28 zero days.
    """
    day_ms = 86_400_000
    base_ts = 1700000000000

    # Case A: Uniformly spaced trades
    uniform_trades = [
        {"ts": base_ts + i * 3 * day_ms, "exit_ts": base_ts + i * 3 * day_ms + 3600000, "rr_net": 1.0}
        for i in range(10)
    ]
    sh_uniform, days_u, active_u = compute_calendar_day_daily_sharpe(uniform_trades)

    # Case B: Clustered trades on 2 days
    clustered_trades = [
        {"ts": base_ts, "exit_ts": base_ts + 3600000, "rr_net": 1.0} for _ in range(5)
    ] + [
        {"ts": base_ts + 29 * day_ms, "exit_ts": base_ts + 29 * day_ms + 3600000, "rr_net": 1.0}
        for _ in range(5)
    ]
    sh_clustered, days_c, active_c = compute_calendar_day_daily_sharpe(clustered_trades)

    assert days_u >= 28
    assert days_c >= 28
    assert active_u == 10
    assert active_c == 2

    # Clustered returns have much higher variance across calendar days, so daily Sharpe must be strictly lower
    assert sh_clustered < sh_uniform, (
        f"Clustered daily Sharpe ({sh_clustered}) should be strictly lower than uniform ({sh_uniform})"
    )


# ==============================================================================
# 6. HERMES AGENT BRIDGE HARDENING
# ==============================================================================


@pytest.mark.asyncio
async def test_hermes_bridge_rejects_flag_injection_and_oversized_queries():
    """
    Verifies that HermesAgentBridge rejects model/provider flag injection and oversized queries.
    """
    bridge = HermesAgentBridge(hermes_path="/nonexistent/hermes")

    # Flag injection attempt
    with pytest.raises(ValueError, match="flag injection attempt"):
        await bridge.ask_hermes("test query", model="-o /tmp/evil")

    with pytest.raises(ValueError, match="flag injection attempt"):
        await bridge.ask_hermes("test query", provider="--evil-arg")

    # Oversized query > 8000 chars
    huge_query = "x" * 8001
    with pytest.raises(ValueError, match="exceeds maximum allowed 8000"):
        await bridge.ask_hermes(huge_query)
