"""Tests for P12.6 trade cost modeling and net expectancy (data/costs.py).

Verifies the mathematical invariants established in docs/PATH_TO_REAL_MONEY.md §2:
  * Median stop distance 0.823% + 0.10% taker fee round-trip → −0.1215R cost
  * Fees are ~40× funding at 1.8h median hold
  * Long pays positive funding; short receives positive funding
  * Net R turns small gross winners into net losses honestly
"""

from __future__ import annotations

import pytest

from data.costs import (
    DEFAULT_FUNDING_RATE_8H,
    CostModel,
    calculate_trade_cost,
    get_funding_rate_as_of_t,
)


def test_cost_model_defaults_and_env(monkeypatch):
    m = CostModel()
    assert m.taker_fee_pct == 0.0005
    assert m.maker_fee_pct == 0.0002
    assert m.spot_fee_pct == 0.0010
    assert m.default_funding_rate_8h == 0.0001
    assert m.execution_type == "taker"
    assert m.market == "perp"
    assert m.enabled is True

    monkeypatch.setenv("COSTS_ENABLED", "0")
    monkeypatch.setenv("EXECUTION_TYPE", "maker")
    m_env = CostModel.from_env()
    assert m_env.enabled is False
    assert m_env.execution_type == "maker"


def test_fee_r_scales_with_stop_distance():
    """Pin the exact arithmetic from docs/PATH_TO_REAL_MONEY.md §2."""
    # Entry 100,000, SL 99,177 -> stop distance 823 (0.823% of entry)
    entry = 100_000.0
    sl = 99_177.0
    cost = calculate_trade_cost(
        entry=entry,
        stop_loss=sl,
        action="BUY",
        gross_r=2.0,
        holding_hours=1.8,
        symbol="BTCUSDT",
    )

    # 2 * 0.05% = 0.10% round trip = 0.0010
    # stop distance = 823 / 100000 = 0.00823
    # fee_r = 0.0010 / 0.00823 = 0.121506... -> round(4) = 0.1215
    assert cost.fee_r == pytest.approx(0.1215, abs=1e-4)


def test_fee_r_wider_stop_is_cheaper_in_r():
    # 2.0% stop distance -> fee_r = 0.0010 / 0.020 = 0.050R
    cost = calculate_trade_cost(
        entry=100.0, stop_loss=98.0, action="BUY", gross_r=2.0, symbol="BTCUSDT"
    )
    assert cost.fee_r == pytest.approx(0.050, abs=1e-4)


def test_fee_r_tighter_stop_is_more_expensive_in_r():
    # 0.20% stop distance -> fee_r = 0.0010 / 0.0020 = 0.500R (huge drag!)
    cost = calculate_trade_cost(
        entry=100.0, stop_loss=99.8, action="BUY", gross_r=2.0, symbol="BTCUSDT"
    )
    assert cost.fee_r == pytest.approx(0.500, abs=1e-4)


def test_spread_r_calculation():
    # BTCUSDT spread = 0.02% half-spread -> 0.04% round trip (0.0004)
    # Stop distance = 0.823% (0.00823)
    # spread_r = 0.0004 / 0.00823 = 0.0486R
    cost = calculate_trade_cost(entry=100_000.0, stop_loss=99_177.0, symbol="BTCUSDT")
    assert cost.slip_r == pytest.approx(0.0486, abs=1e-4)

    # ETHUSDT spread = 0.035% half-spread -> 0.07% round trip (0.0007)
    # spread_r = 0.0007 / 0.00823 = 0.0851R
    cost_eth = calculate_trade_cost(entry=100_000.0, stop_loss=99_177.0, symbol="ETHUSDT")
    assert cost_eth.slip_r == pytest.approx(0.0851, abs=1e-4)


def test_funding_r_holding_time_and_direction():
    """Pin the ~40x fees-over-funding ratio and direction asymmetry."""
    # 1.8h hold with 0.01%/8h rate on 0.823% stop:
    # funding_pct = 0.0001 * (1.8 / 8.0) = 0.0000225 (0.00225%)
    # funding_r = 0.0000225 / 0.00823 = 0.00273R
    cost_buy = calculate_trade_cost(
        entry=100_000.0,
        stop_loss=99_177.0,
        action="BUY",
        holding_hours=1.8,
        symbol="BTCUSDT",
    )
    assert cost_buy.funding_r == pytest.approx(0.0027, abs=1e-4)
    assert cost_buy.fee_r / cost_buy.funding_r == pytest.approx(45.0, abs=1.0)

    # SELL receives positive funding -> credit / negative funding_r
    cost_sell = calculate_trade_cost(
        entry=100_000.0,
        stop_loss=100_823.0,
        action="SELL",
        holding_hours=1.8,
        symbol="BTCUSDT",
    )
    assert cost_sell.funding_r == pytest.approx(-0.0027, abs=1e-4)
    # Total cost for short is lower because funding is received
    assert cost_sell.total_cost_r < cost_buy.total_cost_r


