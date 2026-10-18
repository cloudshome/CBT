"""
tests/test_research_autonomous_feed.py
======================================
Tests for autonomous research feed extractor, registry, and pipeline ingestion.
Ensures zero-touch RSS ingestion, XML parsing, database persistence, and invariant safety.
"""

from core.knowledge_os.feed_extractor import FeedExtractor
from core.knowledge_os.research_source_registry import ResearchSourceRegistry

SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Federal Reserve Press Releases</title>
    <link>https://www.federalreserve.gov</link>
    <description>Recent press releases from the Federal Reserve Board</description>
    <item>
      <title>Federal Reserve issues FOMC statement on monetary policy stance</title>
      <link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20261011a.htm</link>
      <description>The Committee decided to maintain the target range for the federal funds rate at 4.25 to 4.5 percent.</description>
      <pubDate>Sun, 11 Oct 2026 12:00:00 GMT</pubDate>
      <guid>fomc-20261011a</guid>
    </item>
    <item>
      <title>Balance sheet normalization telemetry update</title>
      <link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20261011b.htm</link>
      <description>System Open Market Account holdings decreased by 25 billion dollars this month.</description>
      <pubDate>Sun, 11 Oct 2026 13:00:00 GMT</pubDate>
      <guid>fomc-20261011b</guid>
    </item>
  </channel>
</rss>
"""

SAMPLE_ATOM_XML = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Ethereum Protocol Research</title>
  <link href="https://blog.ethereum.org/"/>
  <entry>
    <title>Cancun-Deneb Blob Market Structure and Data Availability</title>
    <link href="https://blog.ethereum.org/2026/10/11/blobs-update"/>
    <summary>Empirical measurement of EIP-4844 blob fee burn and rollup settlement latencies.</summary>
    <updated>2026-10-11T10:00:00Z</updated>
    <author>
      <name>Protocol Team</name>
    </author>
  </entry>
</feed>
"""


def test_feed_extractor_rss_parsing():
    extractor = FeedExtractor()
    items = extractor.parse_feed_xml(SAMPLE_RSS_XML, max_items=5)
    assert len(items) == 2
    assert "FOMC statement" in items[0].title
    assert "4.25 to 4.5 percent" in items[0].summary
    assert "federalreserve.gov" in items[0].link


def test_feed_extractor_atom_parsing():
    extractor = FeedExtractor()
    items = extractor.parse_feed_xml(SAMPLE_ATOM_XML, max_items=5)
    assert len(items) == 1
    assert "Cancun-Deneb" in items[0].title
    assert "Protocol Team" in items[0].author
    assert "blobs-update" in items[0].link


def test_research_source_registry_seeding():
    registry = ResearchSourceRegistry()
    sources = registry.list_sources(is_active_only=True)
    assert len(sources) >= 5
    urls = [s["url"] for s in sources]
    assert "https://www.federalreserve.gov/feeds/press_all.xml" in urls
    assert "https://blog.ethereum.org/feed.xml" in urls


def test_due_for_crawl_and_record_success():
    registry = ResearchSourceRegistry()
    due = registry.get_sources_due_for_crawl()
    assert len(due) > 0

    first = due[0]
    registry.record_crawl_success(first["source_id"], items_count=3)

    # Recheck
    sources = registry.list_sources(is_active_only=False)
    updated = next(s for s in sources if s["source_id"] == first["source_id"])
    assert updated["total_items_ingested"] >= 3
    assert updated["last_crawled_at"] is not None
