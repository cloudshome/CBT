"""
core/knowledge_os/research_source_registry.py
=============================================
Autonomous Research Source Registry for SKY Knowledge OS.
Maintains curated, high-integrity intelligence feeds (Macroeconomics, Central Banking,
Crypto Architecture, Market Structure) and seeds them idempotently into the database.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

from core.database import db_manager

logger = logging.getLogger("sky.knowledge_os.research_source_registry")


@dataclass
class ResearchFeedSource:
    feed_id: str
    name: str
    url: str
    source_type: str  # RSS_FEED, YOUTUBE_CHANNEL, WEB_SCRAPE
    category: str  # Macro Geopolitics, Monetary & Debt, Crypto Liquidity, Market Structure, Tech/AI
    crawl_interval_hours: int = 24
    is_active: bool = True
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Default Curated Institutional Feeds
DEFAULT_CURATED_SOURCES: list[ResearchFeedSource] = [
    # 1. Macroeconomics & Federal Reserve
    ResearchFeedSource(
        feed_id="src_fed_press",
        name="Federal Reserve Board Press Releases",
        url="https://www.federalreserve.gov/feeds/press_all.xml",
        source_type="RSS_FEED",
        category="Monetary & Debt",
        crawl_interval_hours=12,
        description="Official Federal Reserve monetary policy and FOMC statements.",
    ),
    ResearchFeedSource(
        feed_id="src_bis_speeches",
        name="Bank for International Settlements (BIS) Research",
        url="https://www.bis.org/doclist/rss/speeches.rss",
        source_type="RSS_FEED",
        category="Monetary & Debt",
        crawl_interval_hours=24,
        description="Global central bank reserve research and financial stability papers.",
    ),
    ResearchFeedSource(
        feed_id="src_imf_news",
        name="International Monetary Fund (IMF) News",
        url="https://www.imf.org/en/News/rss",
        source_type="RSS_FEED",
        category="Macro Geopolitics",
        crawl_interval_hours=24,
        description="Multilateral macroeconomic outlook and cross-border capital flows.",
    ),

    # 2. Institutional Crypto Research & Ethereum Foundation
    ResearchFeedSource(
        feed_id="src_eth_blog",
        name="Ethereum Foundation Blog",
        url="https://blog.ethereum.org/feed.xml",
        source_type="RSS_FEED",
        category="Tech/AI",
        crawl_interval_hours=24,
        description="Ethereum core protocol upgrades, consensus layer, and rollup research.",
    ),
    ResearchFeedSource(
        feed_id="src_vitalik_ca",
        name="Vitalik Buterin Research Notes",
        url="https://vitalik.eth.limo/feed.xml",
        source_type="RSS_FEED",
        category="Market Structure",
        crawl_interval_hours=48,
        description="Cryptoeconomic mechanism design and scaling architectures.",
    ),
    ResearchFeedSource(
        feed_id="src_bitcoin_core",
        name="Bitcoin Core Releases & Announcements",
        url="https://bitcoincore.org/en/rss.xml",
        source_type="RSS_FEED",
        category="Crypto Liquidity",
        crawl_interval_hours=48,
        description="Bitcoin protocol changes, mempool telemetry, and soft fork discussions.",
    ),

    # 3. High-Quality YouTube Macro Channels
    ResearchFeedSource(
        feed_id="src_yt_fedwatch",
        name="Macro & Monetary Liquidity Insights",
        url="https://www.youtube.com/@MacroAlf",
        source_type="YOUTUBE_CHANNEL",
        category="Monetary & Debt",
        crawl_interval_hours=72,
        description="Treasury supply dynamics, reverse repo facility, and dollar liquidity.",
    ),
]


class ResearchSourceRegistry:
    """
    Manages persistent source registrations across brain_memory.db and ensures
    the crawler pipeline has active intelligence feeds to query.
    """

    def __init__(self) -> None:
        self._ensure_tables()
        self.seed_default_sources()

    def _ensure_tables(self) -> None:
        """Ensures research_source_registry table exists in brain_memory.db."""
        with db_manager.get_brain_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS research_source_registry (
                    source_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    source_type TEXT NOT NULL,
                    category TEXT NOT NULL,
                    crawl_interval_hours INTEGER NOT NULL DEFAULT 24,
                    last_crawled_at INTEGER,
                    total_items_ingested INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    description TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_reg_sources_active ON research_source_registry (is_active, last_crawled_at);"
            )
            conn.commit()

    def seed_default_sources(self) -> int:
        """Seeds curated feeds into the database idempotently."""
        now_ms = int(time.time() * 1000)
        seeded = 0

        with db_manager.get_brain_conn() as conn:
            for s in DEFAULT_CURATED_SOURCES:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO research_source_registry
                        (source_id, name, url, source_type, category, crawl_interval_hours,
                         is_active, description, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        s.feed_id,
                        s.name,
                        s.url,
                        s.source_type,
                        s.category,
                        s.crawl_interval_hours,
                        1 if s.is_active else 0,
                        s.description,
                        now_ms,
                        now_ms,
                    ),
                )
                if cursor.rowcount > 0:
                    seeded += 1

                # Also synchronize YouTube channels with research_automation_channels table
                if s.source_type == "YOUTUBE_CHANNEL":
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO research_automation_channels
                            (channel_id, url, label, crawl_interval_hours, max_videos_per_crawl,
                             is_active, added_at, updated_at)
                        VALUES (?, ?, ?, ?, 5, 1, ?, ?);
                        """,
                        (s.feed_id, s.url, s.name, s.crawl_interval_hours, now_ms, now_ms),
                    )

            conn.commit()

        if seeded > 0:
            logger.info("ResearchSourceRegistry: Seeded %d curated research sources.", seeded)
        return seeded

    def list_sources(self, is_active_only: bool = True) -> list[dict[str, Any]]:
        """Lists registered intelligence feeds."""
        with db_manager.get_brain_conn() as conn:
            query = "SELECT * FROM research_source_registry"
            if is_active_only:
                query += " WHERE is_active = 1"
            query += " ORDER BY created_at ASC;"
            rows = conn.execute(query).fetchall()
        return [dict(r) for r in rows]

    def get_sources_due_for_crawl(self) -> list[dict[str, Any]]:
        """Finds sources whose last crawl is older than crawl_interval_hours."""
        now_ms = int(time.time() * 1000)
        with db_manager.get_brain_conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM research_source_registry
                WHERE is_active = 1
                  AND (
                    last_crawled_at IS NULL
                    OR last_crawled_at <= (? - crawl_interval_hours * 3600000)
                  )
                ORDER BY last_crawled_at ASC NULLS FIRST;
                """,
                (now_ms,),
            ).fetchall()
        return [dict(r) for r in rows]

    def record_crawl_success(self, source_id: str, items_count: int) -> None:
        """Updates last crawled timestamp and items count."""
        now_ms = int(time.time() * 1000)
        with db_manager.get_brain_conn() as conn:
            conn.execute(
                """
                UPDATE research_source_registry
                SET last_crawled_at = ?,
                    total_items_ingested = total_items_ingested + ?,
                    updated_at = ?
                WHERE source_id = ?;
                """,
                (now_ms, items_count, now_ms, source_id),
            )
            conn.commit()


# Singleton instance
research_source_registry = ResearchSourceRegistry()
