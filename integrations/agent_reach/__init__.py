"""
Agent-Reach Access Fabric Integration for SKY / Crypto Brain Terminal.

Provides multi-domain intelligence ingestion across Web, RSS, YouTube, and GitHub,
with strict security policy, prompt injection defense, and fault-isolated circuit breakers.
"""

from integrations.agent_reach.adapter import AgentReachAdapter, global_agent_reach_adapter
from integrations.agent_reach.capability_registry import (
    CapabilityRegistry,
    ChannelCapability,
    ChannelStatus,
    PlatformChannel,
    global_capability_registry,
)
from integrations.agent_reach.health import AgentReachHealth, global_agent_reach_health
from integrations.agent_reach.policy import (
    REAL_CAPITAL_ENABLED,
    RateLimitConfig,
    SecurityPolicy,
    global_security_policy,
)

__all__ = [
    "REAL_CAPITAL_ENABLED",
    "AgentReachAdapter",
    "AgentReachHealth",
    "CapabilityRegistry",
    "ChannelCapability",
    "ChannelStatus",
    "PlatformChannel",
    "RateLimitConfig",
    "SecurityPolicy",
    "global_agent_reach_adapter",
    "global_agent_reach_health",
    "global_capability_registry",
    "global_security_policy",
]
