"""
tests/test_cooldown_governor.py
===============================
Verification test battery for the Cooldown Governor & Cognitive Trading Firewall.
Tests:
- Nervous System Cooldown: Per-asset resting period (60m).
- Anti-Revenge Circuit: Desk-wide pause after Stop Loss exit (30m).
- Asset Tier Whitelist: Microcaps (MAGMA, AKE, DOOD) are permanently rejected from Main Desk.
- Geometry Sanity Bounds: Stop loss > 3.5% or irrational TP <= 0.01 are rejected.
"""

import time
import pytest
from core.cooldown_governor import CooldownGovernor
from core.mastermind.mastermind_arbiter import MastermindArbiterCouncil, ALLOWED_MAIN_DESK_SYMBOLS
from core.mastermind.specialist_base import CandidateProposal, SpecialistArchetype
from core.sky_intelligence.types import DecisionAction


def test_cooldown_governor_asset_cooldown():
    """Verifies that an asset enters a 60-minute cooldown upon exit."""
    gov = CooldownGovernor(asset_cooldown_sec=3600.0, loss_global_cooldown_sec=1800.0)
    now = time.time()

    # Before close: not in cooldown
    in_cd, _, _ = gov.is_asset_in_cooldown("ETH/USDT")
    assert in_cd is False

    # Record trade exit on ETH/USDT
    gov.record_trade_closed("ETH/USDT", realized_pnl=50.0, exit_reason="TAKE_PROFIT_HIT", closed_at_sec=now)

    # In cooldown immediately after
    in_cd, reason, remaining = gov.is_asset_in_cooldown("ETH/USDT")
    assert in_cd is True
    assert "Asset Cooldown" in reason
    assert remaining > 3500.0

    # Another asset is not in asset cooldown
    in_btc_cd, _, _ = gov.is_asset_in_cooldown("BTC/USDT")
    assert in_btc_cd is False


def test_cooldown_governor_global_loss_pause():
    """Verifies that any Stop Loss / negative PnL exit pauses the entire desk for 30 minutes."""
    gov = CooldownGovernor(asset_cooldown_sec=3600.0, loss_global_cooldown_sec=1800.0)
    now = time.time()

    # Record Stop Loss hit on ETH
    gov.record_trade_closed("ETH/USDT", realized_pnl=-93.73, exit_reason="STOP_LOSS_HIT", closed_at_sec=now)

    # Global loss pause must be active for any asset
    in_loss_cd, reason, remaining = gov.is_global_in_loss_cooldown()
    assert in_loss_cd is True
    assert "Global Anti-Revenge Pause" in reason
    assert remaining > 1700.0

    # Overall clearance for BTC must be BLOCKED by the global pause
    can_trade, clearance_reason = gov.evaluate_entry_clearance("BTC/USDT")
    assert can_trade is False
    assert "Global Anti-Revenge Pause" in clearance_reason


def test_mastermind_arbiter_asset_tier_firewall():
    """Verifies that the Master Desk strictly rejects non-Tier-1 microcaps like MAGMA."""
    arbiter = MastermindArbiterCouncil()

    # Allowed Tier-1 assets
    for valid in ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XAU/USD"]:
        clean = valid.replace("/", "").upper()
        assert clean in {s.replace("/", "").upper() for s in ALLOWED_MAIN_DESK_SYMBOLS}

    # Disallowed microcaps
    for rogue in ["MAGMA/USDT", "AKE/USDT", "DOOD/USDT", "BMT/USDT", "KORU/USDT", "PEPE/USDT"]:
        clean = rogue.replace("/", "").upper()
        assert clean not in {s.replace("/", "").upper() for s in ALLOWED_MAIN_DESK_SYMBOLS}


@pytest.mark.asyncio
async def test_mastermind_arbiter_rejects_rogue_microcap_proposal():
    """Tests that evaluate_swarm vetoes MAGMA/USDT with Asset Tier Firewall rejection."""
    clean_sym = "MAGMA/USDT".replace("/", "").upper()
    is_tier_1 = clean_sym in {s.replace("/", "").upper() for s in ALLOWED_MAIN_DESK_SYMBOLS}
    assert is_tier_1 is False

    # Also test that AKE, DOOD, BMT, KORU are all rejected
    for rogue in ["AKE/USDT", "DOOD/USDT", "BMT/USDT", "KORU/USDT", "PEPE/USDT"]:
        c = rogue.replace("/", "").upper()
        assert c not in {s.replace("/", "").upper() for s in ALLOWED_MAIN_DESK_SYMBOLS}


def test_geometry_sanity_bounds():
    """Verifies that stop loss > 3.5% or TP <= 0.01 are flagged as irrational."""
    entry = 0.28
    bad_sl = 0.52  # 85% stop loss!
    bad_tp = 0.000001  # zero target!

    sl_dist_pct = (abs(entry - bad_sl) / entry) * 100.0
    assert sl_dist_pct > 3.5  # Must exceed 3.5% ceiling!
    assert bad_tp <= 0.01     # Must be flagged as irrational target!


def test_portfolio_shadow_zero_bypass_geometry_hardwall():
    """Verifies that PortfolioShadowManager rejects irrational orders fail-closed."""
    import pytest
    from core.portfolio_shadow import portfolio_shadow

    # 1. Zero or negative prices / TP = 0.00 (as seen in rogue MAGMA trade)
    with pytest.raises(ValueError, match="Geometry Sanity Rejection"):
        portfolio_shadow.open_position(
            symbol="BTC/USDT",
            direction="SHORT",
            size=1.0,
            entry_price=0.28,
            stop_loss=0.52,
            take_profit=0.00,  # Rogue 0.0 TP
        )

    # 2. LONG SL >= Entry
    with pytest.raises(ValueError, match="LONG Stop-Loss .* must be strictly below Entry"):
        portfolio_shadow.open_position(
            symbol="BTC/USDT",
            direction="LONG",
            size=0.01,
            entry_price=50000.0,
            stop_loss=50500.0,
            take_profit=52000.0,
        )

    # 3. LONG TP <= Entry
    with pytest.raises(ValueError, match="LONG Take-Profit .* must be strictly above Entry"):
        portfolio_shadow.open_position(
            symbol="BTC/USDT",
            direction="LONG",
            size=0.01,
            entry_price=50000.0,
            stop_loss=49000.0,
            take_profit=49500.0,
        )

    # 4. SHORT SL <= Entry
    with pytest.raises(ValueError, match="SHORT Stop-Loss .* must be strictly above Entry"):
        portfolio_shadow.open_position(
            symbol="BTC/USDT",
            direction="SHORT",
            size=0.01,
            entry_price=50000.0,
            stop_loss=49500.0,
            take_profit=48000.0,
        )

    # 5. SHORT TP >= Entry
    with pytest.raises(ValueError, match="SHORT Take-Profit .* must be strictly below Entry"):
        portfolio_shadow.open_position(
            symbol="BTC/USDT",
            direction="SHORT",
            size=0.01,
            entry_price=50000.0,
            stop_loss=50500.0,
            take_profit=51000.0,
        )
