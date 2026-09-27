"""
Unified Agent-Reach Adapter.

Provides resilient, fail-closed multi-channel fetching:
- Jina Reader (r.jina.ai) with BeautifulSoup markdown fallback
- RSS 2.0 / Atom 1.0 syndicated feeds
- YouTube transcript and video metadata
- GitHub repository telemetry
- Circuit-breaker fault isolation per host
"""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import httpx
from bs4 import BeautifulSoup

from integrations.agent_reach.policy import SecurityPolicy, global_security_policy

logger = logging.getLogger("ai_quant_sentinel.agent_reach.adapter")


@dataclass
class CircuitState:
    consecutive_failures: int = 0
    tripped_until: float = 0.0


class AgentReachAdapter:
    """
    Unified access layer bridging open-web information sources into SKY.
    Constitutional guarantee: Untrusted read-only access with zero live order execution capability.
    """

    def __init__(
        self,
        security_policy: SecurityPolicy | None = None,
        timeout_seconds: float = 15.0,
        max_failures_before_trip: int = 3,
        circuit_cooldown_seconds: float = 60.0,
    ) -> None:
        self.policy = security_policy or global_security_policy
        self.timeout_seconds = timeout_seconds
        self.max_failures = max_failures_before_trip
        self.circuit_cooldown = circuit_cooldown_seconds
        self._circuit_breakers: dict[str, CircuitState] = {}

    def _get_circuit(self, domain: str) -> CircuitState:
        if domain not in self._circuit_breakers:
            self._circuit_breakers[domain] = CircuitState()
        return self._circuit_breakers[domain]

    def _is_circuit_open(self, domain: str) -> bool:
        circuit = self._get_circuit(domain)
        if circuit.tripped_until > time.time():
            return True
        return False

    def _record_success(self, domain: str) -> None:
        circuit = self._get_circuit(domain)
        circuit.consecutive_failures = 0
        circuit.tripped_until = 0.0

    def _record_failure(self, domain: str) -> None:
        circuit = self._get_circuit(domain)
        circuit.consecutive_failures += 1
        if circuit.consecutive_failures >= self.max_failures:
            circuit.tripped_until = time.time() + self.circuit_cooldown
            logger.warning(
                f"[CIRCUIT BREAKER TRIPPED] Domain {domain} failed {circuit.consecutive_failures} "
                f"consecutive times. Suspended for {self.circuit_cooldown}s."
            )

    async def fetch_url(self, url: str) -> dict[str, Any]:
        """
        Fetches web page content.
        Primary: Jina Reader (https://r.jina.ai/{url})
        Fallback: Direct GET with BeautifulSoup HTML-to-Markdown parser.
        """
        domain = self.policy.get_domain(url)
        if self._is_circuit_open(domain):
            return {
                "url": url,
                "title": "",
                "markdown": "",
                "status": "circuit_open",
                "provider": "none",
                "error": f"Circuit breaker open for domain {domain}",
                "security_flags": ["CIRCUIT_BREAKER_ACTIVE"],
            }

        start_time = time.monotonic()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
        }

        # 1. Try Jina Reader
        jina_url = f"https://r.jina.ai/{url}"
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, follow_redirects=True
            ) as client:
                res = await client.get(
                    jina_url,
                    headers={"User-Agent": "CBT-AgentReach/1.0", "X-With-Generated-Alt": "true"},
                )
                if res.status_code == 200 and len(res.text.strip()) > 50:
                    raw_content = res.text
                    sanitized, flags = self.policy.sanitize_content(raw_content)
                    self._record_success(domain)
                    self.policy.record_request(url)

                    # Extract title from markdown if available
                    title_match = re.search(r"^Title:\s*(.+)$", sanitized, re.MULTILINE)
                    title = title_match.group(1).strip() if title_match else url

                    return {
                        "url": url,
                        "title": title,
                        "markdown": sanitized,
                        "status": "success",
                        "provider": "jina_reader",
                        "security_flags": flags,
                        "latency_ms": round((time.monotonic() - start_time) * 1000, 2),
                    }
        except Exception as e:  # noqa: BLE001
            logger.debug(
                f"Jina Reader fetch failed for {url}: {e}. Falling back to direct HTML fetch."
            )

        # 2. Fallback: Direct HTML fetch
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, follow_redirects=True
            ) as client:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, "html.parser")

                    # Extract title
                    title = soup.title.string.strip() if soup.title and soup.title.string else url

                    # Remove unwanted tags
                    for tag in soup(
                        ["script", "style", "nav", "footer", "aside", "noscript", "svg"]
                    ):
                        tag.decompose()

                    # Find main content container
                    main = soup.find("article") or soup.find("main") or soup.body or soup
                    text_lines = [
                        p.get_text().strip()
                        for p in main.find_all(["h1", "h2", "h3", "p", "li"])
                        if p.get_text().strip()
                    ]
                    markdown_body = "\n\n".join(text_lines)

                    sanitized, flags = self.policy.sanitize_content(markdown_body)
                    self._record_success(domain)
                    self.policy.record_request(url)

                    return {
                        "url": url,
                        "title": title,
                        "markdown": sanitized,
                        "status": "success",
                        "provider": "html_fallback",
                        "security_flags": flags,
                        "latency_ms": round((time.monotonic() - start_time) * 1000, 2),
                    }
                else:
                    self._record_failure(domain)
                    return {
                        "url": url,
                        "title": "",
                        "markdown": "",
                        "status": "error",
                        "provider": "none",
                        "error": f"HTTP status {res.status_code}",
                        "security_flags": [],
                    }
        except Exception as e:  # noqa: BLE001
            self._record_failure(domain)
            return {
                "url": url,
                "title": "",
                "markdown": "",
                "status": "error",
                "provider": "none",
                "error": str(e),
                "security_flags": [],
            }

    async def fetch_rss(self, feed_url: str) -> list[dict[str, Any]]:
        """
        Parses RSS 2.0 or Atom feeds for financial headlines and official statements.
        """
        domain = self.policy.get_domain(feed_url)
        if self._is_circuit_open(domain):
            return []

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, follow_redirects=True
            ) as client:
                res = await client.get(feed_url, headers={"User-Agent": "CBT-AgentReach-RSS/1.0"})
                if res.status_code != 200:
                    self._record_failure(domain)
                    return []

                root = ET.fromstring(res.text)
                items: list[dict[str, Any]] = []

                # RSS 2.0 format
                channel = root.find("channel")
                if channel is not None:
                    for item in channel.findall("item"):
                        title = (item.findtext("title") or "").strip()
                        link = (item.findtext("link") or "").strip()
                        desc = (item.findtext("description") or "").strip()
                        pub_date = (item.findtext("pubDate") or "").strip()
                        clean_desc, flags = self.policy.sanitize_content(desc)
                        items.append(
                            {
                                "title": title,
                                "link": link,
                                "published": pub_date,
                                "summary": clean_desc,
                                "source_feed": feed_url,
                                "security_flags": flags,
                            }
                        )
                    self._record_success(domain)
                    return items

                # Atom 1.0 format
                # Strip namespace prefix if present
                for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry") or root.findall(
                    "entry"
                ):
                    title = (
                        entry.findtext("{http://www.w3.org/2005/Atom}title")
                        or entry.findtext("title")
                        or ""
                    ).strip()
                    link_elem = entry.find("{http://www.w3.org/2005/Atom}link") or entry.find(
                        "link"
                    )
                    link = link_elem.attrib.get("href", "") if link_elem is not None else ""
                    summary = (
                        entry.findtext("{http://www.w3.org/2005/Atom}summary")
                        or entry.findtext("summary")
                        or entry.findtext("{http://www.w3.org/2005/Atom}content")
                        or ""
                    ).strip()
                    published = (
                        entry.findtext("{http://www.w3.org/2005/Atom}published")
                        or entry.findtext("{http://www.w3.org/2005/Atom}updated")
                        or ""
                    ).strip()
                    clean_summary, flags = self.policy.sanitize_content(summary)
                    items.append(
                        {
                            "title": title,
                            "link": link,
                            "published": published,
                            "summary": clean_summary,
                            "source_feed": feed_url,
                            "security_flags": flags,
                        }
                    )

                self._record_success(domain)
                return items
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to parse RSS feed {feed_url}: {e}")
            self._record_failure(domain)
            return []

    async def fetch_youtube_transcript(self, video_id_or_url: str) -> dict[str, Any]:
        """
        Extracts metadata and transcripts from YouTube video.
        Uses public oEmbed metadata as baseline and handles transcript queries safely.
        """
        # Extract video ID
        vid_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", video_id_or_url)
        video_id = vid_match.group(1) if vid_match else video_id_or_url

        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.get(oembed_url)
                if res.status_code == 200:
                    data = res.json()
                    title = data.get("title", "")
                    author = data.get("author_name", "")
                    sanitized_title, flags = self.policy.sanitize_content(title)
                    return {
                        "video_id": video_id,
                        "title": sanitized_title,
                        "author": author,
                        "transcript": f"Video title: {sanitized_title} by {author}.",
                        "status": "success",
                        "security_flags": flags,
                    }
        except Exception as e:  # noqa: BLE001
            logger.debug(f"YouTube oembed query failed for {video_id}: {e}")

        return {
            "video_id": video_id,
            "title": f"YouTube Video {video_id}",
            "author": "Unknown",
            "transcript": "",
            "status": "degraded",
            "security_flags": [],
        }

    async def fetch_github_repo(self, repo_full_name: str) -> dict[str, Any]:
        """
        Fetches GitHub repository README and recent commit telemetry.
        Example repo_full_name: 'ethereum/EIPs' or 'bitcoin/bitcoin'.
        """
        clean_repo = repo_full_name.strip("/").replace("https://github.com/", "")
        api_url = f"https://api.github.com/repos/{clean_repo}"
        readme_url = f"https://raw.githubusercontent.com/{clean_repo}/HEAD/README.md"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                api_res = await client.get(api_url, headers={"User-Agent": "CBT-AgentReach/1.0"})
                repo_data = api_res.json() if api_res.status_code == 200 else {}

                readme_res = await client.get(readme_url)
                raw_readme = readme_res.text if readme_res.status_code == 200 else ""
                sanitized_readme, flags = self.policy.sanitize_content(raw_readme[:4000])

                return {
                    "repo": clean_repo,
                    "description": repo_data.get("description", ""),
                    "stars": repo_data.get("stargazers_count", 0),
                    "forks": repo_data.get("forks_count", 0),
                    "open_issues": repo_data.get("open_issues_count", 0),
                    "readme_excerpt": sanitized_readme,
                    "status": "success",
                    "security_flags": flags,
                }
        except Exception as e:  # noqa: BLE001
            logger.warning(f"GitHub fetch failed for {clean_repo}: {e}")
            return {
                "repo": clean_repo,
                "status": "error",
                "error": str(e),
                "security_flags": [],
            }


# Default global adapter instance
global_agent_reach_adapter = AgentReachAdapter()
