"""
tests/test_url_extractor_and_universal_ingestion.py
===================================================
Unit & integration tests verifying:
1. URL Research Extraction (Web articles, ArXiv, GitHub repositories).
2. Universal Ingestor multi-paragraph decomposition.
3. Zero-Fabrication epistemic firewall adherence (confidence = 0.0 for qualitative claims).
"""

import pytest
from unittest.mock import patch, MagicMock
from core.url_extractor import url_extractor, URLExtractor
from core.universal_ingestor import universal_ingestor


def test_url_extractor_generic_article_mock():
    """Verifies that generic web articles are cleaned and parsed into structured text."""
    sample_html = """
    <html>
      <head>
        <title>Momentum Trading and Statistical Arbitrage</title>
        <meta property="og:title" content="Momentum Trading Guide" />
        <meta name="author" content="Dr. Quant" />
        <meta name="description" content="A comprehensive analysis of statistical arbitrage." />
      </head>
      <body>
        <nav><a href="/">Home</a></nav>
        <article>
          <h1>Momentum Trading Guide</h1>
          <p>Algorithmic momentum strategies exploit autocorrelation in asset returns across intraday timeframes.</p>
          <p>Risk is managed using half-Kelly sizing and hard volatility-adjusted stop losses to constrain tail drawdown.</p>
        </article>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    """

    with patch.object(url_extractor, "_fetch_html", return_value=sample_html):
        res = url_extractor.extract("https://quant-research.org/momentum-guide")

    assert res["success"] is True
    assert res["source_type"] == "ARTICLE"
    assert "Momentum" in res["title"]
    assert res["author_creator"] == "Dr. Quant"
    assert "autocorrelation" in res["text_content"]
    assert "half-Kelly" in res["text_content"]
    assert "Home" not in res["text_content"]
    assert "Copyright" not in res["text_content"]


def test_url_extractor_arxiv_mock():
    """Verifies ArXiv paper abstract and metadata extraction."""
    arxiv_html = """
    <html>
      <head><title>[2401.99999] High-Frequency Cross-Impact in Crypto</title></head>
      <body>
        <h1 class="title mathjax"><span class="descriptor">Title:</span>High-Frequency Cross-Impact in Crypto</h1>
        <div class="authors"><span class="descriptor">Authors:</span>Alice Smith, Bob Jones</div>
        <blockquote class="abstract mathjax">
          <span class="descriptor">Abstract:</span>
          We investigate cross-asset order flow imbalance and its predictive power over subsequent Bitcoin volatility.
        </blockquote>
      </body>
    </html>
    """

    with patch.object(url_extractor, "_fetch_html", return_value=arxiv_html):
        res = url_extractor.extract("https://arxiv.org/abs/2401.99999")

    assert res["success"] is True
    assert res["domain"] == "arxiv.org"
    assert "High-Frequency Cross-Impact" in res["title"]
    assert "Alice Smith" in res["author_creator"]
    assert "cross-asset order flow imbalance" in res["text_content"]


def test_url_extractor_github_raw_mock():
    """Verifies GitHub repository README extraction."""
    readme_md = """
    # Quantitative Risk Governor
    Author: QuantDesk

    This repository implements real-time Half-Kelly sizing and microstructure toxicity filters.
    When order book imbalance exceeds 0.75, liquidity taker aggression is throttled.
    """

    with patch.object(url_extractor, "_fetch_html", return_value=readme_md):
        res = url_extractor.extract("https://github.com/QuantDesk/risk-governor")

    assert res["success"] is True
    assert res["source_type"] == "GITHUB"
    assert res["author_creator"] == "QuantDesk"
    assert "Half-Kelly" in res["text_content"]


@pytest.mark.asyncio
async def test_universal_ingestor_url_e2e_mock():
    """Verifies end-to-end ingestion of a Web URL with multi-claim atomic decomposition."""
    sample_article_text = (
        "# Statistical Arbitrage in Digital Assets\n"
        "Author: Jane Doe\n"
        "Source: https://research.quant.io/stat-arb\n\n"
        "Mean reversion strategies in crypto pairs profit because liquidity fragmentation leads to temporary price dislocations.\n\n"
        "When the spread widens beyond 2.5 standard deviations, execution algorithms initiate twin limit orders.\n\n"
        "Tail risk is mitigated by monitoring funding rate skew and liquidation cascades across major venues.\n\n"
        "Empirical backtests show a Sharpe ratio of 2.1 under conservative 3-tier transaction friction modeling."
    )

    mock_extract = {
        "success": True,
        "url": "https://research.quant.io/stat-arb",
        "domain": "research.quant.io",
        "source_type": "ARTICLE",
        "title": "Statistical Arbitrage in Digital Assets",
        "author_creator": "Jane Doe",
        "summary": "Mean reversion strategies in crypto pairs.",
        "text_content": sample_article_text,
        "char_count": len(sample_article_text),
    }

    with patch("core.universal_ingestor.url_extractor.extract", return_value=mock_extract):
        res = await universal_ingestor.ingest(
            content="https://research.quant.io/stat-arb",
            mode="RESEARCH",
        )

    assert res["source_id"].startswith("S-")
    assert res["knowledge_id"].startswith("K-")
    assert res["source"]["source_type"] == "ARTICLE"
    assert "Statistical Arbitrage" in res["source"]["title"]
    assert res["source"]["author_creator"] == "Jane Doe"
    assert len(res["claims"]) >= 3
    # Check that claims adhere to Constitutional Zero-Fabrication (confidence = 0.0)
    for claim in res["claims"]:
        assert claim["confidence_score"] == 0.0
    assert len(res["concepts"]) >= 1
    assert len(res["observations"]) >= 1
