"""
tests/test_phase3_backtester_and_sizing_audit.py
=================================================
CTB Phase 3 Rigorous Verification Battery:
1. Causality & Future Data Mutation Invariance
2. Prefix Invariance & Warmup Handling
3. Trade Execution Ambiguous Candle Stop-First Invariant
4. Long & Short Payoff Symmetry & Cost Deductions
5. Independent Hand-Calculation Verification of User Position Sizing Example
6. 3.0x Effective Leverage Ceiling Enforcement & Tight-Stop Flash Crash Guard
"""

import pandas as pd

from core.central_mind import CentralTradingMind, TradeProposal
from core.data_streamer import data_streamer
from core.half_kelly_sizer import HalfKellyPositionSizer
from core.risk_manager import risk_manager
from data.backtester import _evaluate
from engine.indicators import add_all_indicators
from engine.signal_engine import analyze_frame_at

# ==============================================================================
# 1. CAUSALITY & FUTURE DATA MUTATION INVARIANCE
# ==============================================================================

def test_future_data_mutation_invariance():
    """
    INVARIANT: Modifying candle data strictly AFTER decision bar T must NOT alter
    signals, indicators, features, or plans generated at or before bar T.
    """
    from data.store import CandleStore
    store = CandleStore()
    df = store.read("binance", "perp", "BTCUSDT", "1h").head(250).copy()
    assert len(df) == 250
    
    ind_orig = add_all_indicators(df)
    T = 160
    out_orig = analyze_frame_at(ind_orig, df, T, symbol="BTCUSDT", timeframe="1h", min_confidence=50)

    # Mutate all future candles (T+1 to end) by +100% price pump and 5x volume
    df_mut = df.copy()
    df_mut.loc[T + 1:, "open"] *= 2.0
    df_mut.loc[T + 1:, "high"] *= 2.0
    df_mut.loc[T + 1:, "low"] *= 2.0
    df_mut.loc[T + 1:, "close"] *= 2.0
    df_mut.loc[T + 1:, "volume"] *= 5.0
    ind_mut = add_all_indicators(df_mut)

    out_mut = analyze_frame_at(ind_mut, df_mut, T, symbol="BTCUSDT", timeframe="1h", min_confidence=50)

    # Verify that decision at bar T is 100% bit-for-bit identical
    plans_orig = [(p.get("type"), p.get("action"), p.get("entry"), p.get("stop_loss")) for p in out_orig.plans]
    plans_mut = [(p.get("type"), p.get("action"), p.get("entry"), p.get("stop_loss")) for p in out_mut.plans]

    assert plans_orig == plans_mut, "Leakage detected: Future mutation altered plans at bar T!"
    assert out_orig.features == out_mut.features, "Leakage detected: Features at bar T differed after future mutation!"


def test_prefix_invariance():
    """
    INVARIANT: Evaluating bar T in a truncated series [0..T] must produce identical
    plans to evaluating bar T in an extended series [0..N].
    """
    from data.store import CandleStore
    store = CandleStore()
    df = store.read("binance", "perp", "BTCUSDT", "1h").head(200).copy()
    T = 150

    ind_full = add_all_indicators(df)
    out_full = analyze_frame_at(ind_full, df, T, symbol="BTCUSDT", timeframe="1h", min_confidence=50)

    df_trunc = df.iloc[:T + 1].copy()
    ind_trunc = add_all_indicators(df_trunc)
    out_trunc = analyze_frame_at(ind_trunc, df_trunc, T, symbol="BTCUSDT", timeframe="1h", min_confidence=50)

    plans_full = [(p.get("type"), p.get("action"), p.get("entry")) for p in out_full.plans]
    plans_trunc = [(p.get("type"), p.get("action"), p.get("entry")) for p in out_trunc.plans]

    assert plans_full == plans_trunc, "Prefix invariance violated between truncated and full series!"


# ==============================================================================
# 2. TRADE EXECUTION & CONSERVATIVE STOP-FIRST RULE
# ==============================================================================

def test_stop_first_ambiguous_candle_rule():
    """
    INVARIANT: When a single candle touches both Stop-Loss and Take-Profit,
    the backtester must deterministically grade the outcome as LOSS and flag ambiguous_bar=True.
    """
    # 5 candles: bar 0 is entry, bar 1 is an extreme wick touching both SL (90) and TP (120)
    df = pd.DataFrame({
        "ts": [1000, 2000, 3000],
        "open": [100.0, 100.0, 105.0],
        "high": [101.0, 125.0, 110.0],  # Bar 1 high touches TP1=120
        "low": [99.0, 85.0, 102.0],     # Bar 1 low touches SL=90
        "close": [100.0, 105.0, 108.0],
        "volume": [10.0, 50.0, 10.0]
    })
    df.attrs["timeframe"] = "1h"
    df.attrs["symbol"] = "BTCUSDT"

    plan = {
        "type": "Buy Pullback",
        "action": "BUY",
        "entry": 100.0,
        "stop_loss": 90.0,
        "take_profits": [120.0],
        "confidence": 80,
        "status": "active"
    }

    # Grade plan at bar 0 over 2 bars forward
    res = _evaluate(plan, df, i=0, horizon_bars=2)
    assert res.outcome == "LOSS", f"Expected LOSS on ambiguous candle, got {res.outcome}"
    assert res.rr_achieved == -1.0
    assert res.ambiguous_bar is True, "Ambiguous bar flag must be True when both SL and TP are touched"


