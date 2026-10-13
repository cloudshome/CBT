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

from core.telegram.rbac import TelegramUserIdentity
from core.telegram.tool_gateway import (
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

        # Helper: Language detection
        is_bangla = any(ord(char) >= 0x0980 and ord(char) <= 0x09FF for char in clean) or any(
            w in lower for w in ("kemon", "bhai", "vai", "khobor", "dam", "koto", "dike", "jabe", "kinbo", "lagbe", "obostha")
        )
        lang = "bn" if is_bangla else "en"

        # Helper: Target Symbol & Asset extraction
        def _extract_sym(t: str) -> tuple[str, str]:
            if any(k in t for k in ("eth", "ethereum", "ইথেরিয়াম", "ইটিএইচ")):
                return "ETH/USDT", "Ethereum"
            if any(k in t for k in ("sol", "solana", "সোলানা")):
                return "SOL/USDT", "Solana"
            if any(k in t for k in ("gold", "xau", "paxg", "স্বর্ণ", "সোনা", "গোল্ড")):
                return "XAU/USD", "Gold"
            return "BTC/USDT", "Bitcoin"

        # 5a. Standalone Asset Inquiry (e.g. "BTC", "bitcoin", "ETH", "SOL", "GOLD", "বিটকয়েন")
        standalone_map = {
            "btc": "BTC/USDT",
            "bitcoin": "BTC/USDT",
            "বিটকয়েন": "BTC/USDT",
            "বিটিসি": "BTC/USDT",
            "eth": "ETH/USDT",
            "ethereum": "ETH/USDT",
            "ইথেরিয়াম": "ETH/USDT",
            "ইটিএইচ": "ETH/USDT",
            "sol": "SOL/USDT",
            "solana": "SOL/USDT",
            "সোলানা": "SOL/USDT",
            "gold": "XAU/USD",
            "xau": "XAU/USD",
            "paxg": "XAU/USD",
            "স্বর্ণ": "XAU/USD",
            "সোনার": "XAU/USD",
            "গোল্ড": "XAU/USD",
        }
        if lower in standalone_map:
            return PlannerDecision(
                intent="GET_PRICE_OR_DOSSIER",
                tool_name="get_live_ticker_dossier",
                tool_args={"symbol": standalone_map[lower], "language": lang},
            )

        # 5b. Account Balance & Risk Primacy (e.g. "balance", "equity", "ব্যালেন্স", "ইকুইটি", "ব্যালেন্স কত")
        if any(w in lower for w in ("balance", "equity", "capital", "ব্যালেন্স", "ইকুইটি")):
            return PlannerDecision(
                intent="GET_ACCOUNT_RISK",
                tool_name="get_account_risk_overview",
                tool_args={},
            )

        # 5c. Broad Market Overview & State (e.g. "market", "market status", "market overview", "crypto market", "how is the market", "মার্কেট কেমন", "মার্কেটের অবস্থা কি")
        if lower in ("market", "crypto", "মার্কেট") or any(w in lower for w in ("market overview", "market status", "market state", "market update", "crypto market", "the market", "মার্কেট কেমন", "মার্কেটের অবস্থা", "মার্কেট অবস্থা", "মার্কেট আপডেট", "market kemon", "market er khobor")):
            return PlannerDecision(
                intent="GET_MARKET_OVERVIEW",
                tool_name="get_market_overview",
                tool_args={"language": lang},
            )

        # 5d. Asset Update / Overview (e.g. "how is btc", "tell me about btc", "btc update", "btc er obostha ki")
        if any(lower.startswith(pfx) for pfx in ("how is ", "tell me about ", "update on ", "analysis of ", "check ", "what about ")) or any(w in lower for w in ("er obostha", "kemon ache")):
            target_sym, _ = _extract_sym(lower)
            return PlannerDecision(
                intent="GET_PRICE_OR_DOSSIER",
                tool_name="get_live_ticker_dossier",
                tool_args={"symbol": target_sym, "language": lang},
            )

        # 5e. Price / Quote / Ticker Inquiry (e.g. "btc price", "price btc", "bitcoin price", "dam koto", "দাম কত", "বিটকয়েন দাম")
        price_triggers = ("price", "rate", "quote", "cost", "value", "dam", "koto", "দাম", "কত", "দর", "প্রাইজ", "টাকা")
        if any(w in lower for w in price_triggers) and not any(w in lower for w in ("position", "পজিশন", "signal", "সিগন্যাল")):
            target_sym, _ = _extract_sym(lower)
            return PlannerDecision(
                intent="GET_PRICE_OR_DOSSIER",
                tool_name="get_live_ticker_dossier",
                tool_args={"symbol": target_sym, "language": lang},
            )

        # 5f. Trading Concepts & Strategy Candidates (e.g. "concept", "concepts", "active concepts", "m32", "qualified strategies", "কোন স্ট্র্যাটেজি চলছে")
        if any(w in lower for w in ("concept", "concepts", "active concepts", "m32", "qualified strategies", "কোন স্ট্র্যাটেজি চলছে", "ক্যান্ডিডেট কি আছে")):
            return PlannerDecision(
                intent="GET_CONCEPTS",
                tool_name="get_concept_intelligence",
                tool_args={},
            )

        # 6. What AI Learned Today
        if any(w in lower for w in ("আজকে কি শিখলে", "আজকে কি পড়লে", "what ai learned", "learned today", "study", "পড়াশোনা")):
            return PlannerDecision(
                intent="GET_LEARNED",
                tool_name="get_ai_learned_today",
                tool_args={},
            )

        # 7. Research Theses & Institutional Hypotheses
        if any(w in lower for w in ("থিসিস", "হাইপোথিসিস", "thesis", "theses", "ম্যাক্রো থিসিস")):
            return PlannerDecision(
                intent="QUERY_THESES",
                tool_name="query_theses",
                tool_args={"asset_class": None, "status": None},
            )

        # 8. Evidence Timeline & Narrative Evolution
        if any(w in lower for w in ("টাইমলাইন", "timeline", "এভিডেন্স টাইমলাইন", "ঘটনাপঞ্জি")):
            topic_match = clean.replace("টাইমলাইন", "").replace("timeline", "").strip()
            return PlannerDecision(
                intent="GET_TIMELINE",
                tool_name="get_evidence_timeline",
                tool_args={"topic": topic_match},
            )

        # 9. Knowledge Graph & Causal Networks
        if any(w in lower for w in ("গ্রাফ", "নলেজ গ্রাফ", "সম্পর্ক", "knowledge graph", "graph", "কানেকশন", "network")):
            ent = "Bitcoin"
            if "eth" in lower or "ইথেরিয়াম" in lower:
                ent = "Ethereum"
            elif "fed" in lower or "ফেড" in lower:
                ent = "Federal Reserve"
            elif "cpi" in lower or "মুদ্রাস্ফীতি" in lower:
                ent = "CPI Inflation"
            elif "dxy" in lower or "ডলার" in lower:
                ent = "US Dollar Index"
            elif "fvg" in lower:
                ent = "Fair Value Gap"
            return PlannerDecision(
                intent="QUERY_GRAPH",
                tool_name="query_knowledge_graph",
                tool_args={"entity": ent},
            )

        # 10. Epistemic Claim Verification
        if any(w in lower for w in ("ভেরিফাই", "যাচাই", "দাবি পরীক্ষা", "claim", "verify")):
            cid_match = re.search(r"\b[A-Za-z0-9_-]+_C-\d+\b|\bC-\d+\b", clean)
            cid = cid_match.group(0) if cid_match else None
            return PlannerDecision(
                intent="VERIFY_CLAIMS",
                tool_name="verify_claims",
                tool_args={"claim_id": cid},
            )

        # 11. Macro Catalysts / CPI / FOMC
        if any(w in lower for w in ("ম্যাক্রো", "সিপিআই", "এফওএমসি", "ইনফ্লেশন", "সুদের হার", "macro", "cpi", "fomc", "nfp", "fed", "interest rate")):
            ev = "CPI" if "cpi" in lower else ("FOMC" if "fomc" in lower else ("NFP" if "nfp" in lower else ""))
            return PlannerDecision(
                intent="GET_MACRO",
                tool_name="get_macro_flash",
                tool_args={"event_name": ev},
            )

        # 11b. Mastermind Arbiter Council & Specialist Swarm
        if any(w in lower for w in ("সোয়ার্ম", "স্পেশালিস্ট", "ডেডিকেটেড এজেন্ট", "মাস্টারমাইন্ড", "swarm", "specialist", "specialists", "mastermind", "arbiter")):
            return PlannerDecision(
                intent="GET_SWARM_STATUS",
                tool_name="get_mastermind_swarm_status",
                tool_args={},
            )

        # 11c. Autonomous Online Data Collector & Crawl Trigger
        if any(w in lower for w in ("কালেক্টর", "ডাটা কালেক্টর", "collector", "crawler", "feeds", "ফিড")):
            if any(w in lower for w in ("চালু কর", "চালাও", "করো", "start", "run", "crawl", "trigger")):
                return PlannerDecision(
                    intent="TRIGGER_CRAWL",
                    tool_name="trigger_autonomous_crawl",
                    tool_args={},
                )
            return PlannerDecision(
                intent="GET_COLLECTOR_STATUS",
                tool_name="get_autonomous_collector_status",
                tool_args={},
            )

        if any(w in lower for w in ("ডাটা কালেক্ট করো", "ক্রল করো", "ক্রল চালাও", "crawl", "collect intel", "fetch intel", "অনলাইন ডাটা আনো")):
            return PlannerDecision(
                intent="TRIGGER_CRAWL",
                tool_name="trigger_autonomous_crawl",
                tool_args={},
            )

        if any(w in lower for w in ("অনলাইন ডাটা", "অনলাইন ডেটা")):
            return PlannerDecision(
                intent="GET_COLLECTOR_STATUS",
                tool_name="get_autonomous_collector_status",
                tool_args={},
            )

        # 12. Unified Project RAG & Evidence Dossier
        if any(w in lower for w in ("ডসিয়ার", "dossier", "প্রজেক্ট নলেজ", "project knowledge", "rag", "এভিডেন্স সামারি", "রিসার্চ রিপোর্ট")):
            q = clean.replace("ডসিয়ার", "").replace("dossier", "").strip()
            return PlannerDecision(
                intent="QUERY_RAG",
                tool_name="query_project_rag",
                tool_args={"query": q},
            )

        # 13. Research Wiki Search
        if any(w in lower for w in ("উইকি", "রিসার্চ ল্যাব", "wiki", "research", "আর্টিকেল", "পেপার")):
            q = clean.replace("উইকি", "").replace("wiki", "").strip()
            return PlannerDecision(
                intent="QUERY_WIKI",
                tool_name="query_research_wiki",
                tool_args={"query": q},
            )

        # 13. Strategy Candidate Backtest Execution
        if any(w in lower for w in ("ব্যাকটেস্ট", "backtest", "test candidate", "ক্যান্ডিডেট টেস্ট", "ভ্যালিডেট")):
            cand_match = re.search(r"\b(CAND_[A-Za-z0-9_-]+)\b", clean)
            cand_id = cand_match.group(0) if cand_match else ""
            return PlannerDecision(
                intent="RUN_BACKTEST",
                tool_name="run_candidate_backtest",
                tool_args={"candidate_id": cand_id},
            )

        # 14. Strategy Candidate Synthesis from Claim
        if any(w in lower for w in ("সিন্থেসাইজ", "synthesize", "স্ট্র্যাটেজি বানাও", "ক্যান্ডিডেট বানাও", "create strategy")):
            cid_match = re.search(r"\b[A-Za-z0-9_-]+_C-\d+\b|\bC-\d+\b", clean)
            cid = cid_match.group(0) if cid_match else ""
            return PlannerDecision(
                intent="SYNTHESIZE_STRATEGY",
                tool_name="synthesize_strategy_from_claim",
                tool_args={"claim_id": cid},
            )

        # 15. Strategy Candidates Listing
        if any(w in lower for w in ("ক্যান্ডিডেট", "স্ট্র্যাটেজি", "candidate", "strategy", "পরীক্ষা")):
            return PlannerDecision(
                intent="GET_CANDIDATES",
                tool_name="get_strategy_candidates",
                tool_args={},
            )

        # 16. Project Status / Terminal Health
        if any(w in lower for w in ("টার্মিনাল অবস্থা", "প্রজেক্টের অবস্থা", "স্ট্যাটাস", "status", "health", "mode")):
            return PlannerDecision(
                intent="GET_STATUS",
                tool_name="get_project_status",
                tool_args={},
            )

        # 17. General Conversational / Quantitative Advisory
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

        # 1. Fetch current live market telemetry defensively
        btc_price = 78000.0
        btc_change_24h = 2.15
        eth_price = 2500.0
        try:
            btc_ticker = await market_gateway.get_ticker("BTC/USDT")
            btc_price = float(btc_ticker.get("price", btc_price))
            btc_change_24h = float(btc_ticker.get("change_24h_pct", btc_change_24h))
        except Exception as e:
            logger.debug(f"[AgentPlanner] BTC ticker fetch error: {e}")

        try:
            eth_ticker = await market_gateway.get_ticker("ETH/USDT")
            eth_price = float(eth_ticker.get("price", eth_price))
        except Exception as e:
            logger.debug(f"[AgentPlanner] ETH ticker fetch error: {e}")

        try:
            accounting = portfolio_shadow.get_portfolio_accounting()
        except Exception as e:
            logger.debug(f"[AgentPlanner] accounting fetch error: {e}")
            accounting = {"virtual_equity": 100000.0, "open_positions_count": 0, "total_unrealized_pnl": 0.0}

        telemetry_ctx = {
            "btc_price": btc_price,
            "btc_change_24h": btc_change_24h,
            "eth_price": eth_price,
            "virtual_equity": accounting.get("virtual_equity", 100000.0),
            "open_positions_count": accounting.get("open_positions_count", 0),
            "unrealized_pnl": accounting.get("total_unrealized_pnl", 0.0),
            "risk_rule": "Half-Kelly (Max 2.5% Equity / Trade), Zero-Lookahead closed bars only",
            "capital_mode": "REAL_CAPITAL_ENABLED = False (Paper Simulation Locked)",
        }

        # 2. Compile Grounded Project RAG Dossier across the 5 ledgers (defensive)
        try:
            from core.knowledge_os.project_rag import project_rag

            dossier = project_rag.compile_grounded_dossier(query=query, market_vitals=telemetry_ctx)
            telemetry_ctx["rag_dossier"] = dossier.to_dict()
            telemetry_ctx["research_grounding"] = dossier.summary_grounding
        except Exception as e:
            logger.debug(f"[AgentPlanner] project_rag compilation fallback: {e}")

        # 3. Invoke QuantMentor with project context
        try:
            response = await quant_mentor.generate_response(
                user_message=query,
                market_telemetry=telemetry_ctx,
                language_preference="auto",
            )
            return response
        except Exception as e:
            logger.warning(f"[AgentPlanner] quant_mentor generation error: {e}")
            return quant_mentor._generate_heuristic_response(query, telemetry_ctx, "auto")


# Singleton
telegram_agent_planner = TelegramAgentPlanner()
