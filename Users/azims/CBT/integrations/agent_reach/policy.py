"""
Security, Anti-Ban & Sanitization Policy for Agent-Reach Integration.

Constitutional Rules:
- REAL_CAPITAL_ENABLED = False (External data CANNOT trigger orders or bypass risk).
- All web, RSS, and social text is untrusted external data.
- Strips script tags, suspicious prompt-injection signatures, and credential leaks.
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger("ai_quant_sentinel.agent_reach.policy")

# Constitutional boundary
REAL_CAPITAL_ENABLED = False


# Known prompt-injection attack vectors targeting LLM agent executors
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+are\s+now", re.IGNORECASE),
    re.compile(r"disregard\s+all\s+(prior|previous)\s+prompts", re.IGNORECASE),
    re.compile(r"you\s+must\s+execute\s+the\s+following\s+(command|code|trade)", re.IGNORECASE),
    re.compile(r"place\s+(a\s+)?(live\s+)?(buy|sell)\s+order", re.IGNORECASE),
    re.compile(r"bypass\s+(the\s+)?(risk|kelly|safety)\s+gate", re.IGNORECASE),
    re.compile(r"<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\]", re.IGNORECASE),
]

# Sensitive credentials & keys redaction patterns
CREDENTIAL_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9_-]{20,}", re.IGNORECASE),  # OpenAI keys
    re.compile(r"ghp_[a-zA-Z0-9]{20,}", re.IGNORECASE),  # GitHub personal tokens
    re.compile(r"AIza[0-9A-Za-z-_]{35}", re.IGNORECASE),  # Google API keys
    re.compile(r"binance_[a-zA-Z0-9]{32,}", re.IGNORECASE),  # Binance keys
    re.compile(r"bybit_[a-zA-Z0-9]{32,}", re.IGNORECASE),  # Bybit keys
    re.compile(
        r"(api[_-]?secret|api[_-]?key)\s*[:=]\s*['\"]?[a-zA-Z0-9_+/=-]{16,}['\"]?", re.IGNORECASE
    ),
]


@dataclass
class RateLimitConfig:
    """Per-domain rate limit governor."""

    min_interval_seconds: float = 2.0  # Polite crawl interval between requests to same domain
    max_requests_per_minute: int = 30
    request_timeout_seconds: float = 15.0


class SecurityPolicy:
    """
    Sanitization, Prompt Injection Defense, and Rate-Limiting Policy.
    Guarantees external web content cannot manipulate core quant execution.
    """

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self.config = config or RateLimitConfig()
        self._last_request_time: dict[str, float] = defaultdict(float)
        self._request_counts: dict[str, list[float]] = defaultdict(list)

    @property
    def real_capital_enabled(self) -> bool:
        return REAL_CAPITAL_ENABLED

    def get_domain(self, url: str) -> str:
        """Extracts normalized hostname from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower() or "unknown"
        except Exception:  # noqa: BLE001
            return "unknown"

    def can_request(self, url: str) -> tuple[bool, float]:
        """
        Evaluates whether a request can be safely made to the target domain.
        Returns: (can_proceed, wait_seconds_needed)
        """
        domain = self.get_domain(url)
        now = time.time()

        # Check polite crawl minimum interval
        elapsed = now - self._last_request_time[domain]
        if elapsed < self.config.min_interval_seconds:
            wait_needed = self.config.min_interval_seconds - elapsed
            return False, round(wait_needed, 3)

        # Check rolling 1-minute window
        timestamps = self._request_counts[domain]
        # Purge timestamps older than 60s
        self._request_counts[domain] = [t for t in timestamps if now - t < 60.0]
        if len(self._request_counts[domain]) >= self.config.max_requests_per_minute:
            oldest = self._request_counts[domain][0]
            wait_needed = 60.0 - (now - oldest)
            return False, round(max(0.1, wait_needed), 3)

        return True, 0.0

    def record_request(self, url: str) -> None:
        """Registers a completed request timestamp for rate limiting."""
        domain = self.get_domain(url)
        now = time.time()
        self._last_request_time[domain] = now
        self._request_counts[domain].append(now)

    def sanitize_content(self, raw_text: str) -> tuple[str, list[str]]:
        """
        Sanitizes ingested text:
        1. Strips HTML script/style/iframe tags
        2. Neutralizes prompt injection patterns by wrapping/defanging
        3. Redacts credentials and API secrets
        Returns: (sanitized_text, list_of_security_flags)
        """
        if not raw_text or not isinstance(raw_text, str):
            return "", []

        flags: list[str] = []
        text = raw_text

        # 1. Strip raw HTML script / style / iframe tags
        script_pattern = re.compile(
            r"<(script|style|iframe|object|embed)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE
        )
        if script_pattern.search(text):
            text = script_pattern.sub("[STRIPPED_EMBEDDED_CODE]", text)
            flags.append("STRIPPED_CODE_TAGS")

        # 2. Redact sensitive credentials
        for pat in CREDENTIAL_PATTERNS:
            if pat.search(text):
                text = pat.sub("[REDACTED_CREDENTIAL]", text)
                flags.append("REDACTED_CREDENTIAL")

        # 3. Detect and neutralize prompt injection attempts
        for pat in PROMPT_INJECTION_PATTERNS:
            if pat.search(text):
                text = pat.sub(r"[UNTRUSTED_INJECTION_NEUTRALIZED: \g<0>]", text)
                flags.append("NEUTRALIZED_INJECTION_ATTEMPT")

        # Remove duplicate flags
        unique_flags = sorted(list(set(flags)))
        return text, unique_flags


# Default shared security policy instance
global_security_policy = SecurityPolicy()
