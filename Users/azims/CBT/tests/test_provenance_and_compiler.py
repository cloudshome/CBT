"""
Tests for Universal Provenance Engine and Formal Strategy Genome Compiler.
Validates cryptographic source hashing, immutable provenance storage,
deterministic strategy compilation, and fail-closed validation rules.
"""

import pytest
from fastapi.testclient import TestClient

from app import app
from core.provenance_engine import ProvenanceEngine, provenance_engine
from core.strategy_compiler import CompilationStatus, RuleOrigin, StrategyCompiler, strategy_compiler
from core.strategy_league import QuarantineTier, strategy_league_manager


@pytest.fixture
def client():
    return TestClient(app)


def test_compute_sha256_deterministic():
    engine = ProvenanceEngine()
    content = "Quantitative trading strategy based on London liquidity sweeps."
    h1 = engine.compute_sha256(content)
    h2 = engine.compute_sha256(content)
    assert h1 == h2
    assert len(h1) == 64
    
    # Different content produces different hash
    h3 = engine.compute_sha256(content + " ")
    assert h1 != h3


def test_provenance_registration_and_deduplication():
    content = "ICT Fair Value Gap and Asian Range Liquidity Sweep Rulebook 2026."
    title = "SMC Rulebook"
    
    # Register source
    rec1 = provenance_engine.register_source(
        source_type="PDF",
        raw_content=content,
        title=title,
        source_url="https://arxiv.org/abs/2608.12345",
        confidence=0.95,
        extracted_facts=[{"fact": "London session open sweeps Asian high 68% of days"}],
    )
    assert rec1.source_id.startswith("SRC-")
    assert rec1.source_type == "PDF"
    assert rec1.title == title
    assert len(rec1.extracted_facts) == 1

    # Re-registering exact content should return existing record (deduplication)
    rec2 = provenance_engine.register_source(
        source_type="PDF",
        raw_content=content,
        title="Duplicate SMC Rulebook",
    )
    assert rec2.source_id == rec1.source_id
    assert rec2.content_hash == rec1.content_hash


def test_provenance_retrieval():
    content = "Unique institutional order flow observation 491823."
    rec = provenance_engine.register_source(
        source_type="TEXT",
        raw_content=content,
        title="Order Flow Note",
    )
    
    # Fetch by ID
    by_id = provenance_engine.get_by_id(rec.source_id)
    assert by_id is not None
    assert by_id.source_id == rec.source_id
    assert by_id.content_hash == rec.content_hash

    # Fetch by Hash
    by_hash = provenance_engine.get_by_hash(rec.content_hash)
    assert by_hash is not None
    assert by_hash.source_id == rec.source_id


def test_strategy_compiler_valid_hypothesis():
    compiler = StrategyCompiler()
    compiled = compiler.compile_hypothesis(
        name="London Breakout & Asian Sweep",
        raw_description="Wait for Asian session high sweep, then enter on 15m FVG retest with stop at sweep swing high.",
        assets=["BTCUSDT", "ETHUSDT"],
        timeframes={"bias": "4h", "setup": "1h", "entry": "15m"},
        entry_rules=[
            {"condition": "LIQUIDITY_SWEEP_CONFIRMATION", "origin": "EXPLICIT", "parameters": {"wick_ratio": 0.5}}
        ],
        invalidation_rules=[
            {"condition": "SWEEP_HIGH_BUFFER", "origin": "EXPLICIT", "parameters": {"buffer_atr": 0.5}}
        ],
        exit_rules=[
            {"condition": "OPPOSITE_ASIAN_LOW", "origin": "EXPLICIT", "parameters": {"min_rr": 2.5}}
        ],
    )
    
    assert compiled.status == CompilationStatus.READY_FOR_BACKTEST
    assert len(compiled.missing_requirements) == 0
    assert len(compiled.entry_conditions) == 1
    assert len(compiled.invalidation_conditions) == 1
    assert compiled.confidence >= 0.80

    # Verify registered in Strategy League
    leaderboard = strategy_league_manager.get_leaderboard()
    registered_ids = [s["dna_id"] for s in leaderboard]
    assert compiled.strategy_id in registered_ids


def test_strategy_compiler_rejects_missing_invalidation():
    compiler = StrategyCompiler()
    # Explicitly pass empty invalidation rules and vague description without stops
    compiled = compiler.compile_hypothesis(
        name="Vague Moving Average Crossover",
        raw_description="Buy when 9 EMA crosses 21 EMA.",
        assets=["BTCUSDT"],
        entry_rules=[{"condition": "EMA_CROSS", "origin": "EXPLICIT"}],
        invalidation_rules=[],  # Empty
        exit_rules=[{"condition": "CROSS_BACK", "origin": "EXPLICIT"}],
    )
    # Must fail closed with NOT_BACKTESTABLE due to missing risk/stop-loss definition
    assert compiled.status == CompilationStatus.NOT_BACKTESTABLE
    assert any("invalidation" in m.lower() or "stop" in m.lower() for m in compiled.missing_requirements)


def test_strategy_compiler_rejects_invalid_timeframe():
    compiler = StrategyCompiler()
    compiled = compiler.compile_hypothesis(
        name="Bad Timeframe Strat",
        raw_description="Sweep with stop at low",
        assets=["BTCUSDT"],
        timeframes={"entry": "99m"},  # Invalid
        entry_rules=[{"condition": "SWEEP", "origin": "EXPLICIT"}],
        invalidation_rules=[{"condition": "STOP_LOW", "origin": "EXPLICIT"}],
    )
    assert compiled.status == CompilationStatus.NOT_BACKTESTABLE
    assert any("Invalid timeframe" in m for m in compiled.missing_requirements)


def test_api_provenance_and_compiler_routes(client):
    # 1. Ingest research source via API
    ingest_res = client.post(
        "/api/ingest/source",
        json={
            "source_type": "URL",
            "content": "Paper on Cross-Asset Lead-Lag Alpha between PAXG and BTC during macro shocks.",
            "title": "Lead-Lag Paper 2026",
            "source_url": "https://ssrn.com/abstract=391234",
            "confidence": 0.92,
        },
    )
    assert ingest_res.status_code == 200
    src_data = ingest_res.json()
    assert "source_id" in src_data
    source_id = src_data["source_id"]

    # 2. List provenance records
    list_res = client.get("/api/ingest/provenance?limit=10")
    assert list_res.status_code == 200
    records = list_res.json()["records"]
    assert any(r["source_id"] == source_id for r in records)

    # 3. Get specific provenance record
    get_res = client.get(f"/api/ingest/provenance/{source_id}")
    assert get_res.status_code == 200
    assert get_res.json()["source_id"] == source_id

    # 4. Compile strategy via API
    compile_res = client.post(
        "/api/strategy/compile",
        json={
            "name": "API Compiled Macro Strategy",
            "description": "Cross-asset impulse entry with invalidation at ATR stop.",
            "assets": ["BTCUSDT", "PAXGUSDT"],
            "timeframes": {"bias": "1d", "entry": "1h"},
            "entry_rules": [{"condition": "MACRO_IMPULSE", "origin": "EXPLICIT"}],
            "invalidation_rules": [{"condition": "ATR_STOP", "origin": "EXPLICIT", "parameters": {"atr_mult": 1.5}}],
            "source_id": source_id,
        },
    )
    assert compile_res.status_code == 200
    comp_data = compile_res.json()
    assert comp_data["status"] == "READY_FOR_BACKTEST"

    # 5. List Strategy Genomes
    genomes_res = client.get("/api/strategy/genomes")
    assert genomes_res.status_code == 200
    assert len(genomes_res.json()["genomes"]) >= 1
