"""
3-Way Ablation Benchmark Engine for SKY × Kronos.
Evaluates:
  Mode A: SKY Baseline (12-Layer Empirical Alpha & SMC)
  Mode B: Kronos Standalone (Autoregressive Path Predictor)
  Mode C: SKY + Kronos Fusion (Empirical + Neural Evidence)
Computes delta expectancy, profit factor, win rate, and drawdown.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import numpy as np

from core.models.kronos.adapter import KronosModelAdapter, kronos_adapter
from core.models.kronos.schemas import KronosAblationMode, KronosConfig
from core.sky_intelligence.expectancy_engine import expectancy_engine
from core.institutional_alpha import institutional_alpha_engine

logger = logging.getLogger("ai_quant_sentinel.kronos.ablation")


@dataclass
class AblationMetrics:
    mode: str
    total_trades: int
    win_rate_pct: float
    profit_factor: float
    expectancy_r: float
    max_drawdown_pct: float
    sharpe_ratio: float
    directional_accuracy_pct: float


@dataclass
class AblationBenchmarkResult:
    symbol: str
    timeframe: str
    evaluation_bars: int
    mode_a_sky: AblationMetrics
    mode_b_kronos: AblationMetrics
    mode_c_fusion: AblationMetrics
    delta_expectancy_r: float
    delta_win_rate_pct: float
    delta_profit_factor: float
    delta_drawdown_pct: float
    verdict: str  # "KRONOS_CREATES_ALPHA", "KRONOS_NEUTRAL", "KRONOS_DETRIMENTAL"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "evaluation_bars": self.evaluation_bars,
            "modes": {
                "mode_a_sky": self.mode_a_sky.__dict__,
                "mode_b_kronos": self.mode_b_kronos.__dict__,
                "mode_c_fusion": self.mode_c_fusion.__dict__,
            },
            "deltas": {
                "delta_expectancy_r": round(self.delta_expectancy_r, 3),
                "delta_win_rate_pct": round(self.delta_win_rate_pct, 2),
                "delta_profit_factor": round(self.delta_profit_factor, 2),
                "delta_drawdown_pct": round(self.delta_drawdown_pct, 2),
            },
            "verdict": self.verdict,
        }


class KronosAblationBenchmark:
    """Executes chronological out-of-sample 3-way ablation testing."""

    def __init__(self, adapter: Optional[KronosModelAdapter] = None):
        self.adapter = adapter or kronos_adapter

    def run_benchmark(
        self,
        symbol: str,
        timeframe: str,
        candles: List[Dict[str, Any]],
        lookback_window: int = 64,
        forecast_horizon: int = 12,
        step_size: int = 12,
    ) -> AblationBenchmarkResult:
        if len(candles) < lookback_window + forecast_horizon + 20:
            raise ValueError(f"Insufficient candles for ablation benchmark (min {lookback_window + forecast_horizon + 20}).")

        trades_a: List[float] = []
        trades_b: List[float] = []
        trades_c: List[float] = []

        da_hits_a: int = 0
        da_hits_b: int = 0
        da_hits_c: int = 0
        total_eval_points: int = 0

        # Walk-forward evaluation loop
        start_idx = lookback_window
        end_idx = len(candles) - forecast_horizon

        for idx in range(start_idx, end_idx, step_size):
            history = candles[:idx]
            current_bar = history[-1]
            cur_price = float(current_bar["close"])

            future_window = candles[idx : idx + forecast_horizon]
            realized_exit = float(future_window[-1]["close"])
            realized_return = (realized_exit - cur_price) / cur_price
            realized_dir = 1 if realized_return > 0 else -1

            # Mode A: SKY Baseline Signal
            sky_res = institutional_alpha_engine.evaluate_alpha(
                symbol=symbol, timeframe=timeframe, candles=history
            )
            if sky_res.decision == "LONG":
                sky_signal = 1
            elif sky_res.decision == "SHORT":
                sky_signal = -1
            else:
                sky_signal = 0

            # Mode B: Kronos Standalone Signal
            k_forecast = self.adapter.predict(
                symbol=symbol,
                timeframe=timeframe,
                candles=history,
                horizon=forecast_horizon,
                lookback=lookback_window,
                sample_count=5,
            )
            k_signal = 1 if k_forecast.directional_bias == "BULLISH" else (-1 if k_forecast.directional_bias == "BEARISH" else 0)

            # Mode C: Fusion Signal (SKY signal confirmed by Kronos consensus)
            fusion_signal = 0
            if sky_signal == 1 and k_signal == 1 and k_forecast.model_uncertainty < 0.60:
                fusion_signal = 1
            elif sky_signal == -1 and k_signal == -1 and k_forecast.model_uncertainty < 0.60:
                fusion_signal = -1

            total_eval_points += 1

            # Tracking Directional Accuracy
            if sky_signal != 0 and sky_signal == realized_dir:
                da_hits_a += 1
            if k_signal != 0 and k_signal == realized_dir:
                da_hits_b += 1
            if fusion_signal != 0 and fusion_signal == realized_dir:
                da_hits_c += 1

            # Tracking Simulated Trades (net of 0.04% fee + 1.5 bps slippage = 0.055% round-trip)
            friction = 0.00055
            if sky_signal != 0:
                pnl_a = (realized_return * sky_signal) - friction
                trades_a.append(pnl_a)

            if k_signal != 0:
                pnl_b = (realized_return * k_signal) - friction
                trades_b.append(pnl_b)

            if fusion_signal != 0:
                pnl_c = (realized_return * fusion_signal) - friction
                trades_c.append(pnl_c)

        m_a = self._compute_metrics("MODE_A_SKY", trades_a, da_hits_a, total_eval_points)
        m_b = self._compute_metrics("MODE_B_KRONOS", trades_b, da_hits_b, total_eval_points)
        m_c = self._compute_metrics("MODE_C_FUSION", trades_c, da_hits_c, total_eval_points)

        delta_exp = m_c.expectancy_r - m_a.expectancy_r
        delta_wr = m_c.win_rate_pct - m_a.win_rate_pct
        delta_pf = m_c.profit_factor - m_a.profit_factor
        delta_dd = m_c.max_drawdown_pct - m_a.max_drawdown_pct

        if delta_exp > 0.05 and delta_pf >= 0:
            verdict = "KRONOS_CREATES_ALPHA"
        elif delta_exp < -0.05:
            verdict = "KRONOS_DETRIMENTAL"
        else:
            verdict = "KRONOS_NEUTRAL"

        return AblationBenchmarkResult(
            symbol=symbol,
            timeframe=timeframe,
            evaluation_bars=total_eval_points,
            mode_a_sky=m_a,
            mode_b_kronos=m_b,
            mode_c_fusion=m_c,
            delta_expectancy_r=delta_exp,
            delta_win_rate_pct=delta_wr,
            delta_profit_factor=delta_pf,
            delta_drawdown_pct=delta_dd,
            verdict=verdict,
        )

    def _compute_metrics(
        self, mode_name: str, trades: List[float], da_hits: int, total_evals: int
    ) -> AblationMetrics:
        if not trades:
            return AblationMetrics(
                mode=mode_name,
                total_trades=0,
                win_rate_pct=0.0,
                profit_factor=0.0,
                expectancy_r=0.0,
                max_drawdown_pct=0.0,
                sharpe_ratio=0.0,
                directional_accuracy_pct=round((da_hits / max(1, total_evals)) * 100.0, 2),
            )

        wins = [t for t in trades if t > 0]
        losses = [t for t in trades if t <= 0]
        win_rate = len(wins) / len(trades)

        gross_win = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 1e-8
        profit_factor = gross_win / gross_loss

        mean_return = float(np.mean(trades))
        std_return = float(np.std(trades)) if len(trades) > 1 else 0.01
        sharpe = (mean_return / (std_return + 1e-8)) * np.sqrt(252 * 24)

        # Expectancy in R (where 1R = average loss)
        avg_loss = float(np.mean(np.abs(losses))) if losses else 0.01
        expectancy_r = mean_return / max(0.001, avg_loss)

        # Max Drawdown
        cum_equity = np.cumprod(1.0 + np.array(trades))
        peak = np.maximum.accumulate(cum_equity)
        drawdowns = (peak - cum_equity) / peak
        max_dd = float(np.max(drawdowns)) * 100.0 if len(drawdowns) > 0 else 0.0

        return AblationMetrics(
            mode=mode_name,
            total_trades=len(trades),
            win_rate_pct=round(win_rate * 100.0, 2),
            profit_factor=round(profit_factor, 2),
            expectancy_r=round(expectancy_r, 3),
            max_drawdown_pct=round(max_dd, 2),
            sharpe_ratio=round(sharpe, 2),
            directional_accuracy_pct=round((da_hits / max(1, total_evals)) * 100.0, 2),
        )


kronos_ablation_benchmark = KronosAblationBenchmark()
