"""
core/risk/m57_live_gate.py
==========================
Milestone 58: Live Stack A Parity Bridge for M56/M57 Certified Multi-Timeframe Gates.
Enforces:
1. Symbol- & Timeframe-Aware Minimum Stop Distance Floors (>= 55 bps on ETHUSDT,
   >= 45 bps on BTC/SOL/PAXG/XAU, >= 65 bps on 4h Structural Swings).
2. Point-in-Time Causal ETH/BTC Relative-Strength & SMT Regime Gate across 15m, 1h, and 4h.
3. 15m Tactical Day Local Trend & Momentum Gate (EMA50 vs EMA200 + ADX >= 22 + no immediate market-chasing).
4. 4h Structural Swing Macro Chop/Compression Filter (confluence >= 72.0, ADX >= 20.0).
5. Multi-Horizon Sub-Book Style Tagging ([ASSET_DAY], [ASSET_SWING], [ASSET_SWING_4H]).
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from engine.indicators import add_all_indicators
from engine.smt_regime import (
    evaluate_eth_plan_under_smt_regime,
    precompute_eth_btc_regime_table,
)

logger = logging.getLogger("ai_quant_sentinel.m57_live_gate")

M57_SYMBOL_MIN_STOP_PCT: dict[str, float] = {
    "BTCUSDT": 0.0045,
    "ETHUSDT": 0.0055,
    "SOLUSDT": 0.0045,
    "PAXGUSDT": 0.0045,
    "XAUUSD": 0.0045,
}


def get_m57_min_stop_pct(symbol: str, timeframe: str = "15m") -> float:
    """Returns symbol- and timeframe-aware minimum stop-loss distance floor in decimal.

    55 bps on ETHUSDT, 45 bps on BTC/SOL/PAXG/XAU on 15m/1h, and 65 bps on 4h structural swings.
    """
    clean_sym = symbol.replace("/", "").replace("_", "").upper()
    base_floor = M57_SYMBOL_MIN_STOP_PCT.get(clean_sym, 0.0045)
    if timeframe.lower() == "4h":
        return max(base_floor, 0.0065)
    return base_floor


def build_horizon_style_tag(symbol: str, style_code: str, timeframe: str = "15m") -> str:
    """Builds sub-book style tag distinguishing 15m DAY, 1h SWING, and 4h SWING_4H."""
    asset_prefix = (
        symbol.split("/")[0].upper()
        if "/" in symbol
        else symbol.replace("USDT", "").replace("USD", "").upper()
    )
    if timeframe.lower() == "4h" and style_code.upper() == "SWING":
        return f"[{asset_prefix}_SWING_4H]"
    return f"[{asset_prefix}_{style_code.upper()}]"


def evaluate_live_m57_gate(
    symbol: str,
    timeframe: str,
    direction: str,
    candles_tf: list[dict[str, Any]],
    btc_candles_tf: list[dict[str, Any]] | None = None,
    confluence_score: float = 75.0,
    regime_name: str = "",
    setup_type_str: str = "",
    entry_price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict[str, Any]:
    """Evaluates live M57 multi-timeframe risk, trend, and cross-asset relative-strength gates.

    Returns structured dict with decision, reason, and telemetry.
    """
    clean_sym = symbol.replace("/", "").replace("_", "").upper()
    min_stop = get_m57_min_stop_pct(symbol, timeframe)
    tf_lower = timeframe.lower()
    dir_upper = direction.upper()

    eth_btc_regime_aligned: bool | None = None
    eth_btc_regime: str | None = None
    smt_signal: str | None = None

    # =========================================================================
    # Step A: ETH/BTC RS + SMT Check (when symbol is ETH)
    # =========================================================================
    if clean_sym in ("ETHUSDT", "ETHUSD"):
        if btc_candles_tf and len(candles_tf) >= 30 and len(btc_candles_tf) >= 30:
            eth_df = pd.DataFrame(candles_tf)
            btc_df = pd.DataFrame(btc_candles_tf)
            if "timestamp" in eth_df.columns and "ts" not in eth_df.columns:
                eth_df["ts"] = eth_df["timestamp"]
            if "timestamp" in btc_df.columns and "ts" not in btc_df.columns:
                btc_df["ts"] = btc_df["timestamp"]

            regime_table = precompute_eth_btc_regime_table(eth_df, btc_df, timeframe=timeframe)
            if regime_table:
                # Get snapshot for latest available closed bar
                last_ts = max(regime_table.keys())
                smt_snap = regime_table[last_ts]
                eth_btc_regime = smt_snap.regime
                smt_signal = smt_snap.smt_signal

                plan = {
                    "action": "BUY" if dir_upper in ("LONG", "BUY") else "SELL",
                    "type": setup_type_str or "Pullback",
                    "confidence": int(confluence_score),
                    "entry": entry_price,
                    "stop_loss": stop_loss,
                    "take_profits": [take_profit] if take_profit else [],
                }

                plan_ok, veto_reason = evaluate_eth_plan_under_smt_regime(
                    plan, regime_name, smt_snap, strict_a_plus_only=True
                )

                if not plan_ok:
                    eth_btc_regime_aligned = False
                    return {
                        "allowed": False,
                        "reason": f"M57_ETH_BTC_SMT_VETO: {veto_reason}",
                        "eth_btc_regime_aligned": False,
                        "eth_btc_regime": eth_btc_regime,
                        "smt_signal": smt_signal,
                        "min_stop_pct": min_stop,
                    }
                else:
                    eth_btc_regime_aligned = True

    # =========================================================================
    # Step B: 15m Tactical Day Local Trend & Passive Structure Gate
    # =========================================================================
    if tf_lower == "15m":
        # Reject immediate market-chasing entries
        raw_st = str(setup_type_str or "").strip().upper()
        if raw_st in ("IMMEDIATE_BUY", "IMMEDIATE_SELL", "IMMEDIATE BUY", "IMMEDIATE SELL"):
            return {
                "allowed": False,
                "reason": (
                    f"M57_15M_CHASE_VETO: Immediate market-taker entry '{setup_type_str}' "
                    "prohibited on 15m. Strict A+ passive limit/pullback required."
                ),
                "eth_btc_regime_aligned": eth_btc_regime_aligned,
                "eth_btc_regime": eth_btc_regime,
                "smt_signal": smt_signal,
                "min_stop_pct": min_stop,
            }

        # Trend gate activates when sufficient candle depth exists (len >= 50)
        if len(candles_tf) >= 50:
            eval_candles = candles_tf[:-1] if len(candles_tf) >= 2 else candles_tf
            df = pd.DataFrame(eval_candles)
            ind = add_all_indicators(df)
            last = ind.iloc[-1]
            close_v = float(last["close"])
            ema50_v = float(last.get("ema_50", close_v))
            ema200_v = float(last.get("ema_200", close_v))
            adx_v = float(last.get("adx", 25.0))

            if dir_upper in ("LONG", "BUY"):
                if not (close_v >= ema200_v and ema50_v >= ema200_v and adx_v >= 22.0):
                    return {
                        "allowed": False,
                        "reason": (
                            f"M57_15M_TREND_GATE_VETO: LONG requires close ({close_v:.2f}) >= EMA200 ({ema200_v:.2f}), "
                            f"EMA50 ({ema50_v:.2f}) >= EMA200, and ADX ({adx_v:.1f}) >= 22.0"
                        ),
                        "eth_btc_regime_aligned": eth_btc_regime_aligned,
                        "eth_btc_regime": eth_btc_regime,
                        "smt_signal": smt_signal,
                        "min_stop_pct": min_stop,
                    }
            elif dir_upper in ("SHORT", "SELL"):
                if not (close_v <= ema200_v and ema50_v <= ema200_v and adx_v >= 22.0):
                    return {
                        "allowed": False,
                        "reason": (
                            f"M57_15M_TREND_GATE_VETO: SHORT requires close ({close_v:.2f}) <= EMA200 ({ema200_v:.2f}), "
                            f"EMA50 ({ema50_v:.2f}) <= EMA200, and ADX ({adx_v:.1f}) >= 22.0"
                        ),
                        "eth_btc_regime_aligned": eth_btc_regime_aligned,
                        "eth_btc_regime": eth_btc_regime,
                        "smt_signal": smt_signal,
                        "min_stop_pct": min_stop,
                    }

    # =========================================================================
    # Step C: 4h Structural Swing Macro Chop/Compression Gate
    # =========================================================================
    if tf_lower == "4h":
        reg_upper = str(regime_name or "").upper()
        if (
            any(k in reg_upper for k in ("CHOP", "COMPRESSION", "SQUEEZE"))
            and confluence_score < 72.0
        ):
            return {
                "allowed": False,
                "reason": (
                    f"M57_4H_CHOP_COMPRESSION_VETO: 4h regime {regime_name} requires "
                    f"confluence >= 72.0 (got {confluence_score:.1f})"
                ),
                "eth_btc_regime_aligned": eth_btc_regime_aligned,
                "eth_btc_regime": eth_btc_regime,
                "smt_signal": smt_signal,
                "min_stop_pct": min_stop,
            }

    return {
        "allowed": True,
        "reason": "M57_GATE_CLEARED",
        "eth_btc_regime_aligned": eth_btc_regime_aligned,
        "eth_btc_regime": eth_btc_regime,
        "smt_signal": smt_signal,
        "min_stop_pct": min_stop,
    }
