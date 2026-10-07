"""
core/telegram/agent_planner.py
==============================
Project-Aware Natural Language Agent Planner & Intent Resolver for CBT Telegram AI.

Capabilities:
1. Intent Recognition: Resolves natural language user inputs (Bangla, English, Banglish)
   into deterministic ToolGateway actions or project queries.
2. Grounded Project Awareness: Answers questions grounded in CBT architecture,
   Constitution, live telemetry, and permanent Research Wiki dossiers.
3. Two-Phase Confirmation Routing: Automatically manages pending Class C paper actions.
4. Evidence Mode: Structures quantitative and market answers with institutional rigor.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from core.telegram.rbac import TelegramRole, TelegramUserIdentity
from core.telegram.tool_gateway import (
    ToolClass,
    ToolResult,
    telegram_tool_gateway,
)

logger = logging.getLogger("sky.telegram.agent_planner")


@dataclass
class PlannerDecision:
    intent: str
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    direct_reply: str | None = None
    requires_confirmation: bool = False


class TelegramAgentPlanner:
    """
    Translates natural language conversation into governed project tools and evidence responses.
    """

    def __init__(self):
        self._url_regex = re.compile(r"https?://[^\s]+")

    def resolve_intent(self, text: str, user_id: int | str) -> PlannerDecision:
        """
        Classifies incoming natural language into actionable intent.
        Supports Bengali, English, and Banglish.
        """
        clean = text.strip()
        lower = clean.lower()

        # 1. Check for Pending Confirmation Responses ("হ্যাঁ", "confirm", "করো", "yes", "চালাও")
        if lower in ("হ্যাঁ", "হ্যা", "confirm", "yes", "করো", "চালাও", "চালু কর", "ঠিক আছে", "ok", "execute", "y"):
            pending = telegram_tool_gateway.get_latest_pending_for_user(user_id)
            if pending:
                return PlannerDecision(
                    intent="CONFIRM_ACTION",
                    tool_name="confirm_action",
                    tool_args={"token": pending.token},
                )

        if lower in ("না", "cancel", "বাতিল", "দরকার নেই", "no", "stop"):
            pending = telegram_tool_gateway.get_latest_pending_for_user(user_id)
            if pending:
                telegram_tool_gateway.pop_pending_action(pending.token)
                return PlannerDecision(
                    intent="CANCEL_ACTION",
                    direct_reply="❌ পূর্বের অ্যাকশনটি সফলভাবে বাতিল করা হয়েছে।",
                )

        # 2. Check for Embedded Links (Link Persistence Invariant)
        urls = self._url_regex.findall(clean)
        if urls:
            return PlannerDecision(
                intent="INGEST_URL",
                tool_name="ingest_research_url",
                tool_args={"url": urls[0]},
            )

        # 3. Open Positions / PnL / Portfolio
        if any(w in lower for w in ("পজিশন", "খোলা ট্রেড", "ট্রেড কি আছে", "position", "positions", "pnl", "portfolio", "লাভ", "লস", "লাভ ক্ষতি")):
            return PlannerDecision(
                intent="GET_POSITIONS",
                tool_name="get_open_positions",
                tool_args={},
            )

        # 4. Close Trade / Position
        if any(w in lower for w in ("ট্রেড বন্ধ", "ক্লোজ কর", "পজিশন কাটো", "close trade", "close position", "exit", "close")):
            # Extract symbol if specified
            sym = "BTC/USDT" if "btc" in lower else ("ETH/USDT" if "eth" in lower else ("SOL/USDT" if "sol" in lower else ""))
            return PlannerDecision(
                intent="PLAN_CLOSE",
                tool_name="plan_close_position",
                tool_args={"symbol": sym},
                requires_confirmation=True,
            )

        # 5. Signal / Trade Setup Request
        if any(w in lower for w in ("সিগন্যাল", "ট্রেড দাও", "বাই করব", "সেল করব", "signal", "setup", "entry", "লং", "শর্ট")):
            sym = "ETH/USDT" if "eth" in lower else ("SOL/USDT" if "sol" in lower else "BTC/USDT")
            return PlannerDecision(
                intent="PLAN_SIGNAL",
                tool_name="plan_trade_signal",
                tool_args={"symbol": sym},
                requires_confirmation=True,
            )

        # 6. What AI Learned Today
        if any(w in lower for w in ("আজকে কি শিখলে", "আজকে কি পড়লে", "what ai learned", "learned today", "study", "পড়াশোনা")):
            return PlannerDecision(
                intent="GET_LEARNED",
                tool_name="get_ai_learned_today",
                tool_args={},
            )

        # 7. Macro Catalysts / CPI / FOMC
        if any(w in lower for w in ("ম্যাক্রো", "সিপিআই", "এফওএমসি", "ইনফ্লেশন", "সুদের হার", "macro", "cpi", "fomc", "nfp", "fed", "interest rate")):
            ev = "CPI" if "cpi" in lower else ("FOMC" if "fomc" in lower else ("NFP" if "nfp" in lower else ""))
            return PlannerDecision(
                intent="GET_MACRO",
                tool_name="get_macro_flash",
                tool_args={"event_name": ev},
            )

        # 8. Research Wiki Search
        if any(w in lower for w in ("উইকি", "রিসার্চ ল্যাব", "wiki", "research", "আর্টিকেল", "পেপার")):
            q = clean.replace("উইকি", "").replace("wiki", "").strip()
            return PlannerDecision(
                intent="QUERY_WIKI",
                tool_name="query_research_wiki",
                tool_args={"query": q},
            )

        # 9. Strategy Candidates
        if any(w in lower for w in ("ক্যান্ডিডেট", "স্ট্র্যাটেজি", "candidate", "strategy", "পরীক্ষা")):
            return PlannerDecision(
                intent="GET_CANDIDATES",
                tool_name="get_strategy_candidates",
                tool_args={},
            )

        # 10. Project Status / Terminal Health
        if any(w in lower for w in ("টার্মিনাল অবস্থা", "প্রজেক্টের অবস্থা", "স্ট্যাটাস", "status", "health", "mode")):
            return PlannerDecision(
                intent="GET_STATUS",
                tool_name="get_project_status",
                tool_args={},
            )

        # 11. General Conversational / Quantitative Advisory
        return PlannerDecision(
            intent="CONVERSATIONAL",
        )

    async def handle_user_message(
        self,
        message: str,
        chat_id: int | str,
        identity: TelegramUserIdentity,
    ) -> str:
        """
        Master execution pipeline for any natural language user message.
        """
        decision = self.resolve_intent(message, identity.user_id)
        logger.info(f"[AgentPlanner] Resolved intent '{decision.intent}' for message: {message[:60]}")

        # Case 1: Direct Reply (e.g. Cancel Action)
        if decision.direct_reply:
            return decision.direct_reply

        # Case 2: Deterministic Tool Call
        if decision.tool_name:
            tool_res = await telegram_tool_gateway.execute_tool(
                tool_name=decision.tool_name,
                arguments=decision.tool_args or {},
                identity=identity,
            )
            return tool_res.output_text

        # Case 3: Conversational Intelligence grounded in Project Data & Telemetry
        return await self._synthesize_grounded_response(message, identity)

    async def _synthesize_grounded_response(
        self,
        query: str,
        identity: TelegramUserIdentity,
    ) -> str:
        """
        Synthesizes an institutional, project-grounded answer using QuantMentor
        with rich CBT telemetry, Constitution constraints, and research context.
        """
        from core.market_providers import market_gateway
        from core.portfolio_shadow import portfolio_shadow
        from core.quant_mentor import quant_mentor

        # 1. Fetch current live market telemetry
        btc_ticker = await market_gateway.get_ticker("BTC/USDT")
        eth_ticker = await market_gateway.get_ticker("ETH/USDT")
        accounting = portfolio_shadow.get_portfolio_accounting()

        telemetry_ctx = {
            "btc_price": btc_ticker.get("price", 0.0),
            "btc_change_24h": btc_ticker.get("change_24h_pct", 0.0),
            "eth_price": eth_ticker.get("price", 0.0),
            "virtual_equity": accounting.get("virtual_equity", 100000.0),
            "open_positions_count": accounting.get("open_positions_count", 0),
            "unrealized_pnl": accounting.get("total_unrealized_pnl", 0.0),
            "risk_rule": "Half-Kelly (Max 2.5% Equity / Trade), Zero-Lookahead closed bars only",
            "capital_mode": "REAL_CAPITAL_ENABLED = False (Paper Simulation Locked)",
        }

        # 2. Invoke QuantMentor with project context
        response = await quant_mentor.generate_response(
            user_message=query,
            market_telemetry=telemetry_ctx,
            language_preference="auto",
        )
        return response


# Singleton
telegram_agent_planner = TelegramAgentPlanner()
