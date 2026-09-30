"""
Capability and Channel Registry for Agent-Reach Integration.

Manages availability status across multi-domain research channels:
- Zero-config public channels: Web (Jina), RSS, YouTube transcripts, GitHub.
- Cookie-gated social channels: Twitter/X, Reddit, Xueqiu.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ChannelStatus(str, Enum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class PlatformChannel(str, Enum):
    WEB = "WEB"
    RSS = "RSS"
    YOUTUBE = "YOUTUBE"
    GITHUB = "GITHUB"
    TWITTER = "TWITTER"
    REDDIT = "REDDIT"
    XUEQIU = "XUEQIU"


@dataclass
class ChannelCapability:
    channel: PlatformChannel
    status: ChannelStatus
    description: str
    requires_cookies: bool
    details: dict[str, Any] = field(default_factory=dict)


class CapabilityRegistry:
    """
    Detects local dependencies, tools, and session credentials to register
    the operational capability of each intelligence channel.
    """

    def __init__(self, credentials_dir: Path | None = None) -> None:
        self.credentials_dir = credentials_dir or (Path("credentials"))
        self._capabilities: dict[PlatformChannel, ChannelCapability] = {}
        self.refresh()

    def refresh(self) -> None:
        """Evaluates tool presence and cookies to refresh capability statuses."""
        # 1. WEB channel: relies on httpx and Jina Reader / fallback parser
        self._capabilities[PlatformChannel.WEB] = ChannelCapability(
            channel=PlatformChannel.WEB,
            status=ChannelStatus.ONLINE,
            description="Web reading via Jina Reader (r.jina.ai) with BeautifulSoup markdown fallback.",
            requires_cookies=False,
            details={"primary_provider": "Jina Reader", "fallback": "Local HTML Parser"},
        )

        # 2. RSS channel: built-in XML ElementTree parser
        self._capabilities[PlatformChannel.RSS] = ChannelCapability(
            channel=PlatformChannel.RSS,
            status=ChannelStatus.ONLINE,
            description="Syndicated feeds parsing (RSS 2.0 / Atom 1.0) for central banks & financial news.",
            requires_cookies=False,
            details={"parser": "xml.etree.ElementTree"},
        )

        # 3. GITHUB channel: public REST API & raw content
        self._capabilities[PlatformChannel.GITHUB] = ChannelCapability(
            channel=PlatformChannel.GITHUB,
            status=ChannelStatus.ONLINE,
            description="Public repository README, release notes, and commit telemetry inspection.",
            requires_cookies=False,
            details={"rate_limit_authenticated": bool(os.getenv("GITHUB_TOKEN"))},
        )

        # 4. YOUTUBE channel: checks yt-dlp or fallback transcript scraper
        has_ytdlp = shutil.which("yt-dlp") is not None
        self._capabilities[PlatformChannel.YOUTUBE] = ChannelCapability(
            channel=PlatformChannel.YOUTUBE,
            status=ChannelStatus.ONLINE if has_ytdlp else ChannelStatus.DEGRADED,
            description="Video transcript & key concept extraction for financial keynotes.",
            requires_cookies=False,
            details={
                "yt_dlp_installed": has_ytdlp,
                "mode": "yt-dlp" if has_ytdlp else "transcript_api_fallback",
            },
        )

        # 5. TWITTER / X channel: requires user session cookies
        has_x_cookie = (
            (self.credentials_dir / "x_cookies.json").exists()
            or bool(os.getenv("TWITTER_COOKIES"))
            or bool(os.getenv("X_AUTH_TOKEN"))
        )
        self._capabilities[PlatformChannel.TWITTER] = ChannelCapability(
            channel=PlatformChannel.TWITTER,
            status=ChannelStatus.ONLINE if has_x_cookie else ChannelStatus.UNAVAILABLE,
            description="X/Twitter institutional research accounts, macro commentary & sentiment flow.",
            requires_cookies=True,
            details={"has_cookies": has_x_cookie},
        )

        # 6. REDDIT channel: public json or user cookie
        has_reddit_cookie = (self.credentials_dir / "reddit_cookies.json").exists() or bool(
            os.getenv("REDDIT_COOKIES")
        )
        self._capabilities[PlatformChannel.REDDIT] = ChannelCapability(
            channel=PlatformChannel.REDDIT,
            status=ChannelStatus.ONLINE if has_reddit_cookie else ChannelStatus.DEGRADED,
            description="Community sentiment, retail positioning chatter, and token discussions.",
            requires_cookies=True,
            details={
                "has_cookies": has_reddit_cookie,
                "mode": "authenticated" if has_reddit_cookie else "public_json_readonly",
            },
        )

        # 7. XUEQIU channel (Chinese market insights): requires cookie
        has_xueqiu = (self.credentials_dir / "xueqiu_cookies.json").exists() or bool(
            os.getenv("XUEQIU_COOKIES")
        )
        self._capabilities[PlatformChannel.XUEQIU] = ChannelCapability(
            channel=PlatformChannel.XUEQIU,
            status=ChannelStatus.ONLINE if has_xueqiu else ChannelStatus.UNAVAILABLE,
            description="Chinese equity market, PBOC policy chatter, and global supply chain intelligence.",
            requires_cookies=True,
            details={"has_cookies": has_xueqiu},
        )

    def get_status(self, channel: PlatformChannel) -> ChannelStatus:
        cap = self._capabilities.get(channel)
        return cap.status if cap else ChannelStatus.UNAVAILABLE

    def is_channel_usable(self, channel: PlatformChannel) -> bool:
        status = self.get_status(channel)
        return status in (ChannelStatus.ONLINE, ChannelStatus.DEGRADED)

    def to_dict(self) -> dict[str, Any]:
        return {
            ch.value: {
                "status": cap.status.value,
                "description": cap.description,
                "requires_cookies": cap.requires_cookies,
                "details": cap.details,
            }
            for ch, cap in self._capabilities.items()
        }


# Default global capability registry
global_capability_registry = CapabilityRegistry()
