"""
Epistemic Evidence Classifier for SKY Global Intelligence.

Grades external intelligence records according to quantitative epistemic standards:
- VERIFIED_PRIMARY: Official central banks, government statistical bureaus, SEC EDGAR, arXiv.
- CORROBORATED_REPORT: Top-tier financial wire services & established market media.
- UNVERIFIED_CLAIM: Single-author blogs, newsletters, and general web writeups.
- SPECULATION: Social media posts, forum discussions, price predictions, and sentiment hype.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from core.intelligence.schema import EvidenceGrade, SourcePlatform

PRIMARY_DOMAINS = {
    "federalreserve.gov",
    "bls.gov",
    "sec.gov",
    "treasury.gov",
    "ecb.europa.eu",
    "bis.org",
    "bankofengland.co.uk",
    "imf.org",
    "arxiv.org",
    "ssrn.com",
    "nber.org",
    "eips.ethereum.org",
}

CORROBORATED_DOMAINS = {
    "bloomberg.com",
    "reuters.com",
    "ft.com",
    "wsj.com",
    "cnbc.com",
    "coindesk.com",
    "cointelegraph.com",
    "theblock.co",
    "decrypt.co",
    "marketwatch.com",
    "investing.com",
    "barrons.com",
}

SPECULATION_DOMAINS = {
    "twitter.com",
    "x.com",
    "reddit.com",
    "t.me",
    "telegram.org",
    "xueqiu.com",
    "v2ex.com",
    "discord.com",
    "youtube.com",
    "youtu.be",
}

SPECULATION_TEXT_PATTERNS = [
    re.compile(r"\b(100x|1000x|moon|pump(ing)?|dump|gem|alpha\s+leak)\b", re.IGNORECASE),
    re.compile(r"\b(target\s+price|price\s+prediction|next\s+stop)\s*[:\$]?\s*\d+", re.IGNORECASE),
    re.compile(r"\b(insider\s+tells?|trust\s+me|not\s+financial\s+advice|nfa)\b", re.IGNORECASE),
]


class EvidenceClassifier:
    """
    Assigns epistemic evidence tiers and justification notes to external information.
    """

    def classify(
        self,
        url: str,
        source_platform: SourcePlatform | str,
        title: str = "",
        content: str = "",
    ) -> tuple[EvidenceGrade, str]:
        """
        Classifies evidence grade based on source provenance and content markers.
        Returns: (EvidenceGrade, rationale)
        """
        parsed = urlparse(url)
        hostname = (parsed.netloc or "").lower().replace("www.", "")

        # 1. Check Primary Sources
        for prim in PRIMARY_DOMAINS:
            if hostname == prim or hostname.endswith(f".{prim}"):
                return (
                    EvidenceGrade.VERIFIED_PRIMARY,
                    f"Official primary institutional publisher: {hostname}",
                )

        # 2. Check Corroborated Media
        for corr in CORROBORATED_DOMAINS:
            if hostname == corr or hostname.endswith(f".{corr}"):
                return (
                    EvidenceGrade.CORROBORATED_REPORT,
                    f"Established institutional financial/crypto media: {hostname}",
                )

        # 3. Check Social & Speculative Platforms
        platform_str = (
            source_platform.value
            if isinstance(source_platform, SourcePlatform)
            else str(source_platform)
        )
        if platform_str in (
            SourcePlatform.TWITTER.value,
            SourcePlatform.REDDIT.value,
            SourcePlatform.XUEQIU.value,
        ):
            return (
                EvidenceGrade.SPECULATION,
                f"Social media channel ({platform_str}) represents crowd sentiment, not verified evidence.",
            )

        for spec in SPECULATION_DOMAINS:
            if hostname == spec or hostname.endswith(f".{spec}"):
                return (
                    EvidenceGrade.SPECULATION,
                    f"Community discussion platform: {hostname}",
                )

        # 4. Check Text-Level Speculative Markers
        combined = f"{title}\n{content}"
        for pat in SPECULATION_TEXT_PATTERNS:
            if pat.search(combined):
                return (
                    EvidenceGrade.SPECULATION,
                    "Detected high-speculation marketing or price target hype markers in text.",
                )

        # 5. Default to UNVERIFIED_CLAIM
        return (
            EvidenceGrade.UNVERIFIED_CLAIM,
            f"Uncorroborated third-party source: {hostname or 'unknown'}",
        )


# Default global evidence classifier
global_evidence_classifier = EvidenceClassifier()
