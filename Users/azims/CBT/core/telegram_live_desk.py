"""
core/telegram_live_desk.py
==========================
Milestone 21.3: Real-Time Telegram Live Trading Commander & Event Alerting.

Features:
1. 4-Times Daily Automated Reporting strictly adapted to Bangladesh Standard Time (BST = UTC+6):
   - 08:00 AM BST: Morning Asian / Macro Briefing & Overnight Structure Shifts
   - 02:00 PM BST: Midday / London Open Market Pulse & Funding Rate Matrix
   - 08:00 PM BST: US Session Open & Catalyst Shock Watch
   - 10:00 PM BST: "What AI Learned Today" Comprehensive Knowledge & Risk Dossier
2. High-Priority Macro Catalyst Alerting (CPI, FOMC, NFP) with surprise delta,
   price reaction (BTC/ETH), IV crush, and tactical risk directives.
3. Live Trading Execution Commander:
   - /live_status & /live_readiness: multi-exchange balance probe, 1.5% equity cap, 6-gate scorecard.
   - /live_preflight <exchange> <notional>: 6-gate constitutional clearance check.
   - /live_canary <exchange> <symbol> <notional>: micro-order execution ($10-$25) with HMAC dual confirmation.
   - /ai_learned: On-demand "What AI Learned Today" synthesis report.
   - /macro_flash: On-demand high-impact macroeconomic event result report.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from core.daily_learning_reporter import daily_learning_reporter
from core.execution.account_probe import account_probe
from core.execution.kill_switch import live_kill_switch
from core.execution.live_canary_runner import CanaryRunRequest, live_canary_runner
from core.execution.live_gatekeeper import live_gatekeeper
from core.macro_event_reporter import macro_event_reporter

logger = logging.getLogger("sky.telegram.live_desk")

# Bangladesh Standard Time (BST = UTC+6 / Asia/Dhaka)
BD_TZ = datetime.timezone(datetime.timedelta(hours=6))


@dataclass
class HmacActionToken:
    action: str
    token: str
    nonce: str
    created_at: float
    expires_at: float
    payload: dict[str, Any] = field(default_factory=dict)
    consumed: bool = False


class TelegramLiveTradingDesk:
    """Master Telegram live trading commander and scheduled reporting coordinator."""

    def __init__(self) -> None:
        self._secret = os.getenv("JWT_SECRET", "sky_tele_live_secret_key_2026").encode("utf-8")
        self._active_tokens: dict[str, HmacActionToken] = {}

    def generate_action_token(
        self, action: str, payload: dict[str, Any], ttl_seconds: float = 60.0
    ) -> HmacActionToken:
        """Generates a cryptographically signed single-use HMAC token."""
        now = time.time()
        nonce = uuid.uuid4().hex[:8]
        raw = f"{action}:{nonce}:{now}".encode()
        token_str = hmac.new(self._secret, raw, hashlib.sha256).hexdigest()[:16]

        act_token = HmacActionToken(
            action=action,
            token=token_str,
            nonce=nonce,
            created_at=now,
            expires_at=now + ttl_seconds,
            payload=payload,
            consumed=False,
        )
        self._active_tokens[token_str] = act_token
        return act_token

    def validate_and_consume_token(self, token_str: str) -> HmacActionToken | None:
        """Validates and atomically consumes a single-use action token."""
        now = time.time()
        # Prune expired tokens
        expired = [k for k, v in self._active_tokens.items() if now > v.expires_at or v.consumed]
        for k in expired:
            self._active_tokens.pop(k, None)

        token = self._active_tokens.get(token_str)
        if not token:
            return None
        if token.consumed or now > token.expires_at:
            return None

        token.consumed = True
        self._active_tokens.pop(token_str, None)
        return token

    async def format_live_readiness_report(self, environment: str = "PRODUCTION") -> str:
        """
        Formats a comprehensive live account and gatekeeper scorecard for Telegram.
        """
        summary = await account_probe.get_portfolio_readiness(environment=environment)
        verdict = await live_gatekeeper.evaluate_order_clearance(
            exchange="BINANCE",
            order_notional_usd=summary.single_trade_equity_cap_usd or 10.0,
            environment=environment,
        )

        now_bd = datetime.datetime.now(BD_TZ)
        time_str = now_bd.strftime("%d %b %Y, %I:%M %p BST")

        # Checks mapping
        chk_vault = "🟢 UNLOCKED" if summary.vault_unlocked else "🔴 LOCKED (Master Key Required)"
        kill_active, _ = live_kill_switch.is_active()
        chk_kill = "🔴 ACTIVE (Halted)" if kill_active else "🟢 CLEAR (Operational)"
        chk_drift = (
            "🟢 PASS (<500ms)"
            if verdict.checks.get("connectivity_and_clock_drift")
            else "🔴 FAILED / DISCONNECTED"
        )
        chk_drawdown = (
            "🟢 PASS (<3.0%)"
            if verdict.checks.get("daily_drawdown_safe")
            else "🔴 CIRCUIT BREAKER TRIPPED"
        )
        chk_cap = (
            "🟢 CONFORMED" if verdict.checks.get("single_trade_cap_conformed") else "🔴 EXCEEDED"
        )
        chk_live = (
            "🟢 AUTHORIZED"
            if verdict.checks.get("live_trading_authorized")
            else "🟡 DRY-RUN / DISABLED"
        )

        status_emoji = (
            "🟢 ALL CHECKS PASS — CANARY READY"
            if verdict.passed
            else "🛡️ FAIL-CLOSED SAFETY LOCK ENGAGED"
        )

        lines = [
            "⚡ **SKY LIVE EXCHANGE TRADING COMMANDER (PHASE 21)**",
            f"📅 *Timestamp:* `{time_str}` (Bangladesh Standard Time)",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "💰 **MULTI-EXCHANGE PORTFOLIO BALANCE:**",
            f"  • **Total Portfolio Equity:** `${summary.total_portfolio_equity_usd:,.2f} USD`",
            f"  • **Available Free Cash:** `${summary.total_free_cash_usd:,.2f} USD`",
            f"  • **Constitutional 1.5% Single-Trade Cap:** `${summary.single_trade_equity_cap_usd:,.2f} USD`",
            f"  • **Max 6.0% Portfolio Heat:** `${summary.max_portfolio_heat_usd:,.2f} USD`",
            f"  • **Active Venues Connected:** `{', '.join(summary.active_exchanges) if summary.active_exchanges else 'None (Offline)'}`",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "🏛️ **6-POINT CONSTITUTIONAL PRE-FLIGHT SCORECARD:**",
            f"  1. KMS / HSM Vault Enclave: {chk_vault}",
            f"  2. Master Kill Switch: {chk_kill}",
            f"  3. Venue Connectivity & Drift: {chk_drift}",
            f"  4. Daily Drawdown Stop (3.0%): {chk_drawdown}",
            f"  5. Sizing Equity Cap (1.5%): {chk_cap}",
            f"  6. Live Trading Authorization: {chk_live}",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"🚦 **OVERALL VERDICT:** `{status_emoji}`",
        ]

        if not verdict.passed:
            lines.append("\n⚠️ **Pending Safety Gate Clearances:**")
            for r in verdict.rejection_reasons:
                lines.append(f"  • `{r}`")

        lines.extend(
            [
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "💡 **Available Operator Directives:**",
                "  • `/live_preflight <venue> <size>` — Validate an order against all 6 gates.",
                "  • `/live_canary <venue> <sym> <size>` — Run $10-$25 micro-canary order.",
                "  • `/ai_learned` — Review today's 10:00 PM AI learning synthesis.",
                "  • `/macro_flash` — Review latest CPI / FOMC event release & impact.",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "🛡️ *Invariant: Real-money orders require explicit vault unlock & LIVE_TRADING_ENABLED=true.*",
            ]
        )

        return "\n".join(lines)

    async def handle_live_canary_command(
        self,
        exchange: str = "BINANCE",
        symbol: str = "BTC/USDT",
        notional_usd: float = 10.0,
        is_dry_run: bool = True,
    ) -> str:
        """Executes or dry-runs a micro-canary order from Telegram."""
        req = CanaryRunRequest(
            exchange=exchange,
            symbol=symbol,
            notional_usd=notional_usd,
            is_dry_run=is_dry_run,
        )
        res = await live_canary_runner.execute_canary_order(req)

        mode_badge = (
            "🧪 DRY-RUN CANARY SIMULATION" if res.is_dry_run else "🚨 REAL-MONEY LIVE CANARY"
        )
        result_emoji = "✅ SUCCESS" if res.success else "🛑 BLOCKED / FAILED"

        lines = [
            f"🧪 **LIVE CANARY EXECUTION REPORT ({mode_badge})**",
            f"• **Outcome:** `{result_emoji}` ({res.status})",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"• **Venue:** `{res.exchange}` | **Symbol:** `{res.symbol}`",
            f"• **Requested Notional:** `${res.notional_usd:.2f} USD`",
            f"• **Simulated / Fill Price:** `${res.executed_price:,.2f}`",
            f"• **Simulated / Fill Qty:** `{res.executed_qty:.6f}`",
            f"• **Slippage:** `{res.slippage_bps:.2f} bps`",
            f"• **Round-Trip Latency:** `{res.roundtrip_latency_ms:.2f} ms`",
            f"• **Client Order ID:** `{res.client_order_id}`",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"📝 **Message:** {res.message}",
        ]

        if res.reconciliation_id:
            lines.append(f"🔍 **Reconciliation ID:** `{res.reconciliation_id}` (trading_logs.db)")

        return "\n".join(lines)

    def get_what_ai_learned_today_report(self) -> str:
        """Dispatches 'What AI Learned Today' aligned to Bangladesh Standard Time."""
        return daily_learning_reporter.generate_what_ai_learned_today_report()

    def get_latest_macro_flash_report(self) -> str:
        """Dispatches the latest high-impact macroeconomic event result report."""
        return macro_event_reporter.format_event_flash_report()


# Global singleton
telegram_live_desk = TelegramLiveTradingDesk()
