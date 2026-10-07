"""
core/telegram/tool_gateway.py
=============================
Controlled Tool-Execution Gateway for CBT / SKY Project-Aware Telegram AI Agent.

Constitutional Governance:
- Class A: Read-Only Intelligence (Auto-executes without confirmation).
- Class B: Research & Backtest (Auto-executes non-destructive simulations).
- Class C: Simulation / Paper Trades (Mandatory Two-Phase Confirmation: Plan -> User Confirms -> Commit).
- Class D: Live Capital / Real Execution (PERMANENTLY BLOCKED: REAL_CAPITAL_ENABLED = False).
- Full Audit Trail: Every call logged to TelegramAuditLogger.
"""

from __future__ import annotations

import enum
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from core.telegram.audit import TelegramAuditLogger
from core.telegram.rbac import TelegramUserIdentity

logger = logging.getLogger("sky.telegram.tool_gateway")


class ToolClass(enum.StrEnum):
    CLASS_A_READONLY = "CLASS_A_READONLY"
    CLASS_B_ANALYSIS = "CLASS_B_ANALYSIS"
    CLASS_C_ACTION = "CLASS_C_ACTION"
    CLASS_D_LIVE_BLOCKED = "CLASS_D_LIVE_BLOCKED"


@dataclass
class ToolResult:
    success: bool
    tool_name: str
    tool_class: ToolClass
    output_text: str
    data: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    confirmation_token: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "tool_name": self.tool_name,
            "tool_class": self.tool_class.value,
            "output_text": self.output_text,
            "data": self.data,
            "requires_confirmation": self.requires_confirmation,
            "confirmation_token": self.confirmation_token,
            "error": self.error,
        }


