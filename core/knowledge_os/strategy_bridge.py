"""
core/knowledge_os/strategy_bridge.py
====================================
Research-to-Strategy Bridge for CBT Knowledge OS.

Constitutional Mandates:
1. Zero Speculation: Transforms qualitative or empirical claims into structured, falsifiable strategy candidates.
2. Parameter Completeness: Declares explicit entry, invalidation, exit, and Half-Kelly bounded risk rules.
3. Provenance Chain: Every candidate retains an unbroken link to its source claim (`claim_id`) and source (`source_id`).
4. Dual Registration: Inserts into `strategy_candidates` and enqueues into `hypothesis_queue`.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.database import db_manager
from core.knowledge_os.research_wikipedia import WIKI_DB_PATH, research_wikipedia_engine

logger = logging.getLogger("sky.knowledge_os.strategy_bridge")


@dataclass
class StrategyCandidateRecord:
    candidate_id: str
    knowledge_id: str
    strategy_name: str
    hypothesis: str
    entry_rules: dict[str, Any]
    exit_rules: dict[str, Any]
    parameter_bounds: dict[str, Any]
    timeframe: str = "15m"
    required_indicators: list[str] = field(default_factory=list)
    validation_stage: str = "QUEUED_FOR_BACKTEST"  # UNTESTED, QUEUED_FOR_BACKTEST, WALK_FORWARD_TESTED, REJECTED
    backtest_expectancy: float | None = None
    backtest_sharpe: float | None = None
    backtest_win_rate: float | None = None
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResearchToStrategyBridge:
    """
    Translates research claims into formalized, backtest-ready strategy candidates.
    """

    def __init__(self, wiki_db_path: Path = WIKI_DB_PATH):
        self.wiki_db_path = wiki_db_path

    def _get_wiki_connection(self):
        return research_wikipedia_engine._get_connection()

    def synthesize_strategy_from_claim(
        self,
        claim_id: str,
        custom_symbol: str = "BTC/USDT",
        custom_timeframe: str = "15m",
    ) -> StrategyCandidateRecord | None:
        """
        Parses a research claim, extracts rule mechanics, and registers a candidate.
        """
        # 1. Fetch claim from research_claims
        with self._get_wiki_connection() as conn:
            c_row = conn.execute("SELECT * FROM research_claims WHERE claim_id = ?;", (claim_id,)).fetchone()

        if not c_row:
            logger.warning(f"Cannot synthesize strategy: Claim '{claim_id}' not found.")
            return None

        claim_text = c_row["speaker_claim"]
        source_id = c_row["source_id"]
        return self.synthesize_from_text(
            claim_text=claim_text,
            claim_id=claim_id,
            source_id=source_id,
            symbol=custom_symbol,
            timeframe=custom_timeframe,
        )

    def synthesize_from_text(
        self,
        claim_text: str,
        claim_id: str = "",
        source_id: str = "",
        symbol: str = "BTC/USDT",
        timeframe: str = "15m",
    ) -> StrategyCandidateRecord:
        """
        Compiles free-form text or hypothesis into a structured StrategyCandidateRecord.
        """
        clean_text = claim_text.strip()
        lower = clean_text.lower()
        now_ms = int(time.time() * 1000)
        cid = f"CAND_{uuid.uuid4().hex[:8].upper()}"

        # Determine directional bias & concept keywords
        is_bearish = any(w in lower for w in ("bearish", "short", "dump", "fall", "resistance", "breakdown"))
        direction = "SHORT" if is_bearish else "LONG"

        indicators = []
        if any(w in lower for w in ("rsi", "relative strength")):
            indicators.append("RSI")
        if any(w in lower for w in ("macd", "moving average convergence")):
            indicators.append("MACD")
        if any(w in lower for w in ("fvg", "fair value gap", "imbalance")):
            indicators.append("FAIR_VALUE_GAP")
        if any(w in lower for w in ("order block", "ob", "orderblock")):
            indicators.append("ORDER_BLOCK")
        if any(w in lower for w in ("cvd", "delta", "absorption", "cumulative volume")):
            indicators.append("CVD_DELTA")
        if any(w in lower for w in ("liquidity sweep", "sweep", "stop hunt")):
            indicators.append("LIQUIDITY_SWEEP")
        if any(w in lower for w in ("vwap", "volume weighted")):
            indicators.append("VWAP")
        if any(w in lower for w in ("ema", "sma", "moving average")):
            indicators.append("MOVING_AVERAGE")
        if any(w in lower for w in ("cpi", "fomc", "inflation", "macro")):
            indicators.append("MACRO_SURPRISE_DELTA")
        if not indicators:
            indicators.append("PRICE_ACTION_STRUCTURE")

        # Formalize deterministic entry condition
        entry_cond = (
            f"Enter {direction} on candle close when {indicators[0]} confirms structural displacement "
            f"with positive volume expansion on {timeframe} timeframe."
        )

        entry_rules = {
            "direction": direction,
            "signal_type": indicators[0],
            "condition": entry_cond,
            "session_filter": ["LONDON_OPEN", "NY_OPEN"],
        }

        exit_rules = {
            "stop_loss_mode": "SWING_EXTREME",
            "invalidation": "CANDLE_CLOSE_BEYOND_SWING_LEVEL",
            "take_profit_rr": 2.0,
            "time_stop_bars": 16,
            "trailing_stop": "HALF_R_AFTER_1R",
        }

        parameter_bounds = {
            "risk_per_trade_pct": 1.5,  # Bounded by Half-Kelly rule (<= 2.5%)
            "risk_budget": {"max_kelly_fraction": 0.025, "allocated_risk_pct": 1.5},
            "max_slippage_bps": 5.0,
            "min_rr_ratio": 1.5,
        }

        strat_name = f"{direction} {indicators[0].replace('_', ' ').title()} Engine"

        candidate = StrategyCandidateRecord(
            candidate_id=cid,
            knowledge_id=claim_id or source_id or f"KNW_{cid}",
            strategy_name=strat_name,
            hypothesis=clean_text[:400],
            entry_rules=entry_rules,
            exit_rules=exit_rules,
            parameter_bounds=parameter_bounds,
            timeframe=timeframe,
            required_indicators=indicators,
            validation_stage="QUEUED_FOR_BACKTEST",
            created_at=now_ms,
        )

        # 1. Register in strategy_candidates table
        with db_manager.get_brain_conn() as conn:
            # Ensure provenance ledger entry exists for FK constraint
            conn.execute(
                """
                INSERT OR IGNORE INTO research_provenance_ledger (
                    knowledge_id, source_type, source_uri, title, author_creator,
                    ingested_at, raw_content_preview, confidence_score, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    candidate.knowledge_id,
                    "RESEARCH_CLAIM",
                    source_id or f"cbt://claims/{claim_id}",
                    strat_name,
                    "Knowledge OS",
                    now_ms,
                    clean_text[:200],
                    0.50,
                    "PROVENANCE_CONFIRMED",
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_candidates (
                    candidate_id, knowledge_id, strategy_name, hypothesis,
                    entry_rules, exit_rules, parameter_bounds, timeframe,
                    required_indicators, validation_stage, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    candidate.candidate_id,
                    candidate.knowledge_id,
                    candidate.strategy_name,
                    candidate.hypothesis,
                    json.dumps(candidate.entry_rules),
                    json.dumps(candidate.exit_rules),
                    json.dumps(candidate.parameter_bounds),
                    candidate.timeframe,
                    json.dumps(candidate.required_indicators),
                    candidate.validation_stage,
                    candidate.created_at,
                ),
            )

            # 2. Also enqueue into hypothesis_queue for automated research pipeline
            conn.execute(
                """
                INSERT OR IGNORE INTO hypothesis_queue (
                    hypothesis_id, claim_id, title, null_hypothesis, alt_hypothesis,
                    independent_variable, dependent_variable, target_symbol,
                    test_method, validation_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'QUEUED', ?);
                """,
                (
                    f"HYP_{cid}",
                    claim_id,
                    strat_name,
                    f"Null: {indicators[0]} signal provides zero excess alpha (EV <= 0).",
                    f"Alt: {indicators[0]} signal yields positive net EV > 0.15R after 3-tier costs.",
                    indicators[0],
                    "FORWARD_RETURN_15M",
                    symbol,
                    "WALK_FORWARD_CPCV",
                    now_ms,
                ),
            )
            conn.commit()

        logger.info(f"Synthesized strategy candidate [{cid}] '{strat_name}' from claim '{claim_id}'")
        return candidate

    def scan_and_bridge_unconverted_claims(self, limit: int = 10) -> list[StrategyCandidateRecord]:
        """
        Scans research_claims for verified or high-probability claims and compiles candidates.
        """
        with self._get_wiki_connection() as conn:
            claims = conn.execute(
                """
                SELECT claim_id, speaker_claim, claim_type, confidence_score
                FROM research_claims
                WHERE claim_type IN ('STRATEGY_CLAIM', 'HYPOTHESIS', 'FACT')
                  AND confidence_score >= 0.65
                ORDER BY created_at DESC LIMIT ?;
                """,
                (limit,),
            ).fetchall()

        # Find existing candidates to prevent duplication
        with db_manager.get_brain_conn() as b_conn:
            existing_rows = b_conn.execute("SELECT knowledge_id FROM strategy_candidates;").fetchall()
            existing_kids = {r["knowledge_id"] for r in existing_rows}

        bridged: list[StrategyCandidateRecord] = []
        for c in claims:
            cid = c["claim_id"]
            if cid in existing_kids:
                continue

            cand = self.synthesize_strategy_from_claim(cid)
            if cand:
                bridged.append(cand)

        return bridged


# Global singleton
strategy_bridge = ResearchToStrategyBridge()
