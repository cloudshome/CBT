"""
core/cognitive_brain/hermes_agent_bridge.py
===========================================
Institutional Bridge connecting Crypto Brain Terminal (CBT) to Nous Research's
Hermes Agent (v0.22+).

Provides:
1. System status & model discovery
2. Asynchronous headless query execution (--oneshot -Q)
3. Quantitative trading hypothesis & market autopsy critique
4. Multi-model routing (Nous Portal, Gemini, OpenRouter)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger("cbt.cognitive_brain.hermes")

DEFAULT_HERMES_BIN = "/home/cloudslover/.local/bin/hermes"


class HermesAgentBridge:
    """Institutional adapter for Nous Research Hermes Agent."""

    def __init__(self, hermes_path: str | None = None) -> None:
        self.hermes_bin = hermes_path or shutil.which("hermes") or DEFAULT_HERMES_BIN
        self.hermes_home = Path(os.path.expanduser("~/.hermes"))

    @property
    def is_installed(self) -> bool:
        """Verify hermes binary exists and is executable."""
        return os.path.exists(self.hermes_bin) and os.access(self.hermes_bin, os.X_OK)

    async def get_status(self) -> dict[str, Any]:
        """Fetch current Hermes Agent runtime state and configured model."""
        if not self.is_installed:
            return {
                "installed": False,
                "error": f"Hermes binary not found at {self.hermes_bin}",
            }

        try:
            proc = await asyncio.create_subprocess_exec(
                self.hermes_bin,
                "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            raw_out = stdout.decode("utf-8", errors="replace")

            model_match = re.search(r"Model:\s+([^\n\r]+)", raw_out)
            provider_match = re.search(r"Provider:\s+([^\n\r]+)", raw_out)
            gateway_match = re.search(r"Gateway:\s+([^\n\r]+)", raw_out)

            return {
                "installed": True,
                "binary": self.hermes_bin,
                "model": model_match.group(1).strip() if model_match else "unknown",
                "provider": provider_match.group(1).strip() if provider_match else "unknown",
                "gateway": gateway_match.group(1).strip() if gateway_match else "offline",
                "raw_status": raw_out.strip(),
            }
        except Exception as e:
            logger.error("Failed to query hermes status: %s", e)
            return {
                "installed": True,
                "binary": self.hermes_bin,
                "error": str(e),
            }

    async def ask_hermes(
        self,
        query: str,
        *,
        model: str | None = None,
        provider: str | None = None,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        """Execute a headless query against Hermes Agent and return response text."""
        if not self.is_installed:
            return {
                "success": False,
                "error": f"Hermes Agent binary not found at {self.hermes_bin}",
            }

        cmd = [self.hermes_bin, "chat", "-q", query, "--oneshot", "-Q"]
        if model:
            cmd.extend(["-m", model])
        if provider:
            cmd.extend(["--provider", provider])

        try:
            logger.info("Executing Hermes Agent query: %s...", query[:60])
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            out_str = stdout.decode("utf-8", errors="replace").strip()
            err_str = stderr.decode("utf-8", errors="replace").strip()

            # Extract session id if present
            session_id = None
            sess_match = re.search(r"session_id:\s*([a-zA-Z0-9_\-]+)", out_str + "\n" + err_str)
            if sess_match:
                session_id = sess_match.group(1)

            # Strip session_id line from response text for cleaner output
            clean_text = re.sub(r"session_id:\s*[a-zA-Z0-9_\-]+", "", out_str).strip()

            if proc.returncode != 0 and not clean_text:
                return {
                    "success": False,
                    "error": err_str or "Non-zero exit code from Hermes",
                    "session_id": session_id,
                }

            return {
                "success": True,
                "response": clean_text,
                "session_id": session_id,
            }
        except TimeoutError:
            return {
                "success": False,
                "error": f"Hermes Agent timed out after {timeout}s",
            }
        except Exception as e:
            logger.error("Hermes Agent invocation error: %s", e)
            return {
                "success": False,
                "error": str(e),
            }

    async def evaluate_market_thesis(
        self,
        symbol: str,
        timeframe: str,
        current_price: float,
        hypothesis: str,
        timeout: float = 90.0,
    ) -> dict[str, Any]:
        """Ask Hermes to critique a trading setup or market hypothesis."""
        prompt = (
            f"You are the Quantitative Market Intelligence Analyst for Crypto Brain Terminal.\n"
            f"Asset: {symbol} | Timeframe: {timeframe} | Current Price: {current_price}\n"
            f"Proposed Hypothesis / Setup: {hypothesis}\n"
            f"Evaluate this hypothesis strictly from an SMC / Order Flow / Microstructure perspective. "
            f"Provide:\n"
            f"1. Directional Thesis (Bullish/Bearish/Neutral)\n"
            f"2. Invalidation Level (Price threshold)\n"
            f"3. Key Microstructure Risk (Liquidity sweep, funding friction, lookahead)\n"
            f"Keep the analysis concise, quantitative, and institutional."
        )
        return await self.ask_hermes(prompt, timeout=timeout)


# Global singleton instance
hermes_bridge = HermesAgentBridge()
