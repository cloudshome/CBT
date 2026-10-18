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
import uuid
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
    ipaddress.ip_network("0.0.0.0/8"),  # This host on this network (RFC 1122)
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("10.0.0.0/8"),  # RFC 1918 Private
    ipaddress.ip_network("172.16.0.0/12"),  # RFC 1918 Private
    ipaddress.ip_network("192.168.0.0/16"),  # RFC 1918 Private
    ipaddress.ip_network("169.254.0.0/16"),  # Link-Local / Cloud Metadata (AWS/GCP)
    ipaddress.ip_network("100.64.0.0/10"),  # Carrier-grade NAT
    ipaddress.ip_network("198.18.0.0/15"),  # Benchmark testing (RFC 2544)
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast (RFC 5771)
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved for future use (RFC 1112)
    ipaddress.ip_network("::/128"),  # IPv6 Unspecified
    ipaddress.ip_network("::1/128"),  # IPv6 Loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 Unique Local
    ipaddress.ip_network("fe80::/10"),  # IPv6 Link-Local
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------------
# Phase 2: Bounded Multi-Worker Data Contracts (claude-ads pattern)
# -----------------------------------------------------------------------------
@dataclass
class SearchPlanResult:
    topic: str
    query_variants: list[str]
    category: str
    target_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CleanTextDocument:
    url: str
    canonical_url: str
    source_sha256: str
    title: str
    author: str
    domain: str
    clean_markdown: str
    word_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractedClaimSet:
    source_url: str
    source_sha256: str
    claims: list[dict[str, Any]]
    injection_attempts_detected: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchCriticReport:
    candidate_title: str
    summary: str
    novel_claims_count: int
    contradictions_detected: list[dict[str, Any]]
    corroborations_detected: list[dict[str, Any]]
    triage_item_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BoundedResearchCycleResult:
    cycle_id: str
    topic: str
    query: str
    candidates_found: int
    documents_fetched: int
    claims_extracted: int
    critic_report: ResearchCriticReport | None
    worker_durations_ms: dict[str, float]
    status: str
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.critic_report:
            d["critic_report"] = self.critic_report.to_dict()
        return d


# -----------------------------------------------------------------------------
# Phase 2: Five Bounded Workers
# -----------------------------------------------------------------------------
class QueryPlannerWorker:
    """Worker 1: Formulates structured, multi-variant queries and determines taxonomy category."""

    def plan(self, topic: str, user_query: str | None = None, limit: int = 3) -> SearchPlanResult:
        variants = []
        if user_query and user_query.strip():
            variants.append(user_query.strip())
        variants.extend(
            [
                f"{topic} empirical market structure",
                f"{topic} quantitative research alpha",
                f"{topic} liquidity order flow analysis",
            ]
        )
        unique_variants = list(dict.fromkeys(variants))[:3]

        t_lower = topic.lower()
        if any(k in t_lower for k in ["macro", "tga", "fed", "dollar", "geopolitic", "hegemony"]):
            category = "Macro Geopolitics & Hegemony"
        elif any(k in t_lower for k in ["debt", "rate", "yield", "treasury", "inflation"]):
            category = "Monetary & Debt"
        elif any(k in t_lower for k in ["liquidity", "ethena", "basis", "funding", "perp", "amm"]):
            category = "Crypto Liquidity"
        elif any(
            k in t_lower for k in ["microstructure", "fvg", "order book", "vpin", "l2", "slippage"]
        ):
            category = "Market Structure"
        else:
            category = "Alpha Factor"

        return SearchPlanResult(
            topic=topic,
            query_variants=unique_variants,
            category=category,
            target_count=limit,
        )


