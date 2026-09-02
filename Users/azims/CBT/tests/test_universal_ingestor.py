"""
tests/test_universal_ingestor.py
================================
Unit tests for SKY Universal Research Ingestor and Provenance 4-Vault Engine.
"""

import pytest
import asyncio
from core.provenance_engine import provenance_engine
from core.universal_ingestor import universal_ingestor


@pytest.mark.asyncio
async def test_universal_ingestor_analyze_mode():
    """Verifies that ANALYZE mode extracts concepts to Knowledge Vault without creating Strategy Candidates."""
    sample_text = (
        "In Smart Money Concepts, a Fair Value Gap (FVG) represents a 3-candle imbalance. "
        "When price retraces into the FVG zone, institutional resting liquidity absorbs the orders. "
        "Always size positions using conservative half-kelly rules."
    )

    result = await universal_ingestor.ingest(
        content=sample_text,
        mode="ANALYZE",
        title="SMC FVG & Risk Theory Lesson",
        author_creator="Institutional Quant Academy",
    )

    assert result["knowledge_id"].startswith("K-")
    assert result["mode"] == "ANALYZE"
    assert result["summary"]["concepts_saved"] >= 1
    assert result["summary"]["candidates_queued"] == 0  # ANALYZE mode must NOT queue strategy candidates
    assert len(result["concepts"]) >= 1


@pytest.mark.asyncio
async def test_universal_ingestor_research_mode():
    """Verifies that RESEARCH mode extracts strategy candidates with entry/exit rules and parameter bounds."""
    sample_strategy = (
        "Strategy Name: Asian Judas Sweep Reversal\n"
        "Entry Rule: Wait for Asian session high sweep, then enter short on 5m Market Structure Shift.\n"
        "Exit Rule: Take profit at opposite Asian low, stop loss above sweep wick high.\n"
        "Parameters: min_fvg_bps=5.0, risk_pct=1.0%."
    )

    result = await universal_ingestor.ingest(
        content=sample_strategy,
        mode="RESEARCH",
        title="Asian Sweep MSS Strategy",
        author_creator="Photon Trading",
    )

    assert result["knowledge_id"].startswith("K-")
    assert result["mode"] == "RESEARCH"
    assert result["summary"]["candidates_queued"] >= 1
    assert len(result["strategy_candidates"]) >= 1

    cand = result["strategy_candidates"][0]
    assert cand["validation_stage"] == "UNTESTED"
    assert "entry_rules" in cand


@pytest.mark.asyncio
async def test_provenance_vaults_query():
    """Verifies that the 4 vaults can be queried with consistent counts."""
    vaults = provenance_engine.get_all_vault_data()
    assert "counts" in vaults
    assert "knowledge" in vaults
    assert "candidates" in vaults
    assert "evidence" in vaults
    assert "rejected" in vaults
    assert vaults["counts"]["knowledge_count"] >= 0
    assert vaults["counts"]["candidates_count"] >= 0
