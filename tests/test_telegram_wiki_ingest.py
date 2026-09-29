"""
tests/test_telegram_wiki_ingest.py
==================================
Unit test suite validating Telegram V5 Research Wikipedia & Journal Integration.

Validates:
1. Command registry registration of /wiki with aliases (/wikipedia, /journal, /encyclopedia).
2. Institutional /wiki command handler:
   - Catalog listing (/wiki, /wiki list)
   - Search execution (/wiki search <term>)
   - Direct article dossier inspection (/wiki <article_id>)
   - URL ingestion and instant fact-checking (/wiki <url>)
3. TelegramBotDispatcher two-way reverse flow link ingestion:
   - Ingests Facebook Reel / Web / YouTube URLs directly into Research Wikipedia.
   - Generates persistent Markdown articles in data/research_wiki/articles/.
   - Returns institutional Research Wikipedia Telegram card.
4. Role-based access control (RBAC): ANALYST role access verification.
"""

from __future__ import annotations

import pytest

from core.knowledge_os.research_wikipedia import research_wikipedia_engine
from core.telegram.commands import command_registry
from core.telegram.handlers import handle_wiki
from core.telegram.rbac import TelegramRole, TelegramUserIdentity
from core.telegram_bot import telegram_bot


@pytest.fixture
def analyst_identity() -> TelegramUserIdentity:
    return TelegramUserIdentity(
        user_id=12345678,
        chat_id=99999,
        username="test_analyst",
        role=TelegramRole.ANALYST,
    )


def test_wiki_command_registered_in_registry():
    """Verifies that /wiki and its aliases are properly registered in command_registry."""
    cmd = command_registry.get_command("/wiki")
    assert cmd is not None, "/wiki command must be registered in command_registry"
    assert cmd.name == "/wiki"
    assert cmd.required_role == TelegramRole.ANALYST
    assert "/wikipedia" in cmd.aliases
    assert "/journal" in cmd.aliases
    assert "/encyclopedia" in cmd.aliases

    # Check aliases resolve
    assert command_registry.get_command("/wikipedia") is not None
    assert command_registry.get_command("/journal") is not None
    assert command_registry.get_command("/encyclopedia") is not None


@pytest.mark.asyncio
async def test_handle_wiki_list(analyst_identity: TelegramUserIdentity):
    """Verifies that /wiki (no args) returns the recent research Wikipedia catalog."""
    res = await handle_wiki("", chat_id="99999", identity=analyst_identity)
    assert "SKY RESEARCH WIKIPEDIA JOURNAL" in res
    assert "Active living encyclopedia" in res
    assert "/wiki" in res


@pytest.mark.asyncio
async def test_handle_wiki_search(analyst_identity: TelegramUserIdentity):
    """Verifies that /wiki search <query> returns relevant articles."""
    res = await handle_wiki("search China", chat_id="99999", identity=analyst_identity)
    assert "WIKIPEDIA SEARCH RESULTS FOR: 'China'" in res
    assert "US & China" in res or "China" in res


@pytest.mark.asyncio
async def test_handle_wiki_article_lookup(analyst_identity: TelegramUserIdentity):
    """Verifies looking up an article by its ID returns the detailed research card."""
    res = await handle_wiki(
        "wiki_us_china_economic_trajectory_hegemony",
        chat_id="99999",
        identity=analyst_identity,
    )
    assert "RESEARCH WIKIPEDIA ENTRY FILED" in res
    assert "US & China" in res
    assert "Epistemic Rigor:" in res
    assert "[FACT]" in res
    assert "data/research_wiki/articles/" in res


@pytest.mark.asyncio
async def test_handle_wiki_url_ingestion(analyst_identity: TelegramUserIdentity):
    """Verifies that /wiki <url> triggers epistemic fact-checking and files an entry."""
    test_url = "https://www.facebook.com/share/r/14rU2inKqPQ/"
    res = await handle_wiki(test_url, chat_id="99999", identity=analyst_identity)
    assert "RESEARCH WIKIPEDIA ENTRY FILED" in res
    assert "US & China" in res
    assert "Epistemic Rigor:" in res
    assert "Provenance ID:" in res


@pytest.mark.asyncio
async def test_telegram_reverse_flow_link_ingest_facebook():
    """
    Verifies that dropping a Facebook Reel link into Telegram triggers
    handle_telegram_research_ingest, creates the Wikipedia entry, and saves the Markdown file.
    """
    fb_url = "https://www.facebook.com/share/r/14rU2inKqPQ/"
    res = await telegram_bot.handle_telegram_research_ingest(
        chat_id="99999",
        text=f"Check out this macro reel: {fb_url}",
        from_user="LeadMacroOperator",
    )
    assert res.get("status") == "RESEARCH_INGESTED"
    assert res.get("type") == "LINK"
    assert res.get("article_id") is not None

    # Verify article is present in Wikipedia engine
    article = research_wikipedia_engine.get_article(res["article_id"])
    assert article is not None
    assert article.author_or_speaker == "LeadMacroOperator" or "LeadMacroOperator" in str(
        article.author_or_speaker
    )
    assert len(article.key_claims) >= 3


@pytest.mark.asyncio
async def test_telegram_wiki_command_skip_in_ingest():
    """
    Verifies that a plain '/wiki' or '/wiki search' command is skipped in
    handle_telegram_research_ingest so it flows directly to the command dispatcher.
    """
    res1 = await telegram_bot.handle_telegram_research_ingest(
        chat_id="99999",
        text="/wiki",
        from_user="LeadMacroOperator",
    )
    assert res1.get("status") == "SKIPPED"

    res2 = await telegram_bot.handle_telegram_research_ingest(
        chat_id="99999",
        text="/wiki search liquidity",
        from_user="LeadMacroOperator",
    )
    assert res2.get("status") == "SKIPPED"
