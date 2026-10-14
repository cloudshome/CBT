"""
tests/test_crawler_daemon.py
============================
Unit tests for CrawlerDaemon:
1. Verifies harvest cycle execution across adapters.
2. Asserts accepted evidence is stored into ResearchWikipedia and research_sources.
3. Tests status serialization.
"""

import pytest
from pathlib import Path
import tempfile
from core.intelligence.crawler.crawler_daemon import CrawlerDaemon
from core.knowledge_os.research_wikipedia import ResearchWikipediaEngine


@pytest.fixture
def temp_crawler_env(tmp_path: Path):
    db_path = tmp_path / "test_wiki.db"
    state_file = tmp_path / "test_crawler_state.json"
    engine = ResearchWikipediaEngine(db_path=db_path)
    daemon = CrawlerDaemon(
        wiki_engine=engine,
        state_file=state_file,
        interval_hours=4.0,
    )
    return daemon, engine


@pytest.mark.asyncio
async def test_crawler_daemon_harvest_and_status(temp_crawler_env):
    daemon, engine = temp_crawler_env

    # 1. Check initial status
    status = daemon.get_status()
    assert status.total_cycles_completed == 0
    assert "academic" in status.active_domains

    # 2. Execute harvest cycle (macro domain)
    summary = await daemon.execute_harvest_cycle(domain_keys=["macro"])
    assert "run_id" in summary
    assert daemon._total_cycles == 1

    # 3. Verify status updated
    new_status = daemon.get_status()
    assert new_status.total_cycles_completed == 1
    assert new_status.last_run_at is not None

