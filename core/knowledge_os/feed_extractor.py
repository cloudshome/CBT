"""
core/knowledge_os/feed_extractor.py
===================================
Robust, SSRF-Safe Multi-Source Feed Extractor (RSS / Atom / Structured Web).
Parses remote and local XML feeds, extracts titles, summaries, timestamps, and full links,
and normalizes them for the Universal Research Ingestion Pipeline.
"""

from __future__ import annotations

import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from typing import Any

from core.knowledge_os.web_search_agent import (
    DEFAULT_TIMEOUT_SECS,
    MAX_RESPONSE_BYTES,
    SecurityValidationError,
    validate_url_security,
)

logger = logging.getLogger("sky.knowledge_os.feed_extractor")


@dataclass
class FeedItem:
    title: str
    link: str
    summary: str
    published_at: str
    author: str = ""
    guid: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FeedExtractor:
    """
    Parses RSS 2.0 and Atom feeds safely under SSRF and size constraints.
    """

    def fetch_feed_items(self, feed_url: str, max_items: int = 10) -> list[FeedItem]:
        """
        Fetches and parses feed items from an RSS/Atom URL.
        """
        # 1. Enforce strict SSRF protection
        try:
            validate_url_security(feed_url)
        except SecurityValidationError as e:
            logger.warning("FeedExtractor rejected unsafe feed URL '%s': %s", feed_url, e)
            return []

        # 2. Fetch with bounded response size and timeout
        req = urllib.request.Request(
            feed_url,
            headers={
                "User-Agent": "SKY-Research-Sentinel/1.0 (+https://cbt.quant/bot; institutional research)",
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECS) as resp:
                content_bytes = resp.read(MAX_RESPONSE_BYTES + 1)
                if len(content_bytes) > MAX_RESPONSE_BYTES:
                    logger.warning("Feed '%s' exceeded %d bytes limit, truncated.", feed_url, MAX_RESPONSE_BYTES)
                    content_bytes = content_bytes[:MAX_RESPONSE_BYTES]
                xml_text = content_bytes.decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch feed '%s': %s", feed_url, exc)
            return []

        # 3. Parse XML
        return self.parse_feed_xml(xml_text, max_items=max_items)

    def parse_feed_xml(self, xml_text: str, max_items: int = 10) -> list[FeedItem]:
        """
        Parses XML string into standardized FeedItem dataclasses.
        Supports both RSS 2.0 and Atom feeds.
        """
        items: list[FeedItem] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as pe:
            logger.warning("XML parse error in feed: %s", pe)
            return items

        # Normalize tag lookup
        tag = root.tag.lower()

        # Case A: Atom feed (<feed xmlns="http://www.w3.org/2005/Atom">)
        if "feed" in tag:
            # Handle potential namespaces
            ns = ""
            if "}" in root.tag:
                ns = root.tag.split("}")[0] + "}"

            entries = root.findall(f"{ns}entry")
            for entry in entries[:max_items]:
                title_elem = entry.find(f"{ns}title")
                title = title_elem.text.strip() if title_elem is not None and title_elem.text else "Untitled Entry"

                # Link in atom is typically in attribute href
                link = ""
                link_elem = entry.find(f"{ns}link")
                if link_elem is not None:
                    link = link_elem.attrib.get("href", "")
                    if not link and link_elem.text:
                        link = link_elem.text.strip()

                summary_elem = entry.find(f"{ns}summary") or entry.find(f"{ns}content")
                summary = summary_elem.text.strip() if summary_elem is not None and summary_elem.text else ""

                pub_elem = entry.find(f"{ns}published") or entry.find(f"{ns}updated")
                pub_date = pub_elem.text.strip() if pub_elem is not None and pub_elem.text else ""

                author_elem = entry.find(f"{ns}author/{ns}name")
                author = author_elem.text.strip() if author_elem is not None and author_elem.text else ""

                items.append(
                    FeedItem(
                        title=title,
                        link=link,
                        summary=summary,
                        published_at=pub_date,
                        author=author,
                    )
                )

        # Case B: RSS 2.0 (<rss version="2.0"><channel><item>...</item></channel></rss>)
        else:
            channel = root.find("channel")
            raw_items = channel.findall("item") if channel is not None else root.findall(".//item")

            for item in raw_items[:max_items]:
                title_elem = item.find("title")
                title = title_elem.text.strip() if title_elem is not None and title_elem.text else "Untitled Entry"

                link_elem = item.find("link")
                link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""

                desc_elem = item.find("description")
                summary = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""

                pub_elem = item.find("pubDate")
                pub_date = pub_elem.text.strip() if pub_elem is not None and pub_elem.text else ""

                guid_elem = item.find("guid")
                guid = guid_elem.text.strip() if guid_elem is not None and guid_elem.text else ""

                items.append(
                    FeedItem(
                        title=title,
                        link=link,
                        summary=summary,
                        published_at=pub_date,
                        guid=guid,
                    )
                )

        return items


# Singleton instance
feed_extractor = FeedExtractor()