def test_spot_market_has_no_funding():
    model = CostModel(market="spot")
    cost = calculate_trade_cost(
        entry=100.0, stop_loss=99.0, action="BUY", holding_hours=24.0, cost_model=model
    )
    assert cost.funding_r == 0.0
    # Spot fee is 0.10% per side -> 0.20% round trip (0.0020 / 0.010 = 0.20R)
    assert cost.fee_r == pytest.approx(0.20, abs=1e-4)


def test_net_r_turns_small_gross_winner_into_net_loss():
    # Gross win of +0.10R with cost of ~0.17R yields net -0.07R (loss!)
    cost = calculate_trade_cost(
        entry=100_000.0,
        stop_loss=99_177.0,
        action="BUY",
        gross_r=0.10,
        holding_hours=1.8,
        symbol="BTCUSDT",
    )
    assert cost.gross_r == 0.10
    assert cost.total_cost_r > 0.15
    assert cost.net_r < 0.0


def test_net_r_increases_loss_size():
    # Gross loss of -1.0R with cost of 0.17R yields net -1.17R
    cost = calculate_trade_cost(
        entry=100_000.0,
        stop_loss=99_177.0,
        action="BUY",
        gross_r=-1.0,
        holding_hours=1.8,
        symbol="BTCUSDT",
    )
    assert cost.gross_r == -1.0
    assert cost.net_r == pytest.approx(-1.173, abs=0.01)


def test_costs_disabled_returns_zero_drag():
    model = CostModel(enabled=False)
    cost = calculate_trade_cost(entry=100.0, stop_loss=99.0, gross_r=1.5, cost_model=model)
    assert cost.fee_r == 0.0
    assert cost.slip_r == 0.0
    assert cost.funding_r == 0.0
    assert cost.total_cost_r == 0.0
    assert cost.net_r == 1.5


def test_maker_execution_cheaper_than_taker():
    taker_model = CostModel(execution_type="taker")
    maker_model = CostModel(execution_type="maker")
    maker_in_taker_out = CostModel(execution_type="maker_in_taker_out")

    c_taker = calculate_trade_cost(entry=100.0, stop_loss=99.0, cost_model=taker_model)
    c_maker = calculate_trade_cost(entry=100.0, stop_loss=99.0, cost_model=maker_model)
    c_hybrid = calculate_trade_cost(entry=100.0, stop_loss=99.0, cost_model=maker_in_taker_out)

    assert c_maker.fee_r < c_hybrid.fee_r < c_taker.fee_r
    assert c_maker.fee_r == pytest.approx(0.04, abs=1e-4)  # 2 * 0.02% / 1%
    assert c_hybrid.fee_r == pytest.approx(0.07, abs=1e-4)  # (0.02% + 0.05%) / 1%
    assert c_taker.fee_r == pytest.approx(0.10, abs=1e-4)  # 2 * 0.05% / 1%


def test_get_funding_rate_as_of_t_fallback():
    assert get_funding_rate_as_of_t("BTCUSDT", ts=None) == DEFAULT_FUNDING_RATE_8H
    assert get_funding_rate_as_of_t("BTCUSDT", ts=123456789) == DEFAULT_FUNDING_RATE_8H


# ---------------------------------------------------------------------------
# P12.10: XAU bid/ask cost model (Dukascopy blocker #2)
# ---------------------------------------------------------------------------


def test_is_gold_symbol():
    from data.costs import is_gold_symbol

    assert is_gold_symbol("XAUUSD")
    assert is_gold_symbol("xauusd")
    assert is_gold_symbol("XAU/USD")
    assert is_gold_symbol("GOLD")
    assert is_gold_symbol("gold")
    assert not is_gold_symbol("BTCUSDT")
    assert not is_gold_symbol("ETHUSDT")
    assert not is_gold_symbol("")
    assert not is_gold_symbol(None)


def test_cost_model_for_symbol_selects_gold_model():
    from data.costs import DEFAULT_GOLD_COMMISSION_PCT, cost_model_for_symbol

    m = cost_model_for_symbol("XAUUSD")
    assert m.market == "spot"
    assert m.default_funding_rate_8h == 0.0
    assert m.spot_fee_pct == DEFAULT_GOLD_COMMISSION_PCT
    assert m.execution_type == "taker"

    # BTC stays on the default perp model
    m_btc = cost_model_for_symbol("BTCUSDT")
    assert m_btc.market == "perp"
    assert m_btc.default_funding_rate_8h > 0


