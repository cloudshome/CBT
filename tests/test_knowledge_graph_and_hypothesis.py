"""
tests/test_knowledge_graph_and_hypothesis.py
============================================
Comprehensive test suite for SKY Knowledge & Discovery Graph (10/10 Architecture).
Verifies:
1. Multi-Dimensional atomic decomposition preserving verbatim source framing.
2. 6-Node ontology (Sources, Claims, Concepts, Variables, Observations, Edges).
3. Cross-Domain link discovery connecting unconventional worldviews to financial variables.
4. Formal Hypothesis Formulation (H0 vs H1).
5. Empirical Statistical Testing against historical market data with p-value & effect size.
"""

import pytest

from core.knowledge_graph_engine import knowledge_graph_engine
from core.universal_ingestor import universal_ingestor


@pytest.mark.asyncio
async def test_astrology_cross_domain_decomposition():
    """
    Verifies that an astrology source retains its original framing (worldview: ASTROLOGICAL)
    without contaminating the normalized quantitative ontology.
    """
    sample_text = (
        "When Saturn aligns in retrograde Cycle X, human conflict historically increases across nations. "
        "Economic disruptions and market shocks follow in clusters."
    )

    result = await universal_ingestor.ingest(
        content=sample_text,
        mode="RESEARCH",
        title="Cycles and Historical Turmoil",
        author_creator="Historical Cycle Researcher",
    )

    assert result["worldview"] == "ASTROLOGICAL"
    assert result["source"]["original_worldview"] == "ASTROLOGICAL"
    assert len(result["claims"]) >= 1

    claim = result["claims"][0]
    assert claim["source_worldview"] == "ASTROLOGICAL"
    assert claim["epistemic_status"] == "UNVERIFIED"
    assert (
        "Retrograde" in claim["original_claim_verbatim"]
        or "Saturn" in claim["original_claim_verbatim"]
    )

    # Observations must be separated from causal claims
    assert len(result["observations"]) >= 1
    assert (
        "Decade" in result["observations"][0]["period_context"]
        or "Historical" in result["observations"][0]["period_context"]
    )


@pytest.mark.asyncio
async def test_cross_domain_discovery_and_hypothesis_workflow():
    """
    Verifies that the Discovery Engine generates cross-domain candidate links
    and can formulate a testable H0/H1 hypothesis.
    """
    # Trigger cross-domain discovery
    discoveries = knowledge_graph_engine.discover_cross_domain_links()
    assert len(discoveries) >= 1

    disc = discoveries[0]
    assert "cross_domain_candidate" in disc
    assert disc["status"] == "UNTESTED"

    # Formulate hypothesis from discovery
    hypo = knowledge_graph_engine.create_hypothesis(
        title=f"Test Hypothesis from {disc['discovery_id']}",
        null_hypothesis=f"H0: {disc['target_variable']} has zero statistical difference across phases.",
        alt_hypothesis=disc["proposed_hypothesis"],
        independent_variable="TEMPORAL_CYCLE_PHASE",
        dependent_variable=disc["target_variable"],
        target_symbol=disc["target_symbol"],
        test_method="VOLATILITY_EVENT_STUDY",
        control_variables=["HALVING_CYCLE", "FUNDING_RATE", "DXY"],
    )

    assert hypo.hypothesis_id.startswith("H-")
    assert hypo.validation_status == "QUEUED"

    # Run Empirical Test against market candles
    test_res = knowledge_graph_engine.run_empirical_test(hypo.hypothesis_id)
    assert "verdict" in test_res
    assert "p_value" in test_res
    assert "effect_size" in test_res
    assert test_res["verdict"] in ["SUPPORTED", "REJECTED", "INCONCLUSIVE", "REFUTED"]
    assert 0.0 <= test_res["p_value"] <= 1.0


@pytest.mark.asyncio
async def test_full_graph_payload_retrieval():
    """Verifies that the full 6-node ontology graph is returned cleanly."""
    graph = knowledge_graph_engine.get_full_graph_payload()
    assert "nodes" in graph
    assert "edges" in graph
    assert "hypotheses" in graph
    assert "discoveries" in graph
    assert "counts" in graph
    assert graph["counts"]["sources_count"] >= 1
    assert graph["counts"]["claims_count"] >= 1
    assert graph["counts"]["variables_count"] >= 5