class SecureFetchWorker:
    """Worker 2: SSRF-guarded HTTP fetcher with domain cooldown circuit breaker."""

    def __init__(self, user_agent: str):
        self.user_agent = user_agent
        self._domain_failures: dict[str, int] = {}
        self._domain_cooldowns: dict[str, float] = {}

    def fetch(self, url: str) -> SecureFetchResult:
        # Check domain circuit breaker before attempting DNS resolution
        try:
            initial_parsed = urllib.parse.urlparse(url.strip())
            initial_domain = (initial_parsed.hostname or initial_parsed.netloc or "").lower()
            now = time.time()
            if (
                initial_domain
                and initial_domain in self._domain_cooldowns
                and self._domain_cooldowns[initial_domain] > now
            ):
                return SecureFetchResult(
                    url=url,
                    canonical_url=url,
                    status_code=429,
                    content_hash="",
                    text_content="",
                    title="",
                    source_domain=initial_domain,
                    success=False,
                    error="Domain in temporary cooldown (circuit breaker)",
                )
        except Exception:
            pass

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
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECS) as resp:
                status_code = resp.getcode()
                content_type = resp.headers.get("Content-Type", "").lower()
                final_url = resp.geturl()

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

                raw_bytes = resp.read(MAX_RESPONSE_BYTES + 1024)
                if len(raw_bytes) > MAX_RESPONSE_BYTES:
                    logger.warning(
                        f"Payload from '{url}' exceeded max budget ({MAX_RESPONSE_BYTES} bytes). Truncating."
                    )
                    raw_bytes = raw_bytes[:MAX_RESPONSE_BYTES]

            content_hash = hashlib.sha256(raw_bytes).hexdigest()

            try:
                charset = "utf-8"
                if "charset=" in content_type:
                    charset = content_type.split("charset=")[-1].split(";")[0].strip()
                html_text = raw_bytes.decode(charset, errors="replace")
            except Exception:
                html_text = raw_bytes.decode("utf-8", errors="replace")

            extractor = SafeHTMLTextExtractor()
            extractor.feed(html_text)
            clean_text = extractor.get_text()

            title_match = re.search(r"<title>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
            extracted_title = title_match.group(1).strip() if title_match else domain

            # Reset failures on success
            self._domain_failures[domain] = 0

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
            self._record_domain_failure(domain)
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
        except Exception as e:
            self._record_domain_failure(domain)
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

    def _record_domain_failure(self, domain: str) -> None:
        count = self._domain_failures.get(domain, 0) + 1
        self._domain_failures[domain] = count
        if count >= 3:
            self._domain_cooldowns[domain] = time.time() + 300.0


class ExtractionWorker:
    """Worker 3: Converts raw fetched payloads into clean, normalized markdown documents."""

    def normalize(self, fetch_res: SecureFetchResult) -> CleanTextDocument:
        raw_text = fetch_res.text_content
        lines = [line.strip() for line in raw_text.splitlines() if len(line.strip()) > 0]
        meaningful_lines = [
            line
            for line in lines
            if not any(
                b in line.lower()
                for b in [
                    "cookie policy",
                    "terms of service",
                    "all rights reserved",
                    "subscribe now",
                    "accept cookies",
                ]
            )
        ]
        clean_markdown = "\n\n".join(meaningful_lines)
        word_count = len(clean_markdown.split())

        return CleanTextDocument(
            url=fetch_res.url,
            canonical_url=fetch_res.canonical_url,
            source_sha256=fetch_res.content_hash,
            title=fetch_res.title,
            author=fetch_res.source_domain,
            domain=fetch_res.source_domain,
            clean_markdown=clean_markdown,
            word_count=word_count,
        )


INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore\s+(all\s+)?previous\s+instructions"),
    re.compile(r"(?i)system\s*:\s*"),
    re.compile(r"(?i)system\s*prompt\s*override"),
    re.compile(r"(?i)you\s+are\s+now\s+an?\s+execution\s+(bot|agent)"),
    re.compile(r"(?i)place\s+(a\s+)?(market\s+)?(buy|sell)\s+order"),
]