def test_cost_model_for_symbol_returns_base_model_unchanged():
    from data.costs import cost_model_for_symbol

    explicit = CostModel(market="perp", execution_type="maker")
    result = cost_model_for_symbol("XAUUSD", base_model=explicit)
    assert result is explicit
    assert result.market == "perp"


def test_xau_auto_detection_no_cost_model():
    """XAUUSD automatically uses spot gold assumptions when no cost_model given."""
    cost = calculate_trade_cost(
        entry=2000.0,
        stop_loss=1980.0,
        action="BUY",
        gross_r=2.0,
        holding_hours=1.8,
        symbol="XAUUSD",
    )
    # No funding on spot gold
    assert cost.funding_r == 0.0
    assert cost.funding_rate_8h == 0.0
    # Fee is gold commission: 2 * 0.005% / (20/2000 = 0.01) = 0.0001 / 0.01 = 0.01R
    assert cost.fee_r == pytest.approx(0.01, abs=1e-4)
    # Spread: XAUUSD half-spread = 0.06% -> 0.12% round-trip = 0.0012 / 0.01 = 0.12R
    assert cost.slip_r == pytest.approx(0.12, abs=1e-4)


def test_xau_has_no_funding_short_or_long():
    """Both long and short XAU have zero funding cost."""
    cost_buy = calculate_trade_cost(
        entry=2000.0,
        stop_loss=1980.0,
        action="BUY",
        holding_hours=24.0,
        symbol="XAUUSD",
    )
    cost_sell = calculate_trade_cost(
        entry=2000.0,
        stop_loss=2020.0,
        action="SELL",
        holding_hours=24.0,
        symbol="XAUUSD",
    )
    assert cost_buy.funding_r == 0.0
    assert cost_sell.funding_r == 0.0
    # Total costs are identical (no direction asymmetry on spot)
    assert cost_buy.total_cost_r == cost_sell.total_cost_r


def test_xau_gold_commission_scales_with_stop():
    """Gold commission is tiny at typical gold stop distances (~0.5-1.0%)."""
    # 0.5% stop on $2000 gold: entry=2000, sl=1990 -> stop_pct=0.005
    # fee = 2 * 0.005% / 0.005 = 0.0001 / 0.005 = 0.02R
    cost = calculate_trade_cost(entry=2000.0, stop_loss=1990.0, symbol="XAUUSD")
    assert cost.fee_r == pytest.approx(0.02, abs=1e-4)
    # Total cost is mostly spread
    assert cost.slip_r > cost.fee_r


def test_xau_explicit_model_overrides_auto_detect():
    """Passing an explicit CostModel prevents auto-detection."""
    crypto_model = CostModel(market="perp", taker_fee_pct=0.0005)
    cost = calculate_trade_cost(
        entry=2000.0, stop_loss=1980.0, symbol="XAUUSD", cost_model=crypto_model
    )
    # If auto-detect was active, funding_r would be 0 and fee_r would be 0.01.
    # With explicit perp model, fee uses taker rate and funding is computed.
    assert cost.funding_r != 0.0  # perp model applies funding


def test_xau_net_r_small_winner():
    """A small gross win on XAU is reduced by spread + commission."""
    # Gross win +0.50R on $2000 gold with 1% stop
    cost = calculate_trade_cost(
        entry=2000.0, stop_loss=1980.0, action="BUY", gross_r=0.50, symbol="XAUUSD"
    )
    # Total cost = fee_r + slip_r = 0.01 + 0.12 = 0.13R
    assert cost.gross_r == 0.50
    assert cost.total_cost_r == pytest.approx(0.13, abs=1e-4)
    assert cost.net_r == pytest.approx(0.37, abs=1e-4)


def test_xau_spread_is_primary_cost():
    """For XAU, the spread component dominates over commission."""
    cost = calculate_trade_cost(entry=2000.0, stop_loss=1980.0, symbol="XAUUSD")
    assert cost.slip_r > 0
    assert cost.fee_r > 0
    assert cost.slip_r > cost.fee_r  # spread is the main cost
    assert cost.funding_r == 0.0  # no funding on spot


def test_gold_symbol_prefixes_match_common_variants():
    from data.costs import is_gold_symbol

    assert is_gold_symbol("XAUEUR")
    assert is_gold_symbol("XAUGBP")
    assert is_gold_symbol("XAU/GBP")
    assert is_gold_symbol("GOLD100")
    assert is_gold_symbol("gold-futures")
    assert not is_gold_symbol("BTCXAU")  # suffix, not prefix
    assert not is_gold_symbol("PAXGUSDT")  # tokenized gold, not spot gold
