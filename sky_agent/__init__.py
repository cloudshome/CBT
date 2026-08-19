"""sky_agent — 24/7 Trading Intelligence & Research Agent for SKY.

The research/analyst layer around the deterministic SKY engine.
Never places trades, never bypasses risk_gate, never writes main.

See docs/DISCOVERY_2026-08-19_AGENT.md for the full architecture map.
"""

from sky_agent.config import VERSION

__all__ = ["VERSION"]