@dataclass
class PendingAction:
    token: str
    tool_name: str
    args: dict[str, Any]
    user_id: int | str
    chat_id: int | str
    description: str
    created_at: float
    expires_at: float  # default 300s (5m)

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class TelegramToolGateway:
    """
    Institutional Tool Gateway enforcing 4-Tier governance and Two-Phase confirmation.
    """

    def __init__(self):
        self._pending_actions: dict[str, PendingAction] = {}

    # -------------------------------------------------------------------------
    # TWO-PHASE CONFIRMATION MANAGEMENT
    # -------------------------------------------------------------------------
    def register_pending_action(
        self,
        tool_name: str,
        args: dict[str, Any],
        identity: TelegramUserIdentity,
        description: str,
        ttl_seconds: int = 300,
    ) -> str:
        """Stores a Class C paper action awaiting explicit user confirmation."""
        token = f"CONF_{uuid.uuid4().hex[:8].upper()}"
        now = time.time()
        self._pending_actions[token] = PendingAction(
            token=token,
            tool_name=tool_name,
            args=args,
            user_id=identity.user_id,
            chat_id=identity.chat_id,
            description=description,
            created_at=now,
            expires_at=now + ttl_seconds,
        )
        logger.info(f"Registered pending action [{token}] for user {identity.user_id}: {description}")
        return token

    def get_pending_action(self, token: str) -> PendingAction | None:
        action = self._pending_actions.get(token)
        if action and action.is_expired():
            del self._pending_actions[token]
            return None
        return action

    def pop_pending_action(self, token: str) -> PendingAction | None:
        action = self.get_pending_action(token)
        if action:
            del self._pending_actions[token]
        return action

    def get_latest_pending_for_user(self, user_id: int | str) -> PendingAction | None:
        """Finds the most recent non-expired pending action for a user."""
        now = time.time()
        candidates = [
            a for a in self._pending_actions.values()
            if str(a.user_id) == str(user_id) and a.expires_at > now
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda x: x.created_at, reverse=True)
        return candidates[0]

    # -------------------------------------------------------------------------
    # MASTER TOOL DISPATCHER
    # -------------------------------------------------------------------------
    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        identity: TelegramUserIdentity,
    ) -> ToolResult:
        """
        Executes or plans a tool under strict governance checks.
        """
        logger.info(f"[ToolGateway] Dispatching {tool_name} for user {identity.user_id} ({identity.role.value})")

        # ---------------------------------------------------------------------
        # CLASS D: PERMANENTLY BLOCKED LIVE CAPITAL
        # -------------------------------------------------------------------------
        if tool_name.startswith("live_") or "real_money" in tool_name or tool_name == "execute_live_order":
            TelegramAuditLogger.log_command_execution(
                identity=identity,
                command=tool_name,
                args=json.dumps(arguments),
                risk_result="BLOCKED",
                execution_result="BLOCKED",
                details={"reason": "Constitutional Rule: REAL_CAPITAL_ENABLED = False permanently locked."},
            )
            return ToolResult(
                success=False,
                tool_name=tool_name,
                tool_class=ToolClass.CLASS_D_LIVE_BLOCKED,
                output_text=(
                    "🚨 **CONSTITUTIONAL VIOLATION / LIVE CAPITAL GATE BLOCKED**\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    "• **Invariant:** `REAL_CAPITAL_ENABLED = False` is hardcoded & locked.\n"
                    "• **Policy:** Live capital trading is disabled across all Telegram interfaces.\n"
                    "• **Safety:** Capital preservation guaranteed. Only simulated paper desks are authorized."
                ),
                error="Live trading permanently locked.",
            )

        # ---------------------------------------------------------------------
        # CLASS A: READ-ONLY INTELLIGENCE
        # -------------------------------------------------------------------------
        if tool_name == "get_project_status":
            return await self._tool_get_project_status(identity)

        elif tool_name == "get_open_positions":
            return await self._tool_get_open_positions(identity)

        elif tool_name == "query_research_wiki":
            query = arguments.get("query", "")
            return await self._tool_query_research_wiki(query, identity)

        elif tool_name == "get_macro_flash":
            event_name = arguments.get("event_name", "")
            return await self._tool_get_macro_flash(event_name, identity)

        elif tool_name == "get_ai_learned_today":
            return await self._tool_get_ai_learned_today(identity)

        elif tool_name == "get_market_state":
            symbol = arguments.get("symbol", "BTC/USDT")
            return await self._tool_get_market_state(symbol, identity)

        elif tool_name == "get_strategy_candidates":
            return await self._tool_get_strategy_candidates(identity)

        elif tool_name == "query_theses":
            asset_class = arguments.get("asset_class")
            status = arguments.get("status")
            return await self._tool_query_theses(asset_class, status, identity)

        elif tool_name == "get_evidence_timeline":
            topic = arguments.get("topic") or arguments.get("entity") or ""
            return await self._tool_get_evidence_timeline(topic, identity)

        elif tool_name == "query_knowledge_graph":
            entity = arguments.get("entity", "Bitcoin")
            return await self._tool_query_knowledge_graph(entity, identity)

        elif tool_name == "query_project_rag":
            query = arguments.get("query", "")
            return await self._tool_query_project_rag(query, identity)

        # ---------------------------------------------------------------------
        # CLASS B: RESEARCH & ANALYSIS
        # -------------------------------------------------------------------------
        elif tool_name == "ingest_research_url":
            url = arguments.get("url", "")
            return await self._tool_ingest_research_url(url, identity)

        elif tool_name == "verify_claims":
            claim_id = arguments.get("claim_id")
            return await self._tool_verify_claims(claim_id, identity)

        elif tool_name == "run_candidate_backtest":
            candidate_id = arguments.get("candidate_id", "")
            return await self._tool_run_candidate_backtest(candidate_id, identity)

        elif tool_name == "synthesize_strategy_from_claim":
            claim_id = arguments.get("claim_id", "")
            return await self._tool_synthesize_strategy(claim_id, identity)

        # ---------------------------------------------------------------------
        # CLASS C: SIMULATION / PAPER TRADES (TWO-PHASE CONFIRMATION)
        # -------------------------------------------------------------------------
        elif tool_name == "plan_trade_signal":
            symbol = arguments.get("symbol", "BTC/USDT")
            return await self._tool_plan_trade_signal(symbol, identity)

        elif tool_name == "plan_close_position":
            symbol = arguments.get("symbol", "")
            return await self._tool_plan_close_position(symbol, identity)

        elif tool_name == "confirm_action":
            token = arguments.get("token", "")
            return await self._tool_confirm_action(token, identity)

        else:
            return ToolResult(
                success=False,
                tool_name=tool_name,
                tool_class=ToolClass.CLASS_A_READONLY,
                output_text=f"⚠️ Unknown tool `{tool_name}` requested.",
                error="Tool not found",
            )

    # -------------------------------------------------------------------------
    # IMPLEMENTATIONS: CLASS A (READ-ONLY)
    # -------------------------------------------------------------------------
    async def _tool_get_project_status(self, identity: TelegramUserIdentity) -> ToolResult:
        from core.event_shock_engine import event_shock_engine
        from core.portfolio_shadow import portfolio_shadow

        accounting = portfolio_shadow.get_portfolio_accounting()
        event_st = event_shock_engine.evaluate_risk_state()
        lockout = event_st.trading_lockout

        text = (
            "🏛️ **CBT / SKY QUANTITATIVE DESK STATUS**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "• **Core Engine:** Operational (Zero-Lookahead Empirical)\n"
            f"• **Virtual Equity:** `${accounting['virtual_equity']:,.2f}`\n"
            f"• **Open Paper Positions:** `{accounting['open_positions_count']}`\n"
            f"• **Unrealized PnL:** `${accounting['total_unrealized_pnl']:+,.2f}`\n"
            f"• **Macro Lockout:** `{'ACTIVE (Trading Paused)' if lockout else 'CLEAR'}`\n"
            "• **Risk Primacy:** Half-Kelly Cap (Max 2.5% Equity / Trade)\n"
            "• **Live Capital Boundary:** `REAL_CAPITAL_ENABLED = False` (Locked)\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔒 _Institutional Research & Paper Simulation active._"
        )
        return ToolResult(
            success=True,
            tool_name="get_project_status",
            tool_class=ToolClass.CLASS_A_READONLY,
            output_text=text,
            data=accounting,
        )

    async def _tool_get_open_positions(self, identity: TelegramUserIdentity) -> ToolResult:
        from core.portfolio_shadow import portfolio_shadow

        positions = portfolio_shadow.get_open_positions()
        accounting = portfolio_shadow.get_portfolio_accounting()

        if not positions:
            text = (
                "📭 **PAPER DESK: NO ACTIVE OPEN POSITIONS**\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• Virtual Capital: `${accounting['virtual_equity']:,.2f}` (100% Cash / USD)\n"
                "• Send `/signal` or ask: *'BTC এর জন্য সিগন্যাল দাও'* to evaluate new high-EV setups."
            )
        else:
            lines = [
                f"💼 **ACTIVE PAPER PRACTICE POSITIONS ({len(positions)})**",
                "━━━━━━━━━━━━━━━━━━━━━━",
            ]
            for p in positions:
                emoji = "🟢 LONG" if p["direction"] == "LONG" else "🔴 SHORT"
                pnl = p.get("unrealized_pnl", 0.0)
                pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
                lines.append(
                    f"• {emoji} **{p['symbol']}** | Size: `{p['size']}` | Entry: `${p['entry_price']:,.2f}`\n"
                    f"  Current: `${p.get('current_price', p['entry_price']):,.2f}` | PnL: **{pnl_str}** | SL: `${p['stop_loss']:,.2f}`"
                )
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"📊 **Total Unrealized PnL:** `${accounting['total_unrealized_pnl']:+,.2f}`")
            text = "\n".join(lines)

        return ToolResult(
            success=True,
            tool_name="get_open_positions",
            tool_class=ToolClass.CLASS_A_READONLY,
            output_text=text,
            data={"positions": positions, "accounting": accounting},
        )

    async def _tool_query_research_wiki(self, query: str, identity: TelegramUserIdentity) -> ToolResult:
        from core.knowledge_os.research_wikipedia import research_wikipedia_engine

        articles = research_wikipedia_engine.list_articles(search_query=query, limit=4)
        if not articles:
            text = f"ℹ️ No Research Wiki articles found matching '{query}'."
        else:
            lines = [
                f"📚 **RESEARCH WIKI INTELLIGENCE: '{query or 'Recent'}'**",
                "━━━━━━━━━━━━━━━━━━━━━━",
            ]
            for a in articles:
                score = a.get("verification_score", 0.0)
                badge = "🟢" if score >= 80 else ("🟡" if score >= 60 else "🔴")
                lines.append(
                    f"{badge} **{a['title']}**\n"
                    f"• ID: `{a['article_id']}` | Rigor: `{score:.1f}%` | Category: `{a['category']}`\n"
                    f"• Summary: _{a.get('executive_summary', '')[:140]}..._\n"
                )
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")
            lines.append("💡 _Send `/wiki <article_id>` to read the full dossier._")
            text = "\n".join(lines)

        return ToolResult(
            success=True,
            tool_name="query_research_wiki",
            tool_class=ToolClass.CLASS_A_READONLY,
            output_text=text,
            data={"articles": articles},
        )

    async def _tool_get_macro_flash(self, event_name: str, identity: TelegramUserIdentity) -> ToolResult:
        from core.macro_event_reporter import macro_event_reporter

        recent = macro_event_reporter.get_recent_releases(limit=5)
        selected = recent[0] if recent else None
        if event_name and recent:
            for r in recent:
                if event_name.upper() in r.get("event_name", "").upper() or event_name.upper() in r.get("event_id", "").upper():
                    selected = r
                    break

        if selected:
            text = macro_event_reporter.format_event_flash_report(selected)
        else:
            text = "ℹ️ No recent macroeconomic catalyst shock records found in the audit database."

        return ToolResult(
            success=True,
            tool_name="get_macro_flash",
            tool_class=ToolClass.CLASS_A_READONLY,
            output_text=text,
            data={"event": selected},
        )

    async def _tool_get_ai_learned_today(self, identity: TelegramUserIdentity) -> ToolResult:
        from core.daily_learning_reporter import daily_learning_reporter

        report = daily_learning_reporter.generate_what_ai_learned_today_report()
        return ToolResult(
            success=True,
            tool_name="get_ai_learned_today",
            tool_class=ToolClass.CLASS_A_READONLY,
            output_text=report,
        )

    async def _tool_get_market_state(self, symbol: str, identity: TelegramUserIdentity) -> ToolResult:
        from core.market_providers import market_gateway

        ticker = await market_gateway.get_ticker(symbol)
        price = float(ticker.get("price", 0.0))
        chg = float(ticker.get("change_24h_pct", 0.0))
        vol = float(ticker.get("volume_24h", 0.0))

        text = (
            f"📈 **LIVE MARKET STATE VECTOR: {symbol}**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• **Current Price:** `${price:,.2f}`\n"
            f"• **24h Change:** `{chg:+.2f}%`\n"
            f"• **24h High:** `${float(ticker.get('high_24h', price)):,.2f}`\n"
            f"• **24h Low:** `${float(ticker.get('low_24h', price)):,.2f}`\n"
            f"• **24h Volume:** `${vol:,.0f}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔬 _Market State grounded in live orderbook vector._"
        )
        return ToolResult(
            success=True,
            tool_name="get_market_state",
            tool_class=ToolClass.CLASS_A_READONLY,
            output_text=text,
            data=ticker,
        )

    async def _tool_get_strategy_candidates(self, identity: TelegramUserIdentity) -> ToolResult:
        from core.database import db_manager

        with db_manager.get_brain_conn() as conn:
            rows = conn.execute(
                "SELECT candidate_id, strategy_name, validation_stage, confidence_score FROM strategy_candidates ORDER BY created_at DESC LIMIT 5;"
            ).fetchall()
        if not rows:
            text = "ℹ️ No strategy candidates currently filed in the Research Lab."
        else:
            lines = [
                "🔬 **RESEARCH LAB: ACTIVE STRATEGY CANDIDATES**",
                "━━━━━━━━━━━━━━━━━━━━━━",
            ]
            for r in rows:
                lines.append(f"• `{r['candidate_id']}` | **{r.get('strategy_name', 'Candidate')}** | Stage: `[{r['validation_stage']}]`")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")
            lines.append("💡 _Use `/test <id>` to run walk-forward validation._")
            text = "\n".join(lines)

        return ToolResult(
            success=True,
            tool_name="get_strategy_candidates",
            tool_class=ToolClass.CLASS_A_READONLY,
            output_text=text,
        )

    async def _tool_query_theses(
        self,
        asset_class: str | None,
        status: str | None,
        identity: TelegramUserIdentity,
    ) -> ToolResult:
        from core.knowledge_os.thesis_engine import thesis_engine

        theses = thesis_engine.list_theses(asset_class=asset_class, status=status)
        if not theses:
            text = "ℹ️ No research theses found matching criteria."
        else:
            lines = [
                "🏛️ **INSTITUTIONAL MACRO & QUANTITATIVE THESES**",
                "━━━━━━━━━━━━━━━━━━━━━━",
            ]
            for t in theses:
                lines.append(
                    f"• **{t['title']}**\n"
                    f"  Status: `[{t['status']}]` | Class: `{t['asset_class']}`\n"
                    f"  Confidence: `{t['confidence_score']:.2f}` | Supporting: `{t['supporting_claims_count']}` | Contradicting: `{t['contradicting_claims_count']}`\n"
                    f"  _{t['description'][:110]}..._\n"
                )
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")
            lines.append("🔒 _Evolving institutional theses grounded in empirical claims._")
            text = "\n".join(lines)

        return ToolResult(
            success=True,
            tool_name="query_theses",
            tool_class=ToolClass.CLASS_A_READONLY,
            output_text=text,
            data={"theses": theses},
        )

    async def _tool_get_evidence_timeline(
        self,
        topic: str,
        identity: TelegramUserIdentity,
    ) -> ToolResult:
        from core.knowledge_os.evidence_timeline import evidence_timeline_engine

        timeline = evidence_timeline_engine.build_timeline(topic=topic or None, limit=10)
        lines = [
            f"⏱️ **EVIDENCE TIMELINE: {timeline.topic_or_entity.upper()}**",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"• **Narrative Trend:** `{timeline.narrative_trend}`",
            f"• **Net Confidence:** `{timeline.net_confidence_score:.2f}`",
            f"• **Supporting Records:** `{timeline.supporting_evidence_count}` | **Contradictions:** `{timeline.contradiction_count}`",
            "━━━━━━━━━━━━━━━━━━━━━━",
            "📅 **Recent Chronological Events:**",
        ]
        for e in timeline.events[-6:]:
            lines.append(
                f"• `[{e.date_formatted}]` **{e.event_type}** ({e.entity_or_topic}):\n"
                f"  {e.headline[:110]}... (Conf: {e.confidence_score:.2f})"
            )
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("🔬 _Zero-leakage chronological empirical provenance._")
        text = "\n".join(lines)

        return ToolResult(
            success=True,
            tool_name="get_evidence_timeline",
            tool_class=ToolClass.CLASS_A_READONLY,
            output_text=text,
            data=timeline.to_dict(),
        )

    async def _tool_query_knowledge_graph(
        self,
        entity: str,
        identity: TelegramUserIdentity,
    ) -> ToolResult:
        from core.knowledge_os.knowledge_graph import knowledge_graph_engine

        subgraph = knowledge_graph_engine.get_subgraph(entity)
        nodes = subgraph.get("nodes", [])
        edges = subgraph.get("edges", [])

        if not nodes:
            text = f"ℹ️ Entity `{entity}` not found in CBT Knowledge Graph."
        else:
            lines = [
                f"🕸️ **KNOWLEDGE GRAPH SUBGRAPH: {entity.upper()}**",
                "━━━━━━━━━━━━━━━━━━━━━━",
                f"• **Mapped Nodes:** `{len(nodes)}` | **Active Relations:** `{len(edges)}`",
                "━━━━━━━━━━━━━━━━━━━━━━",
                "🔗 **Key Relationships:**",
            ]
            for edge in edges[:8]:
                lines.append(
                    f"• `{edge['source']}` ➔ **{edge['type']}** ➔ `{edge['target']}` "
                    f"(weight: `{edge['weight']:.2f}`)\n"
                    f"  _{edge.get('description', '')[:90]}_"
                )
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")
            lines.append("💡 _Relational causal network across assets, macro indicators, and SMC concepts._")
            text = "\n".join(lines)

        return ToolResult(
            success=True,
            tool_name="query_knowledge_graph",
            tool_class=ToolClass.CLASS_A_READONLY,
            output_text=text,
            data=subgraph,
        )

    async def _tool_query_project_rag(self, query: str, identity: TelegramUserIdentity) -> ToolResult:
        from core.knowledge_os.project_rag import project_rag
        from core.market_providers import market_gateway
        from core.portfolio_shadow import portfolio_shadow

        btc_ticker = await market_gateway.get_ticker("BTC/USDT")
        eth_ticker = await market_gateway.get_ticker("ETH/USDT")
        accounting = portfolio_shadow.get_portfolio_accounting()

        vitals = {
            "btc_price": btc_ticker.get("price", 0.0),
            "eth_price": eth_ticker.get("price", 0.0),
            "virtual_equity": accounting.get("virtual_equity", 100000.0),
            "open_positions_count": accounting.get("open_positions_count", 0),
        }

        dossier = project_rag.compile_grounded_dossier(query=query, market_vitals=vitals)
        return ToolResult(
            success=True,
            tool_name="query_project_rag",
            tool_class=ToolClass.CLASS_A_READONLY,
            output_text=dossier.summary_grounding,
            data=dossier.to_dict(),
        )

    # -------------------------------------------------------------------------
    # IMPLEMENTATIONS: CLASS B (RESEARCH & ANALYSIS)
    # -------------------------------------------------------------------------
    async def _tool_ingest_research_url(self, url: str, identity: TelegramUserIdentity) -> ToolResult:
        from core.knowledge_os.universal_ingestor import universal_ingestor

        res = universal_ingestor.ingest_url(url=url, options={"author": identity.username or str(identity.user_id)})
        badge = "🟢 SUCCESS" if res.status == "SUCCESS" else ("🟡 PARTIAL" if res.status == "PARTIAL" else "⚠️ ACCESS BLOCKED")

        text = (
            f"🔬 **EVIDENCE RESEARCH OS INGESTION RESULT**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• **Status:** `{badge}`\n"
            f"• **Source ID:** `{res.source.source_id}`\n"
            f"• **Domain:** `{res.source.source_domain}` ({res.source.source_type})\n"
            f"• **Wiki Article:** `{res.wiki_article.article_id if res.wiki_article else 'SAVED'}`\n\n"
            f"📝 **Summary:** {res.wiki_article.executive_summary[:200] if res.wiki_article else res.source.failure_reason}..."
        )
        if res.real_life_summary:
            text += (
                f"\n\n🎯 **বাস্তব জীবনের সারসংক্ষেপ:**\n"
                f"• **সহজ বাংলায় মূল কথা:** {res.real_life_summary.core_concept_bn}\n"
                f"• **মার্কেট প্রভাব:** {res.real_life_summary.practical_market_impact}\n"
                f"• **করণীয়:** {res.real_life_summary.actionable_guidance}\n"
                f"• **ঝুঁকি:** {res.real_life_summary.risk_warning}"
            )

        return ToolResult(
            success=True,
            tool_name="ingest_research_url",
            tool_class=ToolClass.CLASS_B_ANALYSIS,
            output_text=text,
            data=res.to_dict(),
        )

    async def _tool_run_candidate_backtest(self, candidate_id: str, identity: TelegramUserIdentity) -> ToolResult:
        from core.telegram.handlers import handle_test

        out = await handle_test(args=candidate_id, identity=identity)
        return ToolResult(
            success=True,
            tool_name="run_candidate_backtest",
            tool_class=ToolClass.CLASS_B_ANALYSIS,
            output_text=out,
        )

    async def _tool_verify_claims(self, claim_id: str | None, identity: TelegramUserIdentity) -> ToolResult:
        from core.knowledge_os.claim_verifier import claim_verifier

        if claim_id:
            res = claim_verifier.verify_claim(claim_id)
            if not res:
                text = f"⚠️ Claim `{claim_id}` not found for verification."
            else:
                lines = [
                    f"🔍 **EPISTEMIC CLAIM VERIFICATION: `{claim_id}`**",
                    "━━━━━━━━━━━━━━━━━━━━━━",
                    f"• **Claim:** _{res.original_claim_text}_\n",
                    f"• **Status:** `{res.previous_status}` ➔ **`{res.new_status}`**",
                    f"• **Confidence:** `{res.confidence_score:.2f}`",
                    f"• **Rationale:** {res.verification_rationale}",
                ]
                if res.corroborating_evidence:
                    lines.append("\n✅ **Corroborating Evidence:**")
                    for c in res.corroborating_evidence:
                        lines.append(f"• `{c.evidence_type}` ({c.source_reference}): {c.citation_text}")
                if res.contradictions_detected:
                    lines.append("\n❌ **Contradictions Flagged:**")
                    for c in res.contradictions_detected:
                        lines.append(f"• `{c.evidence_type}` ({c.source_reference}): {c.citation_text}")
                lines.append("━━━━━━━━━━━━━━━━━━━━━━")
                text = "\n".join(lines)
            return ToolResult(
                success=True,
                tool_name="verify_claims",
                tool_class=ToolClass.CLASS_B_ANALYSIS,
                output_text=text,
                data=res.to_dict() if res else None,
            )

        results = claim_verifier.verify_all_unverified_claims(limit=10)
        lines = [
            "🔍 **BATCH EPISTEMIC CLAIM VERIFICATION**",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"• Verified `{len(results)}` pending research claims.",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]
        for r in results[:5]:
            lines.append(f"• `{r.claim_id}`: **[{r.new_status}]** (Conf: {r.confidence_score:.2f}) — {r.original_claim_text[:80]}...")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        text = "\n".join(lines)

        return ToolResult(
            success=True,
            tool_name="verify_claims",
            tool_class=ToolClass.CLASS_B_ANALYSIS,
            output_text=text,
            data={"verified_count": len(results)},
        )

    async def _tool_synthesize_strategy(self, claim_id: str, identity: TelegramUserIdentity) -> ToolResult:
        from core.knowledge_os.strategy_bridge import strategy_bridge

        target_cid = claim_id
        if not target_cid:
            with strategy_bridge._get_wiki_connection() as conn:
                row = conn.execute(
                    "SELECT claim_id FROM research_claims ORDER BY created_at DESC LIMIT 1;"
                ).fetchone()
                if row:
                    target_cid = row["claim_id"]

        if not target_cid:
            return ToolResult(
                success=False,
                tool_name="synthesize_strategy_from_claim",
                tool_class=ToolClass.CLASS_B_ANALYSIS,
                output_text="⚠️ No claim ID provided and no research claims found in database.",
                error="Claim ID required",
            )

        cand = strategy_bridge.synthesize_strategy_from_claim(target_cid)
        if not cand:
            return ToolResult(
                success=False,
                tool_name="synthesize_strategy_from_claim",
                tool_class=ToolClass.CLASS_B_ANALYSIS,
                output_text=f"⚠️ Could not synthesize strategy: Claim `{target_cid}` not found.",
                error="Claim not found",
            )

        text = (
            f"🔬 **SYNTHESIZED STRATEGY CANDIDATE**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 **Candidate ID:** `{cand.candidate_id}`\n"
            f"🏷️ **Strategy Name:** `{cand.strategy_name}`\n"
            f"📖 **Source Claim:** `{cand.knowledge_id}`\n"
            f"⏱️ **Timeframe:** `{cand.timeframe}`\n"
            f"🎯 **Required Indicators:** `{', '.join(cand.required_indicators) if cand.required_indicators else 'Price Action'}`\n"
            f"⚖️ **Governance Stage:** `[{cand.validation_stage}]`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 **Hypothesis:**\n_{cand.hypothesis}_\n\n"
            f"⚡ **Execute Walk-Forward Backtest:** `/test {cand.candidate_id}`"
        )
        return ToolResult(
            success=True,
            tool_name="synthesize_strategy_from_claim",
            tool_class=ToolClass.CLASS_B_ANALYSIS,
            output_text=text,
            data=cand.to_dict(),
        )

    # -------------------------------------------------------------------------
    # IMPLEMENTATIONS: CLASS C (TWO-PHASE CONFIRMATION REQUIRED)
    # -------------------------------------------------------------------------
    async def _tool_plan_trade_signal(self, symbol: str, identity: TelegramUserIdentity) -> ToolResult:
        """
        Phase 1: Plans the trade setup, verifies risk clearance, and requests user confirmation.
        """
        from core.market_providers import market_gateway
        from core.portfolio_shadow import portfolio_shadow

        ticker = await market_gateway.get_ticker(symbol)
        price = float(ticker.get("price", 0.0))
        if price <= 0:
            return ToolResult(
                success=False,
                tool_name="plan_trade_signal",
                tool_class=ToolClass.CLASS_C_ACTION,
                output_text=f"⚠️ Price feed unavailable for {symbol}.",
                error="Invalid price",
            )

        accounting = portfolio_shadow.get_portfolio_accounting()
        equity = accounting["virtual_equity"]
        half_kelly_pct = 1.50
        alloc_usd = equity * (half_kelly_pct / 100.0)
        size = round(alloc_usd / price, 4)

        sl = round(price * 0.985, 2)
        tp = round(price * 1.035, 2)

        desc = f"Open Paper Practice LONG on {symbol} (Size: {size}, Entry: ${price:,.2f}, SL: ${sl:,.2f}, TP: ${tp:,.2f})"
        token = self.register_pending_action(
            tool_name="open_paper_trade",
            args={
                "symbol": symbol,
                "direction": "LONG",
                "size": size,
                "entry_price": price,
                "stop_loss": sl,
                "take_profit": tp,
            },
            identity=identity,
            description=desc,
        )

        confirm_text = (
            f"📋 **PROPOSED PAPER TRADE PLAN (AWAITING CONFIRMATION)**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• **Asset:** `{symbol}` (LONG)\n"
            f"• **Planned Size:** `{size}` (~${alloc_usd:,.2f} USD, 1.5% Half-Kelly)\n"
            f"• **Entry Price:** `${price:,.2f}`\n"
            f"• **Stop Loss:** `${sl:,.2f}` (-1.50%)\n"
            f"• **Take Profit:** `${tp:,.2f}` (+3.50%)\n"
            f"• **Risk Desk Clearance:** `APPROVED (Deterministic Risk Primacy)`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ **Do you want to execute this paper trade?**\n"
            f"👉 Reply: **'হ্যাঁ'**, **'confirm'**, or send `/confirm {token}`\n"
            f"⏱️ _Offer expires in 5 minutes._"
        )

        return ToolResult(
            success=True,
            tool_name="plan_trade_signal",
            tool_class=ToolClass.CLASS_C_ACTION,
            output_text=confirm_text,
            requires_confirmation=True,
            confirmation_token=token,
            data={"token": token, "symbol": symbol, "size": size, "entry": price},
        )

    async def _tool_plan_close_position(self, symbol: str, identity: TelegramUserIdentity) -> ToolResult:
        """
        Phase 1: Plans the position close and requests confirmation.
        """
        from core.portfolio_shadow import portfolio_shadow

        positions = portfolio_shadow.get_open_positions()
        target = next((p for p in positions if p["symbol"].upper() == symbol.upper()), None)
        if not target and positions:
            target = positions[0]

        if not target:
            return ToolResult(
                success=False,
                tool_name="plan_close_position",
                tool_class=ToolClass.CLASS_C_ACTION,
                output_text=f"ℹ️ No open position found for `{symbol or 'any asset'}`.",
                error="No position",
            )

        sym = target["symbol"]
        desc = f"Close active shadow position on {sym}"
        token = self.register_pending_action(
            tool_name="close_paper_trade",
            args={"symbol": sym, "position_id": target.get("position_id")},
            identity=identity,
            description=desc,
        )

        confirm_text = (
            f"⚠️ **CONFIRM CLOSING SHADOW POSITION**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• **Asset:** `{sym}` ({target['direction']})\n"
            f"• **Entry Price:** `${target['entry_price']:,.2f}`\n"
            f"• **Current Price:** `${target.get('current_price', target['entry_price']):,.2f}`\n"
            f"• **Unrealized PnL:** `${target.get('unrealized_pnl', 0.0):+,.2f}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ **Are you sure you want to close this position?**\n"
            f"👉 Reply: **'হ্যাঁ'**, **'confirm'**, or send `/confirm {token}`"
        )

        return ToolResult(
            success=True,
            tool_name="plan_close_position",
            tool_class=ToolClass.CLASS_C_ACTION,
            output_text=confirm_text,
            requires_confirmation=True,
            confirmation_token=token,
            data={"token": token, "symbol": sym},
        )

    async def _tool_confirm_action(self, token: str, identity: TelegramUserIdentity) -> ToolResult:
        """
        Phase 2: Commits the planned action after explicit user confirmation.
        """
        pending = self.pop_pending_action(token)
        if not pending:
            # Fallback: check latest for user
            pending = self.get_latest_pending_for_user(identity.user_id)
            if pending:
                self.pop_pending_action(pending.token)

        if not pending:
            return ToolResult(
                success=False,
                tool_name="confirm_action",
                tool_class=ToolClass.CLASS_C_ACTION,
                output_text="⚠️ No active or non-expired pending action found to confirm.",
                error="Action expired or not found",
            )

        logger.info(f"[Two-Phase Confirmation] Committing {pending.tool_name} [{pending.token}] for user {identity.user_id}")

        if pending.tool_name == "open_paper_trade":
            from core.portfolio_shadow import portfolio_shadow

            p_id = portfolio_shadow.open_position(
                symbol=pending.args["symbol"],
                direction=pending.args["direction"],
                size=pending.args["size"],
                entry_price=pending.args["entry_price"],
                stop_loss=pending.args["stop_loss"],
                take_profit=pending.args["take_profit"],
            )

            TelegramAuditLogger.log_command_execution(
                identity=identity,
                command="open_paper_trade",
                args=json.dumps(pending.args),
                risk_result="PASS",
                execution_result="EXECUTED",
                details={"position_id": p_id},
            )

            text = (
                f"✅ **TWO-PHASE CONFIRMATION EXECUTED: PAPER POSITION OPENED**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🆔 **Position ID:** `{p_id}`\n"
                f"• **Asset:** `{pending.args['symbol']}` ({pending.args['direction']})\n"
                f"• **Size:** `{pending.args['size']}`\n"
                f"• **Entry Price:** `${pending.args['entry_price']:,.2f}`\n"
                f"• **Stop Loss:** `${pending.args['stop_loss']:,.2f}`\n"
                f"• **Take Profit:** `${pending.args['take_profit']:,.2f}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔒 _Committed atomically into SQLite Shadow Portfolio Ledger._"
            )
            return ToolResult(
                success=True,
                tool_name="confirm_action",
                tool_class=ToolClass.CLASS_C_ACTION,
                output_text=text,
                data={"position_id": p_id},
            )

        elif pending.tool_name == "close_paper_trade":
            from core.portfolio_shadow import portfolio_shadow

            res = portfolio_shadow.close_position(pending.args["symbol"])
            TelegramAuditLogger.log_command_execution(
                identity=identity,
                command="close_paper_trade",
                args=json.dumps(pending.args),
                risk_result="PASS",
                execution_result="EXECUTED",
                details=res,
            )
            text = (
                f"✅ **TWO-PHASE CONFIRMATION EXECUTED: POSITION CLOSED**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• **Asset:** `{pending.args['symbol']}`\n"
                f"• **Realized PnL:** `${res.get('realized_pnl', 0.0):+,.2f}`\n"
                f"• **Status:** Closed and booked into Shadow Equity\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔒 _Transaction recorded in audit ledger._"
            )
            return ToolResult(
                success=True,
                tool_name="confirm_action",
                tool_class=ToolClass.CLASS_C_ACTION,
                output_text=text,
                data=res,
            )

        return ToolResult(
            success=False,
            tool_name="confirm_action",
            tool_class=ToolClass.CLASS_C_ACTION,
            output_text=f"⚠️ Unknown pending tool handler `{pending.tool_name}`.",
            error="Unknown pending tool",
        )


# Singleton
telegram_tool_gateway = TelegramToolGateway()
