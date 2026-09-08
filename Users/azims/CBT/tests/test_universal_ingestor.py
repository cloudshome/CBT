"""
tests/test_universal_ingestor.py
================================
Unit tests for SKY Universal Research Ingestor and Provenance 4-Vault Engine.
"""

import pytest

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
    assert (
        result["summary"]["candidates_queued"] == 0
    )  # ANALYZE mode must NOT queue strategy candidates
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


@pytest.mark.asyncio
async def test_multi_source_summary_synthesis():
    """Verifies executive synthesis narrative and chapter breakdown generation across YouTube, Code, and Notes."""
    # 1. Code / Algorithmic source
    code_text = (
        "class VWAPMeanReversion:\n"
        "    def calculate_bands(self, df):\n"
        "        pass\n"
        "    def check_rsi_divergence(self, rsi, price):\n"
        "        pass\n"
    )
    code_result = await universal_ingestor.ingest(
        content=code_text,
        mode="ANALYZE",
        title="VWAP Divergence Strategy",
        author_creator="Quant Dev",
        file_name="vwap_strat.py",
    )
    assert "Algorithmic Source Code" in code_result["executive_summary"]
    assert len(code_result["chapter_breakdown"]) >= 1
    assert any("calculate_bands" in ch for ch in code_result["chapter_breakdown"])

    # 2. Notes / Research Article
    notes_text = (
        "# Liquidity Void Analysis\n\n"
        "Institutional market makers engineer liquidity voids prior to NY open.\n\n"
        "## Order Book Imbalance\n\n"
        "Bids are pulled rapidly when VPIN spikes above 0.35 threshold.\n"
    )
    notes_result = await universal_ingestor.ingest(
        content=notes_text,
        mode="RESEARCH",
        title="Order Book Liquidity Voids",
        author_creator="Market Microstructure Lab",
    )
    assert "Research Literature Synthesis" in notes_result["executive_summary"]
    assert len(notes_result["chapter_breakdown"]) >= 1


def test_telegram_research_summary_dispatch():
    """Verifies POST /api/research/share-telegram endpoint formats and processes telegram dispatch gracefully."""
    from unittest.mock import AsyncMock, patch

    from starlette.testclient import TestClient

    from app import app
    from core.telegram_bot import telegram_bot

    client = TestClient(app)
    payload = {
        "knowledge_id": "K-TEST-992",
        "title": "Algorithmic Market Making & High-Frequency Trading",
        "author_creator": "Alvaro Cartea",
        "source_type": "PDF_BOOK",
        "executive_summary": "Quantitative monograph presenting stochastic control models for optimal limit order submission and inventory risk penalization.",
        "chapter_breakdown": [
            "Ch 1: Limit Order Books",
            "Ch 2: Optimal Liquidation",
            "Ch 3: Market Making",
        ],
        "epistemic_counts": {"facts": 14, "hypotheses": 5, "rules": 3, "contradictions": 0},
        "candidate_summary": "Inventory Penalized Avellaneda-Stoikov Market Maker",
    }
    with patch.object(telegram_bot, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        resp = client.post("/api/research/share-telegram", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("SENT", "QUEUED_LOCAL")
        assert "dispatched_text" in data
        assert "Alvaro Cartea" in data["dispatched_text"]
        assert "K-TEST-992" in data["dispatched_text"]
        assert "Inventory Penalized" in data["dispatched_text"]


@pytest.mark.asyncio
async def test_telegram_reverse_flow_link_ingestion():
    """Verifies that dropping a research link into Telegram automatically triggers Research Lab ingestion."""
    from unittest.mock import AsyncMock, patch

    from core.telegram_bot import telegram_bot

    update = {
        "update_id": 9991,
        "message": {
            "chat": {"id": 12345},
            "text": "Check out this thesis: https://github.com/quant-research/smc-alpha",
            "from": {"first_name": "QuantTrader"},
        },
    }

    with patch.object(telegram_bot, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        res = await telegram_bot.handle_webhook_update(update)
        assert res["status"] == "RESEARCH_INGESTED"
        assert res["type"] == "LINK"
        assert res["knowledge_id"].startswith("K-")
        assert mock_send.called
        any_summary = any(
            "FILED IN SKY RESEARCH LAB" in call.args[0] for call in mock_send.call_args_list
        )
        assert any_summary


@pytest.mark.asyncio
async def test_telegram_reverse_flow_photo_ingestion():
    """Verifies that dropping a photo into Telegram automatically triggers Vision OCR & Research Lab ingestion."""
    from unittest.mock import AsyncMock, patch

    from core.telegram_bot import telegram_bot

    update = {
        "update_id": 9992,
        "message": {
            "chat": {"id": 12345},
            "photo": [{"file_id": "photo_low_res"}, {"file_id": "photo_high_res"}],
            "caption": "BTC 15m Fair Value Gap Setup",
            "from": {"first_name": "QuantTrader"},
        },
    }

    with (
        patch.object(
            telegram_bot, "download_telegram_file", new_callable=AsyncMock
        ) as mock_download,
        patch.object(telegram_bot, "send_message", new_callable=AsyncMock) as mock_send,
    ):
        mock_download.return_value = b"\x89PNG\r\n\x1a\nfake_image_bytes"
        mock_send.return_value = True
        res = await telegram_bot.handle_webhook_update(update)
        assert res["status"] == "RESEARCH_INGESTED"
        assert res["type"] == "PHOTO"
        assert res["knowledge_id"].startswith("K-")
        assert mock_send.called
        any_summary = any(
            "FILED IN SKY RESEARCH LAB" in call.args[0] for call in mock_send.call_args_list
        )
        assert any_summary


@pytest.mark.asyncio
async def test_universal_ingestor_auto_mode():
    """Verify that AUTO mode auto-detects trading rules vs conceptual literature."""
    # 1. Pure conceptual literature without trading rules: should NOT queue candidate
    lit_text = (
        "Macroeconomic cycles and sovereign debt crises: historical analysis of "
        "interest rate policy and liquidity regimes from 1945 to 1980."
    )
    res_lit = await universal_ingestor.ingest(
        content=lit_text,
        mode="AUTO",
        title="Macroeconomic Debt Regimes",
    )
    assert res_lit["mode"] == "AUTO"
    assert len(res_lit["strategy_candidates"]) == 0
    assert res_lit["summary"]["candidates_queued"] == 0

    # 2. Setup with explicit trading rules: SHOULD queue candidate
    strategy_text = (
        "ICT Liquidity Sweep Model: Entry rule triggers on 15m Fair Value Gap "
        "following a Judas sweep of the Asian session high. Stop loss placed 2 ticks below swing low, "
        "take profit at opposing liquidity pool with 1.5R minimum target."
    )
    res_strat = await universal_ingestor.ingest(
        content=strategy_text,
        mode="AUTO",
        title="ICT Judas Sweep 15m Model",
    )
    assert res_strat["mode"] == "AUTO"
    assert len(res_strat["strategy_candidates"]) == 1
    assert res_strat["summary"]["candidates_queued"] == 1
    cand = res_strat["strategy_candidates"][0]
    assert cand["validation_stage"] == "UNTESTED"
    assert cand["zero_alpha_assumption"] is True
