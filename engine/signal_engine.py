"""engine/signal_engine.py

Orchestrator: OHLCV -> indicators -> market structure -> features -> scores ->
multi-condition plans -> final JSON signal (single best + plan list).

Produces exactly the structured output format requested:

    {
      "signal_id": "BTC_20260804_1452",
      "timestamp": 1722779520000,
      "asset": "BTCUSDT",
      "action": "BUY",
      "entry": 61250.00,
      "stop_loss": 60700.00,
      "take_profit": 62200.00,
      "risk_reward": 2.1,
      "confidence": "HIGH",
      "timeframe": "15m",
      "reason": "Bullish divergence on RSI + volume spike above VWAP",
      "plans": [ ...multi-condition plans... ]
    }
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import pandas as pd

from data.symbols import normalize_symbol

from .features import build_snapshot
from .indicators import add_all_indicators, find_rsi_divergence
from .regime import classify_market_regime
from .rules import Plan, build_plans
from .scorer import ScoreBreakdown, score_bearish, score_bullish, score_neutral
from .structure import analyze_structure


@dataclass
class BrainOutput:
    features: dict = field(default_factory=dict)
    structure: dict = field(default_factory=dict)
    bull_score: ScoreBreakdown = None
    bear_score: ScoreBreakdown = None
    best_signal: dict = field(default_factory=dict)
    plans: list = field(default_factory=list)

    def as_json(self) -> dict:
        return {
            "signal": self.best_signal,
            "plans": self.plans,
            "snapshot": {
                "features": self.features,
                "structure": self.structure,
                "scores": {
                    "bull": self.bull_score.as_dict() if self.bull_score else {},
                    "bear": self.bear_score.as_dict() if self.bear_score else {},
                },
            },
        }


# ── Windowed-analysis constants (P13.4) ─────────────────────────────────
# These MUST stay in lockstep with the default lookbacks used by the
# windowed detectors so the fast walk is behaviour-identical to calling
# analyze_frame on each prefix:
#   analyze_structure(df, lookback=200)   -> last 200 rows
#   find_rsi_divergence(df, lookback=80)  -> last 80 rows
#   classify_market_regime(df, ...)       -> reads tail(15) but refuses
#                                            frames shorter than 20 rows
STRUCTURE_LOOKBACK = 200
DIVERGENCE_LOOKBACK = 80
REGIME_TAIL = 15
REGIME_MIN_ROWS = 20


def _signal_id(symbol: str, ts_ms: int) -> str:
    return f"{symbol.replace('/', '')}_{time.strftime('%Y%m%d_%H%M', time.localtime(ts_ms / 1000))}"


def _reason(
    features: dict, side: str, bull: ScoreBreakdown, bear: ScoreBreakdown
) -> str:
    parts = []
    if side == "BUY":
        if (features.get("rsi_divergence") or {}).get("bull"):
            parts.append("Bullish divergence on RSI")
        if features.get("volume_spike"):
            parts.append("volume spike")
        if features.get("above_vwap"):
            parts.append("price above VWAP")
        if features.get("event_kind") in ("bos_up", "choch_up"):
            parts.append(features["event_kind"].replace("_", " ").upper())
        parts += [r for r in bull.fired if r not in parts]
    else:
        if (features.get("rsi_divergence") or {}).get("bear"):
            parts.append("Bearish divergence on RSI")
        if features.get("volume_spike"):
            parts.append("volume spike")
        if features.get("above_vwap") is False:
            parts.append("price below VWAP")
        if features.get("event_kind") in ("bos_down", "choch_down"):
            parts.append(features["event_kind"].replace("_", " ").upper())
        parts += [r for r in bear.fired if r not in parts]
    if not parts:
        parts.append("No dominant edge — see plans for conditional setups")
    return " + ".join(parts[:6])


def build_best_signal(
    features: dict,
    bull: ScoreBreakdown,
    bear: ScoreBreakdown,
    plans: list[Plan],
    symbol: str,
    timeframe: str,
    min_confidence: int,
) -> dict:
    """Emit the single best actionable signal (or NO TRADE) in the requested
    schema, with entry/SL/TP taken from the top PRIMARY plan when available.

    Decision A1: only plans inside the chosen primary setup family may become
    the best signal; everything else is a research watch-item.
    """
    now_ms = int(time.time() * 1000)
    price = features.get("price") or 0.0
    primary = [p for p in plans if p.primary]
    top = (primary or plans)[0] if (primary or plans) else None

    if top and top.confidence_pct >= min_confidence:
        action = top.action
        entry = top.entry or price
        sl = top.stop_loss
        tp = top.take_profits[0] if top.take_profits else None
        rr = top.risk_reward
        conf_label = top.confidence_label
        reason = _reason(features, action, bull, bear)
        signal_type = "SIGNAL"
    else:
        action = "NO TRADE"
        entry, sl, tp, rr, conf_label = None, None, None, 0.0, "LOW"
        reason = _reason(features, "NEUTRAL", bull, bear)
        signal_type = "MONITOR"

    return {
        "signal_id": _signal_id(symbol, now_ms),
        "timestamp": now_ms,
        "asset": symbol,
        "action": action,
        "entry": round(entry, 2) if entry else None,
        "stop_loss": round(sl, 2) if sl else None,
        "take_profit": round(tp, 2) if tp else None,
        "risk_reward": round(rr, 2),
        "confidence": conf_label,
        "timeframe": timeframe,
        "reason": reason,
        "signal_type": signal_type,
        "note": (
            "NO TRADE: scores below threshold. Read the 'plans' array for "
            "conditional setups to wait for."
            if signal_type == "MONITOR"
            else "Risk advice only — not financial advice. Use stop-losses."
        ),
    }


def analyze_frame(
    df: pd.DataFrame,
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
    min_confidence: int = 55,
    default_rr: float = 2.0,
    calibration: dict | None = None,
    primary_types: set | None = None,
    tp_rr_by_type: dict | None = None,
) -> BrainOutput:
    """Run the full brain on one OHLCV frame.

    `calibration` is the optional self-improvement profile (plan_type ->
    multiplier / filtered) produced by brain.calibrator; None keeps behaviour
    identical to an uncalibrated engine.  Profiles may be regime-keyed
    (``plan_type::regime``).

    `primary_types` (decision A1) narrows which plans may become the best
    signal.  `tp_rr_by_type` (decision A2) supplies per-setup, data-driven
    take-profit distances in R.
    """
    symbol = normalize_symbol(symbol)
    df = df.copy()
    df.attrs["symbol"] = symbol
    df.attrs["timeframe"] = timeframe

    ind = add_all_indicators(df)
    return _analyze_at(
        ind,
        df,
        len(df) - 1,
        symbol,
        timeframe,
        min_confidence=min_confidence,
        default_rr=default_rr,
        calibration=calibration,
        primary_types=primary_types,
        tp_rr_by_type=tp_rr_by_type,
    )


def analyze_frame_at(
    ind: pd.DataFrame,
    raw: pd.DataFrame,
    i: int,
    symbol: str = "BTCUSDT",
    timeframe: str = "15m",
    min_confidence: int = 55,
    default_rr: float = 2.0,
    calibration: dict | None = None,
    primary_types: set | None = None,
    tp_rr_by_type: dict | None = None,
) -> BrainOutput:
    """Analyse bar ``i`` from precomputed indicators (P13.4 fast walk).

    ``ind`` must be ``add_all_indicators(raw)`` over the FULL frame (all
    rows).  Returns exactly what ``analyze_frame(raw.iloc[:i+1], ...)``
    returns for that bar, but in O(lookback) instead of O(i): structure,
    divergence and regime only ever inspect their fixed tail windows, and
    the snapshot only needs the last two rows plus the prefix length.

    This is what the backtester and simulator walk over; it removes the
    O(N^2) "recompute every indicator from bar 0 at every step" cost while
    keeping the walk behaviour-identical.
    """
    symbol = normalize_symbol(symbol)
    return _analyze_at(
        ind,
        raw,
        i,
        symbol,
        timeframe,
        min_confidence=min_confidence,
        default_rr=default_rr,
        calibration=calibration,
        primary_types=primary_types,
        tp_rr_by_type=tp_rr_by_type,
    )


def _analyze_at(
    ind: pd.DataFrame,
    raw: pd.DataFrame,
    i: int,
    symbol: str,
    timeframe: str,
    min_confidence: int,
    default_rr: float,
    calibration: dict | None,
    primary_types: set | None,
    tp_rr_by_type: dict | None,
) -> BrainOutput:
    """Shared analysis for one bar: the exact analyze_frame pipeline applied
    to bar ``i`` with precomputed indicators.  ``raw`` must be positionally
    indexed (0..N-1) and carry the original OHLCV columns."""
    # Structure: only the last STRUCTURE_LOOKBACK rows matter (the detector
    # windows internally), and every bar <= i is identical to the prefix run.
    tail = raw.iloc[max(0, i - STRUCTURE_LOOKBACK + 1) : i + 1]
    ms = analyze_structure(tail, lookback=STRUCTURE_LOOKBACK)
    # RSI divergence: tail window over the indicator frame (needs rsi + OHLC).
    div = find_rsi_divergence(
        ind.iloc[max(0, i - DIVERGENCE_LOOKBACK + 1) : i + 1],
        lookback=DIVERGENCE_LOOKBACK,
    )
    # Snapshot: last two rows for delta features, prefix length for event age.
    last2 = ind.iloc[max(0, i - 1) : i + 1]
    last2.attrs["symbol"] = symbol
    last2.attrs["timeframe"] = timeframe
    features = build_snapshot(last2, ms, div, ms.equal_levels, frame_len=i + 1)

    # Regime: the classifier reads the last REGIME_TAIL rows but refuses any
    # frame shorter than REGIME_MIN_ROWS, so hand it a window that is exactly
    # the prefix when the prefix is short and exactly 20 rows otherwise — the
    # same rows the prefix call would have seen.
    regime = classify_market_regime(
        raw.iloc[max(0, i - REGIME_MIN_ROWS + 1) : i + 1], features
    )
    features["regime"] = regime
    features["regime_name"] = regime.get("regime", "RANGING")
    features["regime_label"] = regime.get("label", "Ranging / Neutral")
    features["fake_breakout"] = bool(regime.get("fake_breakout"))
    features["trap_detected"] = bool(regime.get("trap_detected"))

    bull = score_bullish(features)
    bear = score_bearish(features)
    if bull.score == 0 and bear.score == 0:
        neutral = score_neutral(features)
        bull, bear = neutral, neutral

    plans = build_plans(
        features,
        bull,
        bear,
        min_confidence=min_confidence,
        default_rr=default_rr,
        calibration=calibration,
        primary_types=primary_types,
        tp_rr_by_type=tp_rr_by_type,
        regime=features.get("regime_name", ""),
    )
    best = build_best_signal(
        features, bull, bear, plans, symbol, timeframe, min_confidence
    )

    return BrainOutput(
        features=features,
        structure=ms.as_dict(),
        bull_score=bull,
        bear_score=bear,
        best_signal=best,
        plans=[p.as_dict() for p in plans],
    )
