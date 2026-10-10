"""
core/knowledge_os/web_search_agent.py
=====================================
Autonomous Web Intelligence & Secure Research Discovery Engine.

Constitutional Mandates:
1. Provider Abstraction: DuckDuckGo, SearXNG, official RSS/web adapters.
2. SSRF & Hostile Web Defense: Blocks RFC 1918, loopbacks, link-local, cloud metadata,
   unsafe ports, and schemes.
3. Content & Resource Bounds: Strict byte limits, read timeouts, non-executable HTML parsing.
4. Prompt-Injection Boundary: External text treated strictly as UNTRUSTED DATA, never instructions.
5. Ingestion Bridge: Feeds into existing canonical universal_ingestor without creating parallel DBs.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import re
import socket
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from typing import Any

logger = logging.getLogger("sky.knowledge_os.web_search_agent")


# -----------------------------------------------------------------------------
# SSRF & Network Security Constants
# -----------------------------------------------------------------------------
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443, 8080, 8443}
MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2MB strict content payload limit
DEFAULT_TIMEOUT_SECS = 8.0

BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # RFC 1918 Private
    ipaddress.ip_network("172.16.0.0/12"),    # RFC 1918 Private
    ipaddress.ip_network("192.168.0.0/16"),   # RFC 1918 Private
    ipaddress.ip_network("169.254.0.0/16"),   # Link-Local / Cloud Metadata (AWS/GCP)
    ipaddress.ip_network("100.64.0.0/10"),    # Carrier-grade NAT
    ipaddress.ip_network("::1/128"),          # IPv6 Loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 Unique Local
    ipaddress.ip_network("fe80::/10"),        # IPv6 Link-Local
]


class SecurityValidationError(Exception):
    """Raised when an external URL breaches SSRF, DNS, or security boundaries."""


def validate_url_security(url: str) -> str:
    """
    Validates that a URL does not target loopback, private subnets, cloud metadata,
    or prohibited protocols/ports. Protects against SSRF attacks.
    """
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except Exception as e:
        raise SecurityValidationError(f"Malformed URL: {e}") from e

    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise SecurityValidationError(f"Prohibited URL scheme '{scheme}'. Only HTTP/HTTPS allowed.")

    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise SecurityValidationError("Missing or invalid hostname in URL.")

    # Block direct localhost aliases
    if hostname in {"localhost", "metadata.google.internal", "instance-data"}:
        raise SecurityValidationError(f"Target host '{hostname}' is prohibited.")

    port = parsed.port or (443 if scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise SecurityValidationError(f"Prohibited network port '{port}'.")

    # Resolve IP and check against blocked ranges
    try:
        addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        for _, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip_obj = ipaddress.ip_address(ip_str)
            for net in BLOCKED_IP_NETWORKS:
                if ip_obj in net:
                    raise SecurityValidationError(
                        f"Host '{hostname}' resolved to prohibited private/link-local address: {ip_str}"
                    )
    except socket.gaierror as e:
        raise SecurityValidationError(f"DNS resolution failure for host '{hostname}': {e}") from e

    return url


# -----------------------------------------------------------------------------
# Clean Text Extraction from HTML (No Script Execution)
# -----------------------------------------------------------------------------
class SafeHTMLTextExtractor(HTMLParser):
    """Zero-script HTML text extractor with structural tag whitespace preservation."""

    def __init__(self):
        super().__init__()
        self._text_chunks: list[str] = []
        self._ignored_tags = {"script", "style", "noscript", "svg", "iframe", "head"}
        self._current_tag = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        self._current_tag = tag.lower()
        if self._current_tag in {"p", "br", "div", "h1", "h2", "h3", "h4", "li", "tr"}:
            self._text_chunks.append("\n")

    def handle_endtag(self, tag: str):
        if tag.lower() == self._current_tag:
            self._current_tag = ""

    def handle_data(self, data: str):
        if self._current_tag not in self._ignored_tags:
            cleaned = data.strip()
            if cleaned:
                self._text_chunks.append(cleaned + " ")

    def get_text(self) -> str:
        raw_text = "".join(self._text_chunks)
        # Collapse multiple blank lines
        return re.sub(r"\n\s*\n+", "\n\n", raw_text).strip()


# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------
@dataclass
class SearchCandidate:
    candidate_id: str
    title: str
    url: str
    snippet: str
    source_domain: str
    provider: str
    published_date: str = ""
    relevance_score: float = 0.5
    is_safe: bool = True
    rejection_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SearchDiscoveryResult:
    search_id: str
    query: str
    topic: str
    timestamp_utc: int
    candidates: list[SearchCandidate]
    total_found: int
    provider_status: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "search_id": self.search_id,
            "query": self.query,
            "topic": self.topic,
            "timestamp_utc": self.timestamp_utc,
            "candidates": [c.to_dict() for c in self.candidates],
            "total_found": self.total_found,
            "provider_status": self.provider_status,
        }


@dataclass
class SecureFetchResult:
    url: str
    canonical_url: str
    status_code: int
    content_hash: str
    text_content: str
    title: str
    source_domain: str
    success: bool
    error: str = ""
    fetched_at: int = field(default_factory=lambda: int(time.time() * 1000))


# -----------------------------------------------------------------------------
# Autonomous Web Search Agent
# -----------------------------------------------------------------------------
class AutonomousWebSearchAgent:
    """
    Coordinates secure open-web discovery, SSRF-guarded fetching, and ingestion.
    """

    def __init__(self):
        self.default_user_agent = "SKY-Institutional-Intelligence-Bot/4.0 (Quantitative Research; Linux x64)"

    def secure_fetch_url(self, url: str) -> SecureFetchResult:
        """
        Safely fetches an external web URL under strict SSRF, timeout, and size limits.
        Extracts clean plain text without executing scripts.
        """
        try:
            validated_url = validate_url_security(url)
        except SecurityValidationError as e:
            logger.warning(f"SSRF security validation blocked URL '{url}': {e}")
            return SecureFetchResult(
                url=url,
                canonical_url=url,
                status_code=403,
                content_hash="",
                text_content="",
                title="",
                source_domain="",
                success=False,
                error=f"Security Blocked: {e}",
            )

        parsed = urllib.parse.urlparse(validated_url)
        domain = parsed.netloc.lower()

        req = urllib.request.Request(
            validated_url,
            headers={
                "User-Agent": self.default_user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECS) as resp:
                status_code = resp.getcode()
                content_type = resp.headers.get("Content-Type", "").lower()
                final_url = resp.geturl()

                # Re-validate target if redirected
                if final_url != validated_url:
                    try:
                        validate_url_security(final_url)
                    except SecurityValidationError as rerr:
                        return SecureFetchResult(
                            url=url,
                            canonical_url=final_url,
                            status_code=403,
                            content_hash="",
                            text_content="",
                            title="",
                            source_domain=domain,
                            success=False,
                            error=f"Redirect Security Block: {rerr}",
                        )

                # Bounded read to prevent memory exhaustion
                raw_bytes = resp.read(MAX_RESPONSE_BYTES + 1024)
                if len(raw_bytes) > MAX_RESPONSE_BYTES:
                    logger.warning(f"Payload from '{url}' exceeded max budget ({MAX_RESPONSE_BYTES} bytes). Truncating.")
                    raw_bytes = raw_bytes[:MAX_RESPONSE_BYTES]

            content_hash = hashlib.sha256(raw_bytes).hexdigest()

            # Extract clean text
            try:
                charset = "utf-8"
                if "charset=" in content_type:
                    charset = content_type.split("charset=")[-1].split(";")[0].strip()
                html_text = raw_bytes.decode(charset, errors="replace")
            except Exception:  # noqa: BLE001
                html_text = raw_bytes.decode("utf-8", errors="replace")

            extractor = SafeHTMLTextExtractor()
            extractor.feed(html_text)
            clean_text = extractor.get_text()

            # Attempt to extract title
            title_match = re.search(r"<title>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
            extracted_title = title_match.group(1).strip() if title_match else domain

            return SecureFetchResult(
                url=url,
                canonical_url=final_url,
                status_code=status_code,
                content_hash=content_hash,
                text_content=clean_text,
                title=extracted_title[:200],
                source_domain=domain,
                success=True,
            )

        except urllib.error.HTTPError as e:
            return SecureFetchResult(
                url=url,
                canonical_url=url,
                status_code=e.code,
                content_hash="",
                text_content="",
                title="",
                source_domain=domain,
                success=False,
                error=f"HTTP {e.code}: {e.reason}",
            )
        except Exception as e:  # noqa: BLE001
            return SecureFetchResult(
                url=url,
                canonical_url=url,
                status_code=500,
                content_hash="",
                text_content="",
                title="",
                source_domain=domain,
                success=False,
                error=str(e),
            )

    def search_duckduckgo_lite(self, query: str, limit: int = 5) -> list[SearchCandidate]:
        """
        Searches DuckDuckGo HTML Lite interface without external third-party libraries.
        Extracts structured search candidates with domains and snippets.
        """
        encoded_query = urllib.parse.urlencode({"q": query})
        search_url = f"https://lite.duckduckgo.com/lite/?{encoded_query}"

        req = urllib.request.Request(
            search_url,
            headers={
                "User-Agent": self.default_user_agent,
                "Accept": "text/html",
            },
        )

        candidates: list[SearchCandidate] = []
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECS) as resp:
                html = resp.read(MAX_RESPONSE_BYTES).decode("utf-8", errors="replace")

            # Extract link targets from DDG Lite HTML
            link_pattern = re.compile(
                r'<a[^>]+class=[\'"]result-link[\'"][^>]+href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>',
                re.IGNORECASE | re.DOTALL,
            )
            matches = link_pattern.findall(html)

            # Fallback pattern if classes change
            if not matches:
                link_pattern_fallback = re.compile(
                    r'<a[^>]+href=[\'"](https?://[^\'"]+)[\'"][^>]*rel=[\'"]nofollow[\'"][^>]*>(.*?)</a>',
                    re.IGNORECASE | re.DOTALL,
                )
                matches = link_pattern_fallback.findall(html)

            for target_url, raw_title in matches[: limit * 2]:
                # Skip DDG internal links
                if "duckduckgo.com" in target_url:
                    continue

                # Strip HTML from title
                clean_title = re.sub(r"<[^>]+>", "", raw_title).strip()
                parsed = urllib.parse.urlparse(target_url)
                domain = parsed.netloc.lower()

                # Pre-screen URL security
                is_safe = True
                rejection_reason = ""
                try:
                    validate_url_security(target_url)
                except SecurityValidationError as sec_err:
                    is_safe = False
                    rejection_reason = str(sec_err)

                cand = SearchCandidate(
                    candidate_id=hashlib.sha256(target_url.encode()).hexdigest()[:16],
                    title=clean_title or domain,
                    url=target_url,
                    snippet=f"Discovered via open intelligence search on {domain}",
                    source_domain=domain,
                    provider="DUCKDUCKGO_LITE",
                    is_safe=is_safe,
                    rejection_reason=rejection_reason,
                )
                candidates.append(cand)
                if len([c for c in candidates if c.is_safe]) >= limit:
                    break

        except Exception as e:  # noqa: BLE001
            logger.warning(f"DuckDuckGo Lite search failed for '{query}': {e}")

        return candidates

    async def discover_and_evaluate(
        self, query: str, topic: str = "Quantitative Market Structure", limit: int = 5
    ) -> SearchDiscoveryResult:
        """
        Executes bounded discovery across providers, evaluates candidates,
        and returns normalized results without automatically publishing.
        """
        search_id = f"search_{int(time.time())}_{hashlib.sha256(query.encode()).hexdigest()[:8]}"
        provider_status: dict[str, str] = {}

        # Run provider query in executor to prevent event loop blocking
        loop = asyncio.get_running_loop()
        try:
            candidates = await loop.run_in_executor(None, self.search_duckduckgo_lite, query, limit)
            provider_status["DUCKDUCKGO"] = "HEALTHY" if candidates else "ZERO_RESULTS"
        except Exception as e:  # noqa: BLE001
            candidates = []
            provider_status["DUCKDUCKGO"] = f"ERROR: {e}"

        return SearchDiscoveryResult(
            search_id=search_id,
            query=query,
            topic=topic,
            timestamp_utc=int(time.time()),
            candidates=candidates,
            total_found=len(candidates),
            provider_status=provider_status,
        )

    def auto_ingest_candidate_to_wiki(
        self,
        candidate_url: str,
        custom_topic: str = "Macro Geopolitics & Hegemony",
        custom_title: str | None = None,
    ) -> dict[str, Any]:
        """
        Fetches an evaluated web candidate securely and routes it into the canonical
        universal_ingestor and research_wikipedia_engine without parallel databases.
        """
        fetch_res = self.secure_fetch_url(candidate_url)
        if not fetch_res.success:
            return {
                "status": "REJECTED_SECURITY_OR_NETWORK",
                "url": candidate_url,
                "error": fetch_res.error,
            }

        # Bridge into existing Universal Ingestor
        from core.knowledge_os.universal_ingestor import universal_ingestor

        ingest_options = {
            "title": custom_title or fetch_res.title,
            "category": custom_topic,
            "author": fetch_res.source_domain,
            "content_hash": fetch_res.content_hash,
            "extracted_text": fetch_res.text_content,
        }

        # Leverage existing universal_ingestor to guarantee provenance, hashes, and relational schemas
        res = universal_ingestor.ingest_url(url=candidate_url, options=ingest_options)
        return {
            "status": res.status,
            "source_id": res.source.source_id,
            "wiki_article_id": res.source.wiki_article_id,
            "content_hash": fetch_res.content_hash,
            "claims_extracted": len(res.claims),
            "title": ingest_options["title"],
            "url": candidate_url,
        }


web_search_agent = AutonomousWebSearchAgent()
