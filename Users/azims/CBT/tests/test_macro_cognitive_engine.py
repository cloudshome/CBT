"""
Tests for MacroCognitiveEngine.
Verifies multimodal economic comprehension, causal transmission chain extraction,
deterministic heuristic fallback, and SQLite memory persistence.
"""

import pytest

from core.macro_cognitive_engine import (
    MacroCognitiveEngine,
    MacroComprehensionResult,
)


@pytest.fixture
def macro_engine():
    return MacroCognitiveEngine()


def test_heuristic_fallback_dovish_reel(macro_engine):
    """Verifies that an economic talk show reel with rate cuts and dovish cues produces DOVISH regime."""
    reel_transcript = """
    Welcome to Macro Insights Daily. Today Chairman Powell stated at the press conference
    that the Federal Reserve will begin aggressive rate cuts. We anticipate a 50 bps cut as
    inflation is cooling rapidly. The dollar index DXY is breaking down below 101, and US 10Y yields
    are falling to 3.8%. This massive liquidity expansion is set to boost risk assets, especially Bitcoin and Ethereum.
    """
    result = macro_engine._analyze_deterministic(
        text=reel_transcript,
        title="Powell Pivot Reel",
        author="Macro Insights Daily",
    )

    assert isinstance(result, MacroComprehensionResult)
    assert result.macro_regime.monetary_stance == "DOVISH"
    assert result.macro_regime.liquidity_cycle == "EXPANDING"
    assert len(result.causal_chains) >= 1
    assert "CRYPTO_BTC" in result.asset_matrix
    assert result.asset_matrix["CRYPTO_BTC"].sentiment == "BULLISH"
    assert result.trade_planning_implications["btc_bias"] == "LONG"
    assert result.trade_planning_implications["kelly_multiplier"] == 1.0


def test_heuristic_fallback_hawkish_talkshow(macro_engine):
    """Verifies that a hawkish talk show with sticky inflation triggers HAWKISH regime and dampened sizing."""
    talk_show_transcript = """
    On Bloomberg Surveillance, former Fed governor discusses persistent sticky inflation and CPI prints.
    The Fed will be forced to pause cuts or even consider rate hikes to fight stagflation.
    Quantitative tightening continues, contracting global liquidity. The dollar index is surging,
    putting intense downward pressure on equities and crypto assets.
    """
    result = macro_engine._analyze_deterministic(
        text=talk_show_transcript,
        title="Inflation Panic Show",
        author="Bloomberg Surveillance",
    )

    assert result.macro_regime.monetary_stance == "HAWKISH"
    assert result.macro_regime.liquidity_cycle == "CONTRACTING"
    assert result.asset_matrix["CRYPTO_BTC"].sentiment == "BEARISH"
    assert result.trade_planning_implications["btc_bias"] == "SHORT"
    assert result.trade_planning_implications["kelly_multiplier"] == 0.5


def test_sqlite_memory_persistence(macro_engine):
    """Verifies saving and retrieving macro intelligence from the SQLite memory store."""
    reel_text = "Federal Reserve announces rate cuts as inflation softens. Liquidity expansion. Bitcoin rally expected."
    result = macro_engine.analyze_macro_content(
        text=reel_text,
        title="Test Fed Reel",
        author="Fed Speaker",
    )
    assert result is not None

    latest_state = macro_engine.get_latest_macro_state()
    assert latest_state is not None
    assert latest_state["source_title"] == "Test Fed Reel"
    assert latest_state["macro_regime"]["monetary_stance"] == "DOVISH"


def test_epistemic_separation_and_causal_chains(macro_engine):
    """Verifies causal transmission chains have cause -> mechanism -> market_impact -> crypto_consequence."""
    text = (
        "Interest rate cuts reduce yields, expanding dollar liquidity and driving Bitcoin inflows."
    )
    result = macro_engine.analyze_macro_content(
        text=text,
        title="Transmission Test",
        author="Macro Analyst",
    )
    assert len(result.causal_chains) > 0
    chain = result.causal_chains[0]
    assert hasattr(chain, "cause")
    assert hasattr(chain, "mechanism")
    assert hasattr(chain, "market_impact")
    assert hasattr(chain, "crypto_consequence")
    assert hasattr(chain, "time_horizon")
