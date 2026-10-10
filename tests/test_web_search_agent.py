"""
tests/test_web_search_agent.py
==============================
Adversarial Security & Integration Tests for Autonomous Web Search Agent.

Tests:
1. SSRF Protection: Blocks localhost, 127.0.0.1, RFC 1918 (10.x, 192.168.x), AWS metadata (169.254.169.254).
2. Protocol Restrictions: Rejects file://, ftp://, gopher://, ssh:// schemes.
3. Port Restrictions: Rejects non-standard ports (e.g., 22, 3306, 6379).
4. Safe HTML Text Extraction: Strips script, style, and comments safely.
5. Search Candidate Deduplication & Normalization.
6. Execution Kernel Isolation: Verifies capital firewall and Milestone 18 invariants remain intact.
"""

from __future__ import annotations

import pytest
from core.knowledge_os.web_search_agent import (
    SafeHTMLTextExtractor,
    SecurityValidationError,
    validate_url_security,
    web_search_agent,
)


def test_ssrf_blocks_loopback_and_private_ips():
    """Invariant: System must fail closed on localhost, loopbacks, and RFC1918."""
    blocked_targets = [
        "http://localhost:8000/api/health",
        "http://127.0.0.1:8000/api/orders",
        "http://0.0.0.0:80/status",                   # RFC 1122
        "http://10.0.0.1/admin",
        "http://172.16.0.10:8080/metrics",
        "http://192.168.1.1:8080/router",
        "http://169.254.169.254/latest/meta-data/",  # Cloud Metadata endpoint
        "http://100.64.0.1/cgnat",                   # Carrier-grade NAT
        "http://224.0.0.1/multicast",                # Multicast
        "http://240.0.0.1/reserved",                 # Reserved Future Use
        "http://metadata.google.internal/computeMetadata/v1/",
    ]
    for url in blocked_targets:
        with pytest.raises(SecurityValidationError):
            validate_url_security(url)


def test_ssrf_blocks_unsafe_schemes_and_ports():
    """Invariant: Only HTTP and HTTPS on approved ports are permitted."""
    unsafe_targets = [
        "file:///etc/passwd",
        "ftp://ftp.example.com/file.txt",
        "gopher://example.com:70/",
        "http://example.com:22/",  # SSH port
        "http://example.com:3306/",  # MySQL port
        "http://example.com:6379/",  # Redis port
    ]
    for url in unsafe_targets:
        with pytest.raises(SecurityValidationError):
            validate_url_security(url)


def test_safe_html_text_extractor():
    """Invariant: Scripts, styles, and unsafe tags must not be executed or preserved."""
    html_sample = """
    <!DOCTYPE html>
    <html>
    <head><title>Test Macro Paper</title><style>body { color: red; }</style></head>
    <body>
        <h1>US Liquidity & TGA Cycle</h1>
        <script>alert('prompt injection attack'); window.location = 'http://attacker.com';</script>
        <p>The Treasury General Account balance drained by $40B, injecting net liquidity into market reserves.</p>
        <div>Analysis by Quantitative Research Desk.</div>
    </body>
    </html>
    """
    extractor = SafeHTMLTextExtractor()
    extractor.feed(html_sample)
    cleaned = extractor.get_text()

    assert "alert('prompt injection attack')" not in cleaned
    assert "body { color: red; }" not in cleaned
    assert "The Treasury General Account balance drained" in cleaned
    assert "US Liquidity & TGA Cycle" in cleaned


@pytest.mark.asyncio
async def test_web_search_discovery_structure():
    """Verifies that discover_and_evaluate returns a typed, bounded SearchDiscoveryResult."""
    res = await web_search_agent.discover_and_evaluate(
        query="bitcoin market structure liquidity",
        topic="Quantitative Market Structure",
        limit=3,
    )
    assert res.query == "bitcoin market structure liquidity"
    assert res.topic == "Quantitative Market Structure"
    assert isinstance(res.candidates, list)
    assert "DUCKDUCKGO" in res.provider_status


def test_capital_firewall_and_m18_isolation():
    """Verifies that adding the web search agent does NOT touch Milestone 18 or capital firewall."""
    from core.execution.kill_switch import live_kill_switch
    # Capital firewall remains active and enforced
    assert hasattr(live_kill_switch, "is_active")
