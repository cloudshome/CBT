"""
Continuous Background Empirical Accumulator & Walk-Forward Statistical Validator.
Systematically runs chronological walk-forward evaluations on incoming and historical candles,
accumulating validated R-multiple distributions into SQLite experiments.db until statistical
significance thresholds (N >= 100 trades per regime) are empirically satisfied.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.data_streamer import data_streamer
from core.sky_intelligence.expectancy_engine import expectancy_engine
from core.regime_transition import regime_transition_detector
from core.sandbox_lab import sandbox_lab

logger = logging.getLogger("ai_quant_sentinel.empirical_accumulator")


@dataclass
class RegimeValidationStatus:
    regime: str
    total_samples: int
    target_samples: int
    win_rate: float
    expectancy_r: float
    is_statistically_validated: bool
    status_label: str  # "VALIDATED" or "INSUFFICIENT DATA"


@dataclass
class EmpiricalAccumulatorReport:
    total_samples_collected: int
    validation_target_per_regime: int
    regimes: Dict[str, RegimeValidationStatus]
    last_run_timestamp: int
    active_symbols: List[str]


class EmpiricalAccumulator:
    """Manages continuous statistical evidence accumulation for institutional strategies."""

    SUPPORTED_REGIMES = [
        "TRENDING_BULL",
        "TRENDING_BEAR",
        "RANGING_COMPRESSION",
        "HIGH_VOLATILITY_EXPANSION",
    ]

    def __init__(self, db_path: Optional[Path] = None, target_samples: int = 100):
        self.db_path = db_path or Path("data/db/experiments.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.target_samples = target_samples
        self._init_db()

    def _init_db(self):
        """Initializes the empirical trade samples SQLite table."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS empirical_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    concept TEXT NOT NULL,
                    r_multiple REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    entry_time INTEGER NOT NULL,
                    exit_time INTEGER NOT NULL,
                    pnl_usd REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_regime_concept ON empirical_samples(regime, concept)")
            conn.commit()

    def store_sample(
        self,
        symbol: str,
        timeframe: str,
        regime: str,
        concept: str,
        r_multiple: float,
        entry_price: float,
        exit_price: float,
        entry_time: int,
        exit_time: int,
        pnl_usd: float,
    ) -> None:
        """Stores a validated out-of-sample empirical trade."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO empirical_samples 
                (symbol, timeframe, regime, concept, r_multiple, entry_price, exit_price, entry_time, exit_time, pnl_usd)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (symbol, timeframe, regime, concept, r_multiple, entry_price, exit_price, entry_time, exit_time, pnl_usd),
            )
            conn.commit()

    def get_samples_for_regime(self, regime: str, concept: str = "SETUP_A_SWEEP_MSS") -> List[float]:
        """Retrieves accumulated R-multiples for a specific regime and concept."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT r_multiple FROM empirical_samples WHERE regime = ? AND concept = ?",
                (regime, concept),
            )
            rows = cursor.fetchall()
            return [r[0] for r in rows]

    def run_accumulation_cycle(self, symbols: Optional[List[str]] = None) -> int:
        """
        Executes one historical backtest accumulation cycle across symbols and timeframes.
        Returns the number of new samples recorded.
        """
        target_symbols = symbols or ["BTC/USDT", "ETH/USDT", "PAXG/USDT"]
        timeframes = ["15m", "1h"]
        new_samples = 0

        for sym in target_symbols:
            for tf in timeframes:
                try:
                    candles = data_streamer.get_candles(sym, tf, limit=300)
                    if len(candles) < 30:
                        continue

                    # Classify regime
                    reg_res = regime_transition_detector.classify_regime(candles)
                    regime_str = reg_res.current_regime.value if hasattr(reg_res, "current_regime") else "TRENDING_BULL"

                    # Run walk-forward backtest
                    bt_report = sandbox_lab.run_backtest(sym, tf, candles)
                    for trade in bt_report.trades:
                        self.store_sample(
                            symbol=sym,
                            timeframe=tf,
                            regime=regime_str,
                            concept="SETUP_A_SWEEP_MSS",
                            r_multiple=trade.r_multiple,
                            entry_price=trade.entry_price,
                            exit_price=trade.exit_price,
                            entry_time=trade.entry_time,
                            exit_time=trade.exit_time,
                            pnl_usd=trade.pnl_usd,
                        )
                        new_samples += 1
                except Exception as e:
                    logger.debug(f"Accumulation cycle error on {sym} {tf}: {e}")

        logger.info(f"Empirical accumulator cycle complete. {new_samples} new trade samples recorded.")
        return new_samples

    def get_status_report(self, concept: str = "SETUP_A_SWEEP_MSS") -> EmpiricalAccumulatorReport:
        """Returns the full statistical validation status across all market regimes."""
        import time
        regimes_status = {}
        total_all_samples = 0

        for r_name in self.SUPPORTED_REGIMES:
            r_series = self.get_samples_for_regime(r_name, concept)
            count = len(r_series)
            total_all_samples += count

            if count > 0:
                stats = expectancy_engine.compute_expectancy(r_series, concept_name=concept, regime=r_name)
                wr = round(float(stats.win_rate), 2)
                exp = round(float(stats.expectancy_r), 2)
            else:
                wr = 0.0
                exp = 0.0

            is_valid = count >= self.target_samples
            regimes_status[r_name] = RegimeValidationStatus(
                regime=r_name,
                total_samples=count,
                target_samples=self.target_samples,
                win_rate=wr,
                expectancy_r=exp,
                is_statistically_validated=is_valid,
                status_label="VALIDATED" if is_valid else "INSUFFICIENT DATA",
            )

        return EmpiricalAccumulatorReport(
            total_samples_collected=total_all_samples,
            validation_target_per_regime=self.target_samples,
            regimes=regimes_status,
            last_run_timestamp=int(time.time() * 1000),
            active_symbols=["BTC/USDT", "ETH/USDT", "PAXG/USDT"],
        )


# Singleton
empirical_accumulator = EmpiricalAccumulator()
