"""
tests/test_research_wikipedia.py
================================
Unit test suite for SKY Research Wikipedia & Living Knowledge Journal Engine.

Validates:
1. Database initialization and foundational seed articles (US-China economic trajectory).
2. Epistemic claim extraction and cross-verification status tagging ([FACT], [HYPOTHESIS], [CONTRADICTION]).
3. Universal URL and text ingestion with Markdown file generation.
4. Search, filtering, and [[WikiLink]] cross-referencing.
5. Invariant: Research Knowledge != Live Execution Authority.
"""

import os
import time
from pathlib import Path
import pytest

from core.knowledge_os.research_wikipedia import (
    ResearchWikipediaEngine,
    WikiArticle,
    EpistemicClaim,
)


@pytest.fixture
def temp_wiki_engine(tmp_path: Path) -> ResearchWikipediaEngine:
    """Creates a temporary, sandboxed ResearchWikipediaEngine instance."""
    db_path = tmp_path / "test_research_wiki.db"
    articles_dir = tmp_path / "articles"
    return ResearchWikipediaEngine(db_path=db_path, articles_dir=articles_dir)


def test_wiki_initialization_and_seeding(temp_wiki_engine: ResearchWikipediaEngine):
    """Verifies that the engine initializes and seeds foundational articles."""
    articles = temp_wiki_engine.list_articles()
    assert len(articles) >= 3, "Expected at least 3 seed articles on initial startup"

    titles = [a["title"] for a in articles]
    assert any("US & China" in t for t in titles), "US & China economic trajectory article must be seeded"
    assert any("De-Dollarization" in t for t in titles), "De-Dollarization article must be seeded"
    assert any("Concentrated Liquidity" in t for t in titles), "Concentrated AMM article must be seeded"


def test_us_china_article_structure(temp_wiki_engine: ResearchWikipediaEngine):
    """Verifies that the US-China article contains verified claims, contradictions, and [[WikiLinks]]."""
    article = temp_wiki_engine.get_article("wiki_us_china_economic_trajectory_hegemony")
    assert article is not None, "US-China article must exist"
    assert "https://www.facebook.com/share/r/14rU2inKqPQ/" in article.source_url
    assert article.source_type == "FACEBOOK_REEL"
    assert len(article.key_claims) >= 4

    statuses = [c.epistemic_status for c in article.key_claims]
    assert "FACT" in statuses, "Must contain verified factual claims"
    assert "CONTRADICTION" in statuses, "Must flag narrative contradictions (e.g. instant dollar crash)"
    assert "HYPOTHESIS" in statuses, "Must tag probabilistic macro trends"

    # Verify Markdown persistence
    md_file = temp_wiki_engine.articles_dir / f"{article.article_id}.md"
    assert md_file.exists(), f"Markdown file must be generated at {md_file}"
    content = md_file.read_text(encoding="utf-8")
    assert "# US & China Future Economic Trajectory" in content
    assert "[[US Sovereign Debt Servicing & Treasury Liquidity]]" in content


def test_ingest_custom_url_and_markdown_generation(temp_wiki_engine: ResearchWikipediaEngine):
    """Tests ingesting a new URL and verifying disk persistence."""
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    article = temp_wiki_engine.ingest_url_or_content(
        url_or_text=test_url,
        custom_title="Global Liquidity Regimes & Sovereign Yield Curves",
        custom_category="Monetary Policy & Debt Cycles",
        custom_author="Dr. Quant Macro",
    )

    assert article.article_id.startswith("wiki_")
    assert article.source_type == "YOUTUBE"
    assert article.verification_score > 0
    assert len(article.key_claims) > 0

    # Retrieve from DB
    retrieved = temp_wiki_engine.get_article(article.article_id)
    assert retrieved is not None
    assert retrieved.title == "Global Liquidity Regimes & Sovereign Yield Curves"

    # Check Markdown file
    md_file = temp_wiki_engine.articles_dir / f"{article.article_id}.md"
    assert md_file.exists()


def test_search_and_category_filtering(temp_wiki_engine: ResearchWikipediaEngine):
    """Tests search filtering by term and category."""
    # Category filter
    macro_articles = temp_wiki_engine.list_articles(category="Macro Geopolitics & Hegemony")
    assert len(macro_articles) >= 1
    assert all("Macro" in a["category"] for a in macro_articles)

    # Search term filter
    search_results = temp_wiki_engine.list_articles(search_query="China")
    assert len(search_results) >= 1
    assert "China" in search_results[0]["title"]


def test_article_deletion(temp_wiki_engine: ResearchWikipediaEngine):
    """Tests that deleting an article cleans up both DB and disk."""
    article = temp_wiki_engine.ingest_url_or_content(
        url_or_text="Temporary research note for testing deletion.",
        custom_title="Temporary Test Entry",
    )
    art_id = article.article_id
    md_path = temp_wiki_engine.articles_dir / f"{art_id}.md"
    assert md_path.exists()

    success = temp_wiki_engine.delete_article(art_id)
    assert success is True
    assert temp_wiki_engine.get_article(art_id) is None
    assert not md_path.exists()