class ClaimExtractionWorker:
    """Worker 4: Untrusted data firewall & atomic epistemic claim extractor."""

    def extract_claims(self, doc: CleanTextDocument) -> ExtractedClaimSet:
        text = doc.clean_markdown
        injection_count = 0

        # Scan and neutralize injection strings
        for pat in INJECTION_PATTERNS:
            matches = pat.findall(text)
            if matches:
                injection_count += len(matches)
                text = pat.sub("[REDACTED_SECURITY_PROMPT_INJECTION]", text)

        sentences = re.split(r"(?<=[.!?])\s+", text)
        claims: list[dict[str, Any]] = []

        quant_keywords = [
            "%",
            "bps",
            "basis point",
            "sharpe",
            "win rate",
            "alpha",
            "drawdown",
            "liquidity",
            "imbalance",
            "ratio",
            "correlation",
            "volatility",
            "premium",
            "discount",
            "order flow",
            "spread",
            "reserve",
        ]

        for s in sentences:
            s_clean = s.strip()
            if len(s_clean) < 25 or len(s_clean) > 300:
                continue

            s_lower = s_clean.lower()
            if any(kw in s_lower for kw in quant_keywords):
                if any(
                    w in s_lower
                    for w in [
                        "historically",
                        "measured",
                        "according to",
                        "fred",
                        "sec filing",
                        "data shows",
                        "index",
                    ]
                ):
                    epistemic = "FACT"
                    conf = 0.90
                elif any(
                    w in s_lower
                    for w in [
                        "strategy",
                        "signal",
                        "expect",
                        "predict",
                        "indicates",
                        "suggests",
                        "opportunity",
                        "edge",
                    ]
                ):
                    epistemic = "HYPOTHESIS"
                    conf = 0.65
                elif any(w in s_lower for w in ["assume", "assuming", "baseline fee", "slippage"]):
                    epistemic = "ASSUMPTION"
                    conf = 0.80
                elif any(w in s_lower for w in ["therefore", "implies", "deduces", "correlates"]):
                    epistemic = "INFERENCE"
                    conf = 0.70
                else:
                    epistemic = "UNVERIFIED"
                    conf = 0.50

                claims.append(
                    {
                        "claim_id": f"claim_{doc.source_sha256[:8]}_{len(claims) + 1:02d}",
                        "speaker_claim": s_clean,
                        "epistemic_status": epistemic,
                        "confidence_score": conf,
                        "verbatim_quote": s_clean,
                        "source_url": doc.url,
                        "source_domain": doc.domain,
                    }
                )

            if len(claims) >= 10:
                break

        return ExtractedClaimSet(
            source_url=doc.url,
            source_sha256=doc.source_sha256,
            claims=claims,
            injection_attempts_detected=injection_count,
        )


class ResearchCriticWorker:
    """Worker 5: Cross-references claims against research_wiki.db and stages to triage inbox."""

    def evaluate_and_stage(
        self,
        doc: CleanTextDocument,
        claim_set: ExtractedClaimSet,
        category: str,
    ) -> ResearchCriticReport:
        from core.knowledge_os.research_wikipedia import research_wikipedia_engine

        existing_claims = []
        try:
            with research_wikipedia_engine._get_connection() as conn:
                rows = conn.execute(
                    "SELECT speaker_claim, claim_type FROM research_claims LIMIT 100;"
                ).fetchall()
                existing_claims = [dict(r) for r in rows]
        except Exception:
            pass

        novel_claims_count = len(claim_set.claims)
        contradictions = []
        corroborations = []

        for c in claim_set.claims:
            c_text_lower = c["speaker_claim"].lower()
            for ec in existing_claims:
                ec_text_lower = ec.get("speaker_claim", "").lower()
                common_words = set(c_text_lower.split()) & set(ec_text_lower.split())
                if len(common_words) >= 4:
                    if ("bullish" in c_text_lower and "bearish" in ec_text_lower) or (
                        "positive" in c_text_lower and "negative" in ec_text_lower
                    ):
                        contradictions.append(
                            {"new_claim": c["speaker_claim"], "existing_claim": ec["speaker_claim"]}
                        )
                    else:
                        corroborations.append(
                            {"new_claim": c["speaker_claim"], "existing_claim": ec["speaker_claim"]}
                        )

        summary = (
            (doc.clean_markdown[:280] + "...")
            if len(doc.clean_markdown) > 280
            else doc.clean_markdown
        )
        triage_id = research_wikipedia_engine.add_to_triage_inbox(
            candidate_title=doc.title,
            candidate_summary=summary or "Autonomous research discovery candidate.",
            source_url=doc.url,
            source_domain=doc.domain,
            proposed_category=category,
            extracted_claims=claim_set.claims,
            source_id=f"src_{doc.source_sha256[:12]}",
        )

        return ResearchCriticReport(
            candidate_title=doc.title,
            summary=summary,
            novel_claims_count=novel_claims_count,
            contradictions_detected=contradictions,
            corroborations_detected=corroborations,
            triage_item_id=triage_id,
        )


