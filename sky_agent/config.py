"""sky_agent.config — env-driven config for the 24/7 intelligence agent."""

from __future__ import annotations

import os

VERSION = "0.1.0"

# Polling intervals (seconds)
MARKET_POLL_SECONDS = int(os.getenv("SKY_AGENT_MARKET_POLL_SECONDS", "300"))  # 5m
DERIVATIVES_POLL_SECONDS = int(os.getenv("SKY_AGENT_DERIVATIVES_POLL_SECONDS", "600"))
NEWS_POLL_SECONDS = int(os.getenv("SKY_AGENT_NEWS_POLL_SECONDS", "900"))
EDGAR_POLL_SECONDS = int(os.getenv("SKY_AGENT_EDGAR_POLL_SECONDS", "1800"))  # 30m
SYSTEM_POLL_SECONDS = int(os.getenv("SKY_AGENT_SYSTEM_POLL_SECONDS", "300"))
REPORT_HOUR_UTC = int(os.getenv("SKY_AGENT_REPORT_HOUR_UTC", "5"))

# Reliability thresholds (see discovery doc §2.6 scoring)
NOTIFY_MIN_LEVEL = os.getenv(
    "SKY_AGENT_NOTIFY_LEVEL", "HIGH"
)  # LOW/MEDIUM/HIGH/CRITICAL

# SEC EDGAR (fair-access)
SEC_USER_AGENT = os.getenv(
    "SKY_SEC_USER_AGENT", "SKY Research Agent (azimshawon@SKY; educational)"
)
SEC_MAX_RPS = float(os.getenv("SKY_SEC_MAX_RPS", "5"))  # stay well under 10/s

# System alert thresholds
DISK_ALERT_PCT = float(os.getenv("SKY_AGENT_DISK_ALERT_PCT", "85"))
RAM_ALERT_PCT = float(os.getenv("SKY_AGENT_RAM_ALERT_PCT", "90"))

# WATCH symbols/timeframes mirror SKY config but may be overridden
WATCH_SYMBOLS_RAW = os.getenv("SKY_AGENT_SYMBOLS", "")
WATCH_TIMEFRAMES_RAW = os.getenv("SKY_AGENT_TIMEFRAMES", "5m,15m,1h,4h,1d")