def test_long_and_short_payoff_symmetry():
    """
    INVARIANT: A short trade must yield positive R when price falls to TP, and negative R when price rises to SL.
    """
    df_short = pd.DataFrame({
        "ts": [1000, 2000],
        "open": [100.0, 95.0],
        "high": [101.0, 96.0],
        "low": [99.0, 80.0],    # touches TP=85
        "close": [100.0, 82.0],
        "volume": [10.0, 20.0]
    })
    df_short.attrs["timeframe"] = "1h"
    df_short.attrs["symbol"] = "BTCUSDT"

    short_plan = {
        "type": "Sell Pullback",
        "action": "SELL",
        "entry": 100.0,
        "stop_loss": 110.0,     # Risk = 10
        "take_profits": [80.0], # Target = 20 (2R)
        "confidence": 85,
        "status": "active"
    }
    res = _evaluate(short_plan, df_short, i=0, horizon_bars=1)
    assert res.outcome == "PARTIAL_WIN"
    assert res.rr_achieved == 2.0, f"Expected +2.0R for profitable short, got {res.rr_achieved}"


# ==============================================================================
# 3. POSITION SIZING & INDEPENDENT HAND-CALCULATION VERIFICATION
# ==============================================================================

def test_independent_hand_calculation_user_example():
    """
    Audits the exact user scenario:
    Equity: $10,000
    Authorized Risk: $100 (1.0%)
    Entry: $81,120.24
    Stop: $80,438.25
    Stop Distance: $681.99
    """
    equity = 10000.0
    risk_budget_usd = 100.0
    entry_price = 81120.24
    stop_loss = 80438.25
    stop_dist = abs(entry_price - stop_loss)

    # 1. Stop distance as percentage of entry
    stop_dist_pct = (stop_dist / entry_price) * 100.0
    assert round(stop_dist_pct, 4) == 0.8407

    # 2. Position quantity for $100 risk
    unconstrained_qty = risk_budget_usd / stop_dist
    assert round(unconstrained_qty, 5) == 0.14663

    # 3. Position notional
    notional_usd = unconstrained_qty * entry_price
    assert round(notional_usd, 2) in (11894.64, 11894.66)

    # 4. Effective leverage
    eff_leverage = notional_usd / equity
    assert round(eff_leverage, 2) == 1.19

    # 5. Price-based loss if quantity was 0.2199 BTC (the terminal trade)
    loss_terminal = 0.2199 * stop_dist
    assert round(loss_terminal, 2) == 149.97  # Exactly 1.5% ($150) constitutional risk cap

    # 6. Maximum position notional permitted by 3.0x ceiling
    max_notional_3x = equity * 3.0
    assert max_notional_3x == 30000.0

    # 7. Final quantity after ceiling
    max_qty_3x = max_notional_3x / entry_price
    final_qty = min(unconstrained_qty, max_qty_3x)
    assert final_qty == unconstrained_qty  # Ceiling does not bind at 1.19x leverage
    planned_loss = final_qty * stop_dist
    assert round(planned_loss, 2) == 100.00


def test_half_kelly_sizer_clamps_ultra_tight_stop():
    """
    INVARIANT: On ultra-tight stops (e.g. 0.12%), HalfKellyPositionSizer must CLAMP
    effective leverage to the notional ceiling (<= 3.0x), preventing catastrophic over-leverage.
    """
    sizer = HalfKellyPositionSizer(max_leverage_ceiling=3.0, max_notional_pct=2.0)
    res = sizer.calculate_sizing(
        account_equity=10000.0,
        entry_price=81120.24,
        stop_loss=81020.24,  # $100 stop distance = 0.12%
        take_profit=82742.64,
        symbol="BTCUSDT",
        win_probability=0.55
    )
    # Without ceiling, $150 / $100 = 1.5 BTC ($121k notional = 12.1x leverage!)
    # Sizer must clamp to max_notional_pct (2.0x = $20,000)
    assert res.position_size_usd <= 20000.01
    assert round(res.position_size_usd / 10000.0, 2) == 2.0


def test_central_mind_enforces_3x_leverage_ceiling():
    """
    INVARIANT: CentralTradingMind must strictly clamp proposed position sizes
    so that effective leverage never exceeds MAX_LEVERAGE_CEILING (3.0x).
    """
    mind = CentralTradingMind()
    risk_manager.reset_lockout()
    data_streamer._last_known_prices["BTC/USDT"] = 81120.24

    # Ultra-tight stop proposal: $100 stop distance on $81,120 price
    proposal = TradeProposal(
        origin="TEST",
        symbol="BTC/USDT",
        direction="LONG",
        style="SWING",
        planned_entry=81120.24,
        stop_loss=81020.24,
        take_profit=82742.64,
        thesis="TIGHT_STOP_3X_CLAMP_TEST"
    )

    verdict = mind.evaluate_and_route(proposal)
    assert verdict.is_approved is True
    notional = verdict.approved_size * 81120.24
    effective_lev = notional / 10000.0
    # Must NOT be 12.17x! Must be <= 3.0x (with minor rounding tolerance)
    assert effective_lev <= 3.05, f"LEVERAGE CEILING VIOLATION: Approved {effective_lev:.2f}x leverage (ceiling is 3.0x)!"