# -----------------------------------------------------------------------------
# Master Autonomous Web Search Agent
# -----------------------------------------------------------------------------
class AutonomousWebSearchAgent:
    """
    Coordinates secure open-web discovery, SSRF-guarded fetching, and multi-worker research.
    """

    def __init__(self):
        self.default_user_agent = (
            "SKY-Institutional-Intelligence-Bot/4.0 (Quantitative Research; Linux x64)"
        )
        # Instantiate 5 Bounded Workers
        self.query_planner = QueryPlannerWorker()
        self.secure_fetcher = SecureFetchWorker(user_agent=self.default_user_agent)
        self.extraction_worker = ExtractionWorker()
        self.claim_extractor = ClaimExtractionWorker()
        self.critic_worker = ResearchCriticWorker()

    def secure_fetch_url(self, url: str) -> SecureFetchResult:
        """Safely fetches external URL via SecureFetchWorker."""
        return self.secure_fetcher.fetch(url)

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

        except Exception as e:
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
        except Exception as e:
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

    async def execute_bounded_research_cycle(
        self, topic: str, query: str | None = None, limit: int = 3
    ) -> BoundedResearchCycleResult:
        """
        Executes the full 5-worker bounded research pipeline:
        1. QueryPlanner -> 2. SecureFetcher -> 3. Extractor -> 4. ClaimExtractor -> 5. ResearchCritic
        """
        cycle_id = f"cycle_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        durations: dict[str, float] = {}

        # Worker 1: Query Planner
        t0 = time.time()
        plan = self.query_planner.plan(topic=topic, user_query=query, limit=limit)
        durations["query_planner_ms"] = round((time.time() - t0) * 1000, 2)

        # Discovery across variants
        t1 = time.time()
        loop = asyncio.get_running_loop()
        all_candidates: list[SearchCandidate] = []
        for q in plan.query_variants[:2]:
            try:
                cands = await loop.run_in_executor(None, self.search_duckduckgo_lite, q, limit)
                all_candidates.extend(cands)
            except Exception:
                pass
        durations["discovery_ms"] = round((time.time() - t1) * 1000, 2)

        safe_candidates = [c for c in all_candidates if c.is_safe]
        unique_cands = list({c.url: c for c in safe_candidates}.values())[:limit]

        if not unique_cands:
            return BoundedResearchCycleResult(
                cycle_id=cycle_id,
                topic=topic,
                query=query or topic,
                candidates_found=0,
                documents_fetched=0,
                claims_extracted=0,
                critic_report=None,
                worker_durations_ms=durations,
                status="ZERO_CANDIDATES",
            )

        # Worker 2: Secure Fetcher (fetch top candidate)
        t2 = time.time()
        top_cand = unique_cands[0]
        fetch_res = await loop.run_in_executor(None, self.secure_fetcher.fetch, top_cand.url)
        durations["secure_fetcher_ms"] = round((time.time() - t2) * 1000, 2)

        if not fetch_res.success:
            return BoundedResearchCycleResult(
                cycle_id=cycle_id,
                topic=topic,
                query=query or topic,
                candidates_found=len(unique_cands),
                documents_fetched=0,
                claims_extracted=0,
                critic_report=None,
                worker_durations_ms=durations,
                status="FETCH_FAILED",
                error=fetch_res.error,
            )

        # Worker 3: Extraction Worker
        t3 = time.time()
        doc = self.extraction_worker.normalize(fetch_res)
        durations["extraction_ms"] = round((time.time() - t3) * 1000, 2)

        # Worker 4: Claim Extraction Worker
        t4 = time.time()
        claim_set = self.claim_extractor.extract_claims(doc)
        durations["claim_extraction_ms"] = round((time.time() - t4) * 1000, 2)

        # Worker 5: Research Critic Worker
        t5 = time.time()
        critic_rep = self.critic_worker.evaluate_and_stage(doc, claim_set, category=plan.category)
        durations["critic_eval_ms"] = round((time.time() - t5) * 1000, 2)

        return BoundedResearchCycleResult(
            cycle_id=cycle_id,
            topic=topic,
            query=query or topic,
            candidates_found=len(unique_cands),
            documents_fetched=1,
            claims_extracted=len(claim_set.claims),
            critic_report=critic_rep,
            worker_durations_ms=durations,
            status="SUCCESS",
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

        # Phase 1: Stage candidate into Human-in-the-Loop Triage Inbox
        from core.knowledge_os.research_wikipedia import research_wikipedia_engine

        triage_id = research_wikipedia_engine.add_to_triage_inbox(
            candidate_title=ingest_options["title"],
            candidate_summary=(
                fetch_res.text_content[:300]
                if fetch_res.text_content
                else "Autonomous web research candidate."
            ),
            source_url=candidate_url,
            source_domain=fetch_res.source_domain,
            proposed_category=custom_topic,
            extracted_claims=[c.to_dict() for c in res.claims] if res.claims else [],
            source_id=res.source.source_id,
        )

        return {
            "status": res.status,
            "source_id": res.source.source_id,
            "wiki_article_id": res.source.wiki_article_id,
            "triage_id": triage_id,
            "content_hash": fetch_res.content_hash,
            "claims_extracted": len(res.claims),
            "title": ingest_options["title"],
            "url": candidate_url,
        }


web_search_agent = AutonomousWebSearchAgent()
