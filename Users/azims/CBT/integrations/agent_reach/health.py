"""
Health and Diagnostic Doctor for Agent-Reach Integration.

Provides non-blocking health checks mirroring `agent-reach doctor`:
- Network reachability (Jina Reader, public web)
- Tool availability (yt-dlp, curl, python packages)
- Credential & cookie status for gated platforms
"""

from __future__ import annotations

import logging
import shutil
import time
from typing import Any

import httpx

from integrations.agent_reach.capability_registry import (
    CapabilityRegistry,
    ChannelStatus,
    PlatformChannel,
    global_capability_registry,
)

logger = logging.getLogger("ai_quant_sentinel.agent_reach.health")


class AgentReachHealth:
    """
    Automated diagnostic runner for Agent-Reach connectivity, tool discovery,
    and fallback mechanisms.
    """

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self.registry = registry or global_capability_registry

    async def run_diagnostics(self) -> dict[str, Any]:
        """
        Executes full diagnostic suite and returns comprehensive health status.
        """
        self.registry.refresh()
        capabilities = self.registry.to_dict()

        # 1. Check Jina Reader connectivity
        jina_status = "UNKNOWN"
        jina_latency_ms = None
        try:
            t0 = time.monotonic()
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get("https://r.jina.ai/https://example.com")
                jina_latency_ms = round((time.monotonic() - t0) * 1000, 1)
                jina_status = "ONLINE" if res.status_code == 200 else f"HTTP_{res.status_code}"
        except Exception as e:  # noqa: BLE001
            jina_status = f"OFFLINE ({type(e).__name__})"

        # 2. Check local CLI tools
        tools = {
            "curl": shutil.which("curl") is not None,
            "yt-dlp": shutil.which("yt-dlp") is not None,
            "ffmpeg": shutil.which("ffmpeg") is not None,
        }

        # 3. Compute overall status
        online_channels = sum(
            1 for c in capabilities.values() if c["status"] == ChannelStatus.ONLINE.value
        )
        degraded_channels = sum(
            1 for c in capabilities.values() if c["status"] == ChannelStatus.DEGRADED.value
        )
        total_channels = len(capabilities)

        if online_channels >= 3:
            overall_status = "HEALTHY"
        elif online_channels + degraded_channels >= 2:
            overall_status = "DEGRADED"
        else:
            overall_status = "CRITICAL"

        return {
            "overall_status": overall_status,
            "timestamp_utc": time.time(),
            "summary": f"{online_channels}/{total_channels} channels ONLINE, {degraded_channels} DEGRADED",
            "jina_reader": {
                "status": jina_status,
                "latency_ms": jina_latency_ms,
            },
            "system_tools": tools,
            "channels": capabilities,
            "recommendations": self._generate_recommendations(capabilities, tools),
        }

    def _generate_recommendations(
        self, capabilities: dict[str, Any], tools: dict[str, bool]
    ) -> list[str]:
        recs: list[str] = []
        if not tools.get("yt-dlp"):
            recs.append(
                "Install yt-dlp (`pip install yt-dlp`) to unlock high-fidelity financial keynote transcripts."
            )
        if (
            capabilities.get(PlatformChannel.TWITTER.value, {}).get("status")
            == ChannelStatus.UNAVAILABLE.value
        ):
            recs.append(
                "Add credentials/x_cookies.json to enable institutional Twitter/X sentiment tracking."
            )
        if (
            capabilities.get(PlatformChannel.XUEQIU.value, {}).get("status")
            == ChannelStatus.UNAVAILABLE.value
        ):
            recs.append(
                "Add credentials/xueqiu_cookies.json to track Asian market & PBOC policy chatter."
            )
        return recs


# Default global health runner
global_agent_reach_health = AgentReachHealth()
