"""
core/intelligence/lesson_health.py
==================================
Senior Quantitative Systems Architecture — Lesson Health & Empirical Decay Engine.

Core Mandate:
Prevents obsolete, decaying, or regime-inconsistent research lessons from lingering
indefinitely in the knowledge base.

Mathematical Model:
Health Score H in [0.0, 1.0] = w_e * E_norm + w_w * WR + w_s * S_factor - D_penalty
where:
- E_norm: Normalized realized net expectancy (clamped in [0, 1])
- WR: Realized win rate in [0, 1]
- S_factor: Sample size statistical power factor = min(1.0, sqrt(N) / sqrt(100))
- D_penalty: Penalty for observed max adverse drawdown excursion

Decay Status:
- H >= 0.65 and Expectancy > 0: HEALTHY_ACTIVE
- 0.35 <= H < 0.65: MONITORED_DEGRADING
- H < 0.35 or Expectancy <= 0: AUTO_ARCHIVED (Prevented from influencing future hypotheses)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("ai_quant_sentinel.intelligence.lesson_health")

REAL_CAPITAL_ENABLED: bool = False


class LessonHealthStatus(str, Enum):
    HEALTHY_ACTIVE = "HEALTHY_ACTIVE"
    MONITORED_DEGRADING = "MONITORED_DEGRADING"
    AUTO_ARCHIVED = "AUTO_ARCHIVED"


@dataclass
class QuantitativeResearchLesson:
    """A research lesson stored in the Knowledge OS with empirical performance attribution."""

    lesson_id: str
    hypothesis_text: str
    target_regime: str
    sample_size_n: int
    expectancy_r: float
    win_rate: float
    max_drawdown_r: float
    consecutive_losses: int = 0
    days_active: float = 0.0
    status: LessonHealthStatus = LessonHealthStatus.HEALTHY_ACTIVE
    health_score: float = 1.0
    real_capital_enabled: bool = False


class LessonHealthEngine:
    """
    Evaluates and decays stored research lessons based on empirical out-of-sample evidence.
    """

    MIN_ACTIVE_HEALTH: float = 0.65
    ARCHIVE_HEALTH_THRESHOLD: float = 0.35

    def __init__(self, target_sample_power: int = 100) -> None:
        self.target_sample_power = target_sample_power
        self.real_capital_enabled: bool = False

    def compute_health_score(
        self,
        expectancy_r: float,
        win_rate: float,
        sample_size_n: int,
        max_drawdown_r: float,
    ) -> float:
        """
        Computes composite empirical health score in [0.0, 1.0].
        """
        if sample_size_n <= 0:
            return 0.0

        # Sample size power factor: sqrt(N) / sqrt(target_sample_power)
        s_factor = min(1.0, math.sqrt(sample_size_n) / math.sqrt(self.target_sample_power))

        # Normalized expectancy: map [-1.0R, 1.0R] to [0.0, 1.0]
        # Positive expectancy maps to >= 0.5
        e_norm = max(0.0, min(1.0, (expectancy_r + 1.0) / 2.0))

        # Win rate in [0, 1]
        wr_norm = max(0.0, min(1.0, win_rate))

        # Drawdown penalty: If drawdown exceeds -3.0R, penalize health
        dd_penalty = 0.0
        if max_drawdown_r < -2.0:
            dd_penalty = min(0.3, abs(max_drawdown_r + 2.0) * 0.1)

        raw_health = (0.45 * e_norm) + (0.35 * wr_norm) + (0.20 * s_factor) - dd_penalty
        return max(0.0, min(1.0, raw_health))

    def evaluate_lesson_health(
        self,
        lesson: QuantitativeResearchLesson,
        current_market_regime: str | None = None,
    ) -> QuantitativeResearchLesson:
        """
        Updates the health score and lifecycle status of a research lesson.
        """
        # If expectancy is strictly negative, lesson is dead regardless of sample size
        if lesson.expectancy_r <= 0.0 and lesson.sample_size_n >= 20:
            lesson.health_score = 0.0
            lesson.status = LessonHealthStatus.AUTO_ARCHIVED
            logger.info("Lesson %s AUTO_ARCHIVED due to negative expectancy (E=%.2fR)", lesson.lesson_id, lesson.expectancy_r)
            return lesson

        health = self.compute_health_score(
            expectancy_r=lesson.expectancy_r,
            win_rate=lesson.win_rate,
            sample_size_n=lesson.sample_size_n,
            max_drawdown_r=lesson.max_drawdown_r,
        )

        # Regime mismatch penalty: If evaluated in a different regime, apply 15% discount
        if current_market_regime and lesson.target_regime != "ALL":
            if current_market_regime != lesson.target_regime:
                health *= 0.85

        lesson.health_score = round(health, 4)

        if lesson.health_score >= self.MIN_ACTIVE_HEALTH:
            lesson.status = LessonHealthStatus.HEALTHY_ACTIVE
        elif lesson.health_score >= self.ARCHIVE_HEALTH_THRESHOLD:
            lesson.status = LessonHealthStatus.MONITORED_DEGRADING
            logger.warning(
                "Lesson %s DEGRADED to MONITORED_DEGRADING (Health=%.2f)",
                lesson.lesson_id,
                lesson.health_score,
            )
        else:
            lesson.status = LessonHealthStatus.AUTO_ARCHIVED
            logger.warning(
                "Lesson %s AUTO_ARCHIVED due to low health score (Health=%.2f)",
                lesson.lesson_id,
                lesson.health_score,
            )

        return lesson
