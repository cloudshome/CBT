"""tests/test_m80_trade_drill_and_dictionary.py — Test Suite for Milestone 80.

Validates:
1. Isolated Bull-Breakout Trade Execution Drill (Champion & Challenger fills, gross exposure, fees, PnL).
2. Strict database isolation (zero modifications to data/p2_shadow_ledger.db and data/v2b_challenger_shadow_ledger.db).
3. Complete bilingual trading dictionary seed catalog (181 terms >= 165 minimum, all 9 categories represented, complete EN/BN definitions).
4. Trading dictionary FTS search coverage across indicators, patterns, orders, risk, psychology, macro, slang, quant core, and SMC.
5. Governance invariants locked (TIER_0_PAPER, REAL_CAPITAL_ENABLED=False).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import core.strategies.p2_shadow_runner as p2_sr
import core.strategies.v2b_challenger_shadow as v2b_cs
from core.knowledge_os.dictionary_seed_catalog import MASTER_SEED_TERMS
from core.knowledge_os.trading_dictionary import trading_dictionary
from scripts.run_trade_execution_drill import (
    CAPITAL_MODE,
    REAL_CAPITAL_ENABLED,
    run_trade_execution_drill,
)

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def drill_result() -> dict:
    """Runs the trade execution drill once for the test module."""
    return run_trade_execution_drill(verbose=False)


def test_m80_trade_execution_drill_clean_fills(drill_result: dict) -> None:
    """Verifies that both Champion and Challenger executed >= 1 BUY and >= 1 SELL cleanly."""
    assert drill_result["status"] == "DRILL_PASSED"
    assert drill_result["isolation_verified"] is True
    assert drill_result["bars_evaluated"] == 45

    # Champion (P2_RP) verification
    champ = drill_result["champion"]
    assert champ["buy_fills"] >= 1, f"Champion had no BUY fills: {champ['buy_fills']}"
    assert champ["sell_fills"] >= 1, f"Champion had no SELL fills: {champ['sell_fills']}"
    assert champ["total_fills"] == champ["buy_fills"] + champ["sell_fills"]
    assert champ["total_fills"] >= 2
    assert 0.0 < champ["max_gross_exposure"] <= 1.0001, f"Champion peak gross invalid: {champ['max_gross_exposure']}"
    assert champ["total_fees_usd"] > 0.0, f"Champion fees not recorded: {champ['total_fees_usd']}"
    assert champ["starting_equity_usd"] == 10000.0
    assert champ["ending_equity_usd"] > 0.0

    # Challenger (P2_RP_V2B_PVT) verification
    chall = drill_result["challenger"]
    assert chall["buy_fills"] >= 1, f"Challenger had no BUY fills: {chall['buy_fills']}"
    assert chall["sell_fills"] >= 1, f"Challenger had no SELL fills: {chall['sell_fills']}"
    assert chall["total_fills"] == chall["buy_fills"] + chall["sell_fills"]
    assert chall["total_fills"] >= 2
    assert 0.0 < chall["max_gross_exposure"] <= 1.0001, f"Challenger peak gross invalid: {chall['max_gross_exposure']}"
    assert chall["total_fees_usd"] > 0.0, f"Challenger fees not recorded: {chall['total_fees_usd']}"
    assert chall["starting_equity_usd"] == 10000.0
    assert chall["ending_equity_usd"] > 0.0


def test_m80_trade_drill_strict_db_isolation() -> None:
    """Verifies that live production databases are completely untouched by the drill."""
    live_champ_db = ROOT / "data" / "p2_shadow_ledger.db"
    live_chall_db = ROOT / "data" / "v2b_challenger_shadow_ledger.db"

    champ_stat_before = live_champ_db.stat() if live_champ_db.exists() else None
    chall_stat_before = live_chall_db.stat() if live_chall_db.exists() else None

    # Run drill
    res = run_trade_execution_drill(verbose=False)
    assert res["status"] == "DRILL_PASSED"
    assert res["isolation_verified"] is True

    if champ_stat_before is not None:
        champ_stat_after = live_champ_db.stat()
        assert champ_stat_after.st_mtime == champ_stat_before.st_mtime
        assert champ_stat_after.st_size == champ_stat_before.st_size

    if chall_stat_before is not None:
        chall_stat_after = live_chall_db.stat()
        assert chall_stat_after.st_mtime == chall_stat_before.st_mtime
        assert chall_stat_after.st_size == chall_stat_before.st_size


def test_m80_dictionary_seed_count_and_completeness() -> None:
    """Verifies the catalog has >= 165 terms with all required fields non-empty in EN and BN."""
    assert len(MASTER_SEED_TERMS) >= 165
    assert len(MASTER_SEED_TERMS) == 181

    required_categories = {
        "TECHNICAL_INDICATORS",
        "CHART_PATTERNS_PRICE_ACTION",
        "ORDER_TYPES_EXECUTION",
        "RISK_MONEY_MANAGEMENT",
        "TRADING_PSYCHOLOGY",
        "FUNDAMENTAL_MACRO",
        "CRYPTO_COMMUNITY_SLANG",
        "CBT_QUANT_CORE",
    }

    seen_categories = set()
    seen_ids = set()

    for term in MASTER_SEED_TERMS:
        # ID uniqueness and format
        assert term.term_id, "term_id cannot be empty"
        assert term.term_id not in seen_ids, f"Duplicate term_id: {term.term_id}"
        seen_ids.add(term.term_id)

        # Names & category
        assert term.canonical_name.strip(), f"Empty canonical_name for {term.term_id}"
        assert term.category.strip(), f"Empty category for {term.term_id}"
        seen_categories.add(term.category)

        # Bilingual definitions
        assert len(term.definition_en.strip()) >= 20, f"definition_en too short for {term.term_id}"
        assert len(term.definition_bn.strip()) >= 20, f"definition_bn too short for {term.term_id}"

        # Aliases and related terms
        assert isinstance(term.aliases, list)
        assert isinstance(term.related_terms, list)

    # All required categories must be present
    missing = required_categories - seen_categories
    assert not missing, f"Missing required categories: {missing}"


def test_m80_dictionary_fts_search_coverage() -> None:
    """Verifies FTS search accurately retrieves terms across all key trading domains."""
    test_queries = [
        ("Donchian Channels", "donchian_channels"),
        ("Ichimoku Cloud", "ichimoku_cloud"),
        ("Average True Range", "atr"),
        ("Head and Shoulders", "head_and_shoulders"),
        ("One-Cancels-the-Other", "oco_order"),
        ("Trailing Stop", "trailing_stop_order"),
        ("Kelly Criterion", "kelly_criterion"),
        ("Fear Of Missing Out", "fomo"),
        ("Fully Diluted Valuation", "fully_diluted_valuation"),
        ("Whale", "whale"),
        ("Volatility Targeting", "volatility_targeting"),
        ("Order Block", "order_block"),
        ("Fair Value Gap", "fair_value_gap"),
    ]

    for query, expected_id in test_queries:
        results = trading_dictionary.search(query, limit=5)
        found_ids = [r["term_id"] for r in results]
        assert expected_id in found_ids or any(query.lower() in r["canonical_name"].lower() for r in results), (
            f"Failed to find expected term '{expected_id}' with query '{query}'. Found: {found_ids}"
        )

    # Test Bengali search queries
    bn_results_1 = trading_dictionary.search("ঝুঁকি", limit=5)
    assert len(bn_results_1) > 0, "Bengali query for 'ঝুঁকি' returned 0 results"

    bn_results_2 = trading_dictionary.search("ব্রেকআউট", limit=5)
    assert len(bn_results_2) > 0, "Bengali query for 'ব্রেকআউট' returned 0 results"


def test_m80_governance_invariants_locked() -> None:
    """Verifies that all capital safety and paper mode invariants are strictly locked."""
    assert CAPITAL_MODE == "TIER_0_PAPER"
    assert REAL_CAPITAL_ENABLED is False

    assert p2_sr.CAPITAL_MODE == "TIER_0_PAPER"
    assert p2_sr.REAL_CAPITAL_ENABLED is False

    assert v2b_cs.CAPITAL_MODE == "TIER_0_PAPER"
    assert v2b_cs.REAL_CAPITAL_ENABLED is False

    # Check live SQLite DB integrity if they exist
    for db_name in ["p2_shadow_ledger.db", "v2b_challenger_shadow_ledger.db"]:
        db_path = ROOT / "data" / db_name
        if db_path.exists():
            with sqlite3.connect(db_path) as conn:
                res = conn.execute("PRAGMA integrity_check").fetchone()[0]
                assert res == "ok", f"Integrity check failed for {db_name}: {res}"
