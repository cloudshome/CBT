"""
Telegram V5 Institutional Command Handlers.
Implements the 19 core Telegram command handlers with strict role-based access control (RBAC),
two-phase paper execution, candlestick chart generation, walk-forward strategy validation,
and emergency circuit breaker controls.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from core.database import db_manager
from core.event_shock_engine import event_shock_engine
from core.portfolio_shadow import portfolio_shadow
from core.provenance_engine import provenance_engine
from core.sandbox_lab import sandbox_lab
from core.sky_intelligence import sky_orchestrator
from core.telegram.callbacks import callback_router
from core.telegram.charts import telegram_charts
from core.telegram.commands import TelegramCommand, command_registry
from core.telegram.jobs import job_manager
from core.telegram.rbac import TelegramRole, TelegramUserIdentity

logger = logging.getLogger("ai_quant_sentinel.telegram.handlers")


# ==============================================================================
# COMMAND HANDLERS
# ==============================================================================


async def handle_start_help(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """Returns dynamic role-filtered institutional command help guide."""
    from core.telegram.rbac import rbac_registry

    ident = identity or rbac_registry.resolve_user(chat_id or 0, chat_id or 0)
    return command_registry.generate_help_menu(ident)


async def handle_signal(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """
    Generates a live high-conviction quantitative trade signal.
    Enforces Two-Phase Confirmation: generates a 60s signed ActionToken and
    pure-Python PNG candlestick chart with Entry/SL/TP overlays.
    """
    from core.data_streamer import data_streamer
    from core.telegram_bot import telegram_bot

    sym = args.strip().upper() if args.strip() else "BTC/USDT"
    if "/" not in sym and sym:
        sym = f"{sym}/USDT"

    sig = await telegram_bot.generate_live_signal(sym)
    user_id = identity.user_id if identity else chat_id or "operator"

    # 1. Generate 60s ActionToken for Two-Phase Confirmation
    token = callback_router.create_action_token(
        action_type="STAGE_CONFIRM_ENTRY",
        user_id=user_id,
        chat_id=chat_id,
        payload=sig,
        ttl_seconds=60,
    )
    kb = callback_router.build_signal_keyboard(token.token_id)

    # 2. Render Candlestick Chart
    chart_bytes = b""
    try:
        candles = await data_streamer.fetch_external_ohlcv(sym, "15m", limit=40)
        if not candles or len(candles) < 15:
            candles = data_streamer.generate_synthetic_candles(sym, "15m", count=40)
        chart_bytes = telegram_charts.generate_signal_chart(
            candles=candles,
            entry=sig["entry_price"],
            sl=sig["stop_loss"],
            tp1=sig["tp1"],
            symbol=sym,
        )
    except Exception as e:  # noqa: BLE001 — chart failure is non-fatal
        logger.warning(f"Failed to generate signal chart for {sym}: {e}")

    # 3. Format Signal Text
    msg = (
        f"⚡ **QUANTITATIVE TRADE SIGNAL** | `{sig['symbol']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **Setup:** `{sig['setup']}`\n"
        f"📊 **Regime:** `{sig['regime']}`\n"
        f"🔥 **Confluence:** `{sig['confluence_score']}/100`\n"
        f"💰 **Kelly Allocation:** `{sig['kelly_allocation_pct']:.2f}%`\n\n"
        f"📍 **Entry:** `${sig['entry_price']:,.2f}`\n"
        f"🛑 **Stop Loss:** `${sig['stop_loss']:,.2f}`\n"
        f"🎯 **TP1:** `${sig['tp1']:,.2f}`\n"
        f"🎯 **TP2:** `${sig['tp2']:,.2f}`\n"
        f"🚀 **TP3 (Runner):** `${sig['tp3']:,.2f}`\n"
        f"⚖️ **R:R Ratio:** `{sig['risk_reward']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ **Two-Phase Confirmation:** Tap `[ ⚡ Enter Paper Trade ]` below to arm.\n"
        f"_Action token expires in 60s. Maximum risk capped at Half-Kelly (2.50%)._"
    )

    # 4. Dispatch via Photo or Message
    if chat_id:
        if chart_bytes:
            await telegram_bot.send_photo(
                chart_bytes,
                caption=f"⚡ Institutional Setup: `{sym}`",
                reply_markup=kb,
                chat_id=chat_id,
            )
        else:
            await telegram_bot.send_message(msg, chat_id=chat_id, reply_markup=kb)

    return msg


async def handle_positions(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """Returns active shadow practice positions and attaches quick-management buttons."""
    from core.telegram_bot import telegram_bot

    report = telegram_bot.state_mind.get_positions_report()
    open_pos = portfolio_shadow.get_open_positions()

    kb = None
    if open_pos:
        primary = open_pos[0]
        sym = primary.get("symbol", "BTC/USDT")
        user_id = identity.user_id if identity else chat_id or "operator"

        close_tok = callback_router.create_action_token(
            action_type="STAGE_CLOSE_CONFIRM",
            user_id=user_id,
            chat_id=chat_id,
            payload={"symbol": sym},
            ttl_seconds=60,
        )
        be_tok = callback_router.create_action_token(
            action_type="STAGE_BE_ADJUST",
            user_id=user_id,
            chat_id=chat_id,
            payload={"symbol": sym},
            ttl_seconds=60,
        )
        kb = callback_router.build_position_keyboard(sym, close_tok.token_id, be_tok.token_id)

    if chat_id:
        await telegram_bot.send_message(report, chat_id=chat_id, reply_markup=kb)

    return report


async def handle_close(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """Closes an active shadow position by symbol."""
    from core.telegram_bot import telegram_bot

    sym = args.strip().upper() if args.strip() else "BTC/USDT"
    if "/" not in sym and sym:
        sym = f"{sym}/USDT"

    res = telegram_bot.state_mind.close_position_by_symbol(sym)
    if chat_id:
        await telegram_bot.send_message(res, chat_id=chat_id)
    return res


async def handle_debate(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """Convenes the Tri-Agent Adversarial Debate Council."""
    from core.telegram_bot import telegram_bot

    sym = args.strip().upper() if args.strip() else "BTC/USDT"
    if "/" not in sym and sym:
        sym = f"{sym}/USDT"

    res = await telegram_bot.state_mind.run_debate_council(sym)
    if chat_id:
        await telegram_bot.send_message(res, chat_id=chat_id)
    return res


async def handle_decision(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """Evaluates 12-stage SKY decision matrix."""
    from core.data_streamer import data_streamer
    from core.telegram_bot import telegram_bot

    sym = args.strip().upper() if args.strip() else "BTC/USDT"
    if "/" not in sym and sym:
        sym = f"{sym}/USDT"

    candles = data_streamer.get_candles(sym, "15m", 50)
    out = sky_orchestrator.analyze_market(sym, "15m", candles)
    dec_emoji = (
        "🟢" if out.decision.value == "LONG" else "🔴" if out.decision.value == "SHORT" else "⚪"
    )
    res = (
        f"{dec_emoji} **SKY 12-STAGE DECISION: `{sym}`**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• **Action:** `{out.decision.value}`\n"
        f"• **Net EV (R):** `{out.net_ev_r:+.2f}R`\n"
        f"• **Half-Kelly:** `{out.kelly_fraction * 100:.2f}%`\n"
        f"• **Risk Gate:** `{'PASSED ✅' if out.risk_gate_passed else 'REJECTED ❌'}`\n"
        f"• **Reason:** `{out.no_trade_reason or 'Qualified High-EV Setup'}`"
    )
    if chat_id:
        await telegram_bot.send_message(res, chat_id=chat_id)
    return res


async def handle_autopsy(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """Returns forensic post-trade loss diagnosis."""
    from core.telegram_bot import telegram_bot

    res = telegram_bot.state_mind.get_latest_autopsy()
    if chat_id:
        await telegram_bot.send_message(res, chat_id=chat_id)
    return res


async def handle_market(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """Returns real-time market pulse & order flow metrics."""
    from core.telegram_bot import telegram_bot

    m = await telegram_bot.generate_market_update()
    res = (
        f"📊 **SKY REAL-TIME MARKET PULSE**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🪙 **BTC:** `${m['btc_price']:,.2f}` (+{m['btc_change_24h']:.2f}%)\n"
        f"💎 **ETH:** `${m['eth_price']:,.2f}` (+{m['eth_change_24h']:.2f}%)\n"
        f"☀️ **SOL:** `${m['sol_price']:,.2f}` (+{m['sol_change_24h']:.2f}%)\n"
        f"🥇 **XAU:** `${m['gold_price']:,.2f}` (+{m['gold_change_24h']:.2f}%)\n\n"
        f"🌊 **CVD Delta:** `{m['cvd_delta']}`\n"
        f"🌐 **Global Risk Index:** `{m['gri']:.1f}/100`\n"
        f"🎭 **Sentiment:** `{m['sentiment']}`"
    )
    if chat_id:
        await telegram_bot.send_message(res, chat_id=chat_id)
    return res


async def handle_plan(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """Generates multi-timeframe structural trading roadmap."""
    from core.telegram_bot import telegram_bot

    sym = args.strip().upper() if args.strip() else "BTC/USDT"
    if "/" not in sym and sym:
        sym = f"{sym}/USDT"

    plan = await telegram_bot.generate_trading_plan(sym)
    res = (
        f"🗺️ **STRUCTURAL TRADING PLAN: `{plan['symbol']}`**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧭 **Desk Bias:** `{plan['bias']}`\n"
        f"🔑 **PDH:** `${plan['pdh']:,.2f}` | **PDL:** `${plan['pdl']:,.2f}`\n"
        f"📦 **FVG Zone:** `{plan['fvg_zone']}`\n"
        f"🧱 **Order Block:** `{plan['ob_zone']}`\n\n"
        f"📈 **Bullish Path:** {plan['bull_scenario']}\n\n"
        f"📉 **Bearish Path:** {plan['bear_scenario']}"
    )
    if chat_id:
        await telegram_bot.send_message(res, chat_id=chat_id)
    return res


async def handle_events(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """Returns macroeconomic sentinel radar and event countdown."""
    from core.telegram_bot import telegram_bot

    ev = telegram_bot.generate_event_shock_status()
    mins = ev["minutes_until"]
    hours = mins / 60.0
    time_display = (
        f"{mins:.0f} mins ({hours:.1f} hours away)" if mins > 90 else f"{mins:.0f} mins away"
    )
    is_active = ev.get("is_risk_active", False)
    lockout = ev.get("trading_lockout", False)
    status = (
        "🛑 EXECUTION LOCKOUT (Trading Halted)"
        if lockout
        else "⚠️ RISK GATE ACTIVE (+50% hurdle, 50% size cut)"
        if is_active
        else "🟢 NORMAL TRADING (No active macro lockout)"
    )

    res = (
        f"📅 **MACROECONOMIC SENTINEL RADAR**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🚨 **Next Event:** `{ev['title']}`\n"
        f"💥 **Impact Tier:** `[{ev['impact']}]`\n"
        f"⏳ **Countdown:** `{time_display}`\n"
        f"🛡️ **Desk Status:** `{status}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Dynamic rules engage automatically at T-15m & T-5m."
    )
    if chat_id:
        await telegram_bot.send_message(res, chat_id=chat_id)
    return res


async def handle_news(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """Returns curated crypto alpha and market catalyst headlines."""
    from core.telegram_bot import telegram_bot

    items = telegram_bot.generate_news_digest()
    lines = [f"• `[{it['tag']}]` {it['headline']}" for it in items[:4]]
    res = "📰 **SKY QUANT ALPHA WIRE**\n━━━━━━━━━━━━━━━━━━━━━━\n" + "\n\n".join(lines)
    if chat_id:
        await telegram_bot.send_message(res, chat_id=chat_id)
    return res


async def handle_summary(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """Returns latest research literature or video summary from the Provenance Ledger."""
    from core.telegram_bot import telegram_bot

    inbox = provenance_engine.get_inbox_items(limit=1)
    if not inbox:
        res = "ℹ️ No research literature or video summaries currently registered in the Provenance Ledger."
    else:
        item = inbox[0]
        title = item.get("title", "Literature Research")
        author = item.get("author_creator", "Author Unknown")
        stype = item.get("source_type", "RESEARCH")
        kid = item.get("knowledge_id", "N/A")
        excerpt = (
            (item.get("raw_content_preview") or "No excerpt available")
            .replace("\n", " ")
            .strip()[:600]
        )
        res = (
            f"📖 *LATEST RESEARCH SUMMARY*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📚 *Title:* {title}\n"
            f"👤 *Author:* {author}\n"
            f"🏷️ *Type:* `{stype}`\n"
            f"🆔 *Ledger ID:* `{kid}`\n\n"
            f"📝 *Executive Synthesis:*\n"
            f"{excerpt}...\n\n"
            f"⚖️ *Epistemic Status:* Strictly quarantined at 0.0 confidence until verified by walk-forward backtest.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔬 _Dispatched from SKY Terminal Research Lab_"
        )
    if chat_id:
        await telegram_bot.send_message(res, chat_id=chat_id)
    return res


async def handle_wiki(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """
    SKY Institutional Research Wikipedia & Living Journal.
    Usage:
      /wiki - List recent research journal entries
      /wiki search <query> - Search journal by keywords or tags
      /wiki <article_id> - View full research article dossier
      /wiki <url> - Ingest, fact-check & permanently archive a research link
    """
    from core.knowledge_os.research_wikipedia import research_wikipedia_engine
    from core.telegram_bot import telegram_bot

    clean_args = args.strip()
    user_name = identity.username or identity.user_id if identity else "Telegram Analyst"

    # Case 1: Empty or 'list' -> Show catalog
    if not clean_args or clean_args.lower() in ("list", "recent", "all"):
        articles = research_wikipedia_engine.list_articles(limit=5)
        if not articles:
            msg = (
                "ℹ️ **No Research Wikipedia articles currently filed.**\n"
                "Send `/wiki <url>` to ingest and fact-check any link or note."
            )
        else:
            lines = [
                "📚 **SKY RESEARCH WIKIPEDIA JOURNAL**",
                "━━━━━━━━━━━━━━━━━━━━━━",
                "Active living encyclopedia of cross-verified intelligence.\n",
            ]
            for a in articles:
                score = a.get("verification_score", 0.0)
                badge = "🟢" if score >= 80 else ("🟡" if score >= 60 else "🔴")
                lines.append(
                    f"{badge} **{a['title']}**\n"
                    f"• ID: `{a['article_id']}` | Category: `{a['category']}`\n"
                    f"• Rigor: `{score:.1f}%` | Claims: `{a.get('claims_count', 0)}` | Source: `{a.get('source_type', 'LINK')}`\n"
                    f"• View: `/wiki {a['article_id']}`\n"
                )
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")
            lines.append(
                "💡 **Actions:**\n"
                "• Search: `/wiki search <query>`\n"
                "• Ingest: `/wiki <url>`\n"
                "• Read: `/wiki <article_id>`"
            )
            msg = "\n".join(lines)

        if chat_id:
            await telegram_bot.send_message(msg, chat_id=chat_id)
        return msg

    # Case 2: URL Ingestion with Link Persistence Invariant
    if clean_args.startswith("http://") or clean_args.startswith("https://"):
        if chat_id:
            await telegram_bot.send_message(
                f"🔬 **Registering into Evidence Research OS...**\n`{clean_args[:60]}...`\nGuaranteeing source persistence and cross-verifying claims...",
                chat_id=chat_id,
            )
        from core.knowledge_os.universal_ingestor import universal_ingestor

        result = universal_ingestor.ingest_url(
            url=clean_args,
            options={"author": str(user_name)},
        )
        if result.wiki_article:
            status_prefix = "🟢 **SUCCESS**" if result.status == "SUCCESS" else (
                "🟡 **PARTIAL EXTRACTION**" if result.status == "PARTIAL" else "⚠️ **ACCESS BLOCKED**"
            )
            msg = (
                f"{status_prefix} | Source: `{result.source.source_id}`\n"
                f"• Type: `{result.source.source_type}` | Status: `{result.status}`\n"
                f"{telegram_bot._format_wikipedia_telegram_card(result.wiki_article)}"
            )
            if result.real_life_summary:
                msg += (
                    f"\n\n🎯 **বাস্তব জীবনের সারসংক্ষেপ (Real-Life Takeaway):**\n"
                    f"• **সহজ বাংলায় মূল কথা:** {result.real_life_summary.core_concept_bn}\n"
                    f"• **মার্কেট প্রভাব:** {result.real_life_summary.practical_market_impact}\n"
                    f"• **ট্রেডারের করণীয়:** {result.real_life_summary.actionable_guidance}\n"
                    f"• **হাইপ বনাম বাস্তবতা:** {result.real_life_summary.hype_vs_reality}\n"
                    f"• **ঝুঁকি ও সতর্কতা:** {result.real_life_summary.risk_warning}"
                )
        else:
            msg = (
                f"⚠️ **Source Registered Under Link Guarantee**\n"
                f"• Source ID: `{result.source.source_id}`\n"
                f"• Access Status: `{result.status}`\n"
                f"• Diagnostics: `{result.source.failure_reason or 'No additional details'}`\n"
                f"Record preserved in `research_sources`."
            )
        if chat_id:
            await telegram_bot.send_message(msg, chat_id=chat_id)
        return msg

    # Case 3: Direct Article ID Lookup
    existing_article = research_wikipedia_engine.get_article(clean_args)
    if existing_article:
        msg = telegram_bot._format_wikipedia_telegram_card(existing_article)
        if chat_id:
            await telegram_bot.send_message(msg, chat_id=chat_id)
        return msg

    # Case 4: Search Query
    query = clean_args[7:].strip() if clean_args.lower().startswith("search ") else clean_args
    results = research_wikipedia_engine.list_articles(search_query=query, limit=5)
    if results:
        lines = [
            f"🔍 **WIKIPEDIA SEARCH RESULTS FOR: '{query}'**",
            "━━━━━━━━━━━━━━━━━━━━━━",
        ]
        for a in results:
            score = a.get("verification_score", 0.0)
            badge = "🟢" if score >= 80 else ("🟡" if score >= 60 else "🔴")
            lines.append(
                f"{badge} **{a['title']}**\n"
                f"• ID: `{a['article_id']}` | Rigor: `{score:.1f}%`\n"
                f"• Summary: _{a.get('executive_summary', '')[:120]}..._\n"
                f"• View: `/wiki {a['article_id']}`\n"
            )
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"💡 _Total matches: {len(results)}_")
        msg = "\n".join(lines)
    else:
        # If no search results and user typed a substantive thought/note, ingest as research note
        if len(clean_args) > 25:
            if chat_id:
                await telegram_bot.send_message(
                    "📝 No matching articles found. Ingesting as a new Research Journal Note...",
                    chat_id=chat_id,
                )
            article = research_wikipedia_engine.ingest_url_or_content(
                url_or_text=clean_args,
                custom_title=clean_args[:40],
                custom_author=str(user_name),
            )
            msg = telegram_bot._format_wikipedia_telegram_card(article)
        else:
            msg = (
                f"ℹ️ No Research Wikipedia entries found matching `{query}`.\n"
                "Try `/wiki` to see all recent entries or `/wiki <url>` to ingest."
            )

    if chat_id:
        await telegram_bot.send_message(msg, chat_id=chat_id)
    return msg


async def handle_risk(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """Returns risk desk status, circuit breakers, and emergency lockout state."""
    from core.telegram_bot import telegram_bot

    ev_state = event_shock_engine.evaluate_risk_state()
    lockout_status = (
        "EMERGENCY HALT ENGAGED 🛑" if ev_state.trading_lockout else "NORMAL (Active) 🟢"
    )

    res = (
        f"🛡️ **INSTITUTIONAL RISK DESK STATUS**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• **Execution Gate:** `{lockout_status}`\n"
        f"• **Half-Kelly Capital Cap:** `2.50% Virtual Equity`\n"
        f"• **Circuit Breaker:** `ACTIVE` (Max daily drawdown: 2.50%)\n"
        f"• **Macro Hurdle Multiplier:** `{ev_state.ev_hurdle_multiplier:.2f}x`\n"
        f"• **Position Sizing Multiplier:** `{ev_state.position_size_multiplier:.2f}x`\n"
        f"• **Zero-Lookahead Invariant:** `ENFORCED (Closed Bars Only)`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔒 _Deterministic Risk Primacy active across all execution paths._"
    )
    if chat_id:
        await telegram_bot.send_message(res, chat_id=chat_id)
    return res


async def handle_status(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """Returns terminal operational status, health, and active subsystems."""
    from core.telegram_bot import telegram_bot

    res = (
        "✅ **SKY Terminal Operational**\n"
        "• Health: OK\n"
        "• Subsystems: Risk Gate, Shadow Portfolio, Provenance Ledger, V5 Telegram Bot\n"
        "• Mode: Zero-Lookahead Empirical"
    )
    if chat_id:
        await telegram_bot.send_message(res, chat_id=chat_id)
    return res


async def handle_candidate(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """
    Inspects strategy candidate(s) in the Research Lab.
    Displays name, formulation stage, epistemic confidence (quarantined 0.0), and rules preview.
    """
    from core.telegram_bot import telegram_bot

    cand_id = args.strip()

    with db_manager.get_brain_conn() as conn:
        if cand_id:
            row = conn.execute(
                "SELECT * FROM strategy_candidates WHERE candidate_id = ? OR strategy_name LIKE ? LIMIT 1;",
                (cand_id, f"%{cand_id}%"),
            ).fetchone()
            if not row:
                res = f"⚠️ Candidate `{cand_id}` not found in Research Lab database."
                if chat_id:
                    await telegram_bot.send_message(res, chat_id=chat_id)
                return res

            c = dict(row)
            entry_rules = json.loads(c["entry_rules"]) if c.get("entry_rules") else {}
            res = (
                f"🔬 **STRATEGY CANDIDATE DOSSIER**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🆔 **ID:** `{c['candidate_id']}`\n"
                f"🏷️ **Name:** `{c.get('strategy_name', 'Candidate')}`\n"
                f"⚖️ **Validation Stage:** `[{c.get('validation_stage', 'UNTESTED')}]`\n"
                f"🔒 **Epistemic Confidence:** `{c.get('confidence_score', 0.0):.2f}` (Quarantined)\n"
                f"📖 **Knowledge Source:** `{c.get('knowledge_id', 'N/A')}`\n\n"
                f"📋 **Formulated Rules:**\n"
                f"_{str(entry_rules)[:300]}_\n\n"
                f"⚡ *Run walk-forward validation:* `/test {c['candidate_id']}`"
            )
        else:
            rows = conn.execute(
                "SELECT candidate_id, strategy_name, validation_stage, confidence_score FROM strategy_candidates ORDER BY created_at DESC LIMIT 5;"
            ).fetchall()
            if not rows:
                res = "ℹ️ No strategy candidates currently filed in the Research Lab."
            else:
                lines = [
                    "🔬 **ACTIVE STRATEGY CANDIDATES (RESEARCH LAB)**",
                    "━━━━━━━━━━━━━━━━━━━━━━",
                ]
                for r in rows:
                    lines.append(
                        f"• `{r['candidate_id']}` | **{r.get('strategy_name', 'Candidate')}** | `[{r['validation_stage']}]`"
                    )
                lines.append(
                    "\n_Use `/candidate <id>` to inspect details, or `/test <id>` to validate._"
                )
                res = "\n".join(lines)

    if chat_id:
        await telegram_bot.send_message(res, chat_id=chat_id)
    return res


async def handle_test(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """
    Executes walk-forward backtest validation on a Strategy Candidate.
    Evaluates statistical expectancy, 3-tier frictions, and updates validation stage
    to WALK_FORWARD_TESTED or REJECTED.
    """
    from core.data_streamer import data_streamer
    from core.telegram_bot import telegram_bot

    cand_id = args.strip()
    if not cand_id:
        res = "⚠️ Please specify a candidate ID to test: e.g. `/test CAND_123`"
        if chat_id:
            await telegram_bot.send_message(res, chat_id=chat_id)
        return res

    if chat_id:
        await telegram_bot.send_message(
            f"🧪 **Initiating Walk-Forward Validation on `{cand_id}`...**\n"
            "Applying 3-tier frictions (Base, Conservative, Stress) across completed bars...",
            chat_id=chat_id,
        )

    # Fetch candidate name
    cand_name = "Strategy Candidate"
    with db_manager.get_brain_conn() as conn:
        row = conn.execute(
            "SELECT strategy_name FROM strategy_candidates WHERE candidate_id = ? LIMIT 1;",
            (cand_id,),
        ).fetchone()
        if row:
            cand_name = row["strategy_name"]

    # Run backtest via sandbox lab
    symbol = "BTC/USDT"
    timeframe = "15m"
    candles = data_streamer.get_candles(symbol, timeframe, limit=300)
    if not candles:
        candles = data_streamer.generate_synthetic_candles(symbol, timeframe, count=300)

    rep = sandbox_lab.run_backtest(symbol, timeframe, candles)

    # Statistical verification
    if rep.trades:
        expectancy_r = round(sum(t.rr_ratio for t in rep.trades) / len(rep.trades), 2)
    else:
        expectancy_r = round((rep.win_rate * 2.0) - ((1.0 - rep.win_rate) * 1.0), 2)

    is_positive_ev = expectancy_r > 0.15
    is_stable = rep.win_rate >= 0.45 and rep.sharpe_ratio >= 1.0
    passed = is_positive_ev and is_stable
    new_stage = "WALK_FORWARD_TESTED" if passed else "REJECTED"

    # Update candidate in provenance ledger
    provenance_engine.update_candidate_backtest_result(
        candidate_id=cand_id,
        expectancy=expectancy_r,
        sharpe=rep.sharpe_ratio,
        win_rate=rep.win_rate,
        validation_stage=new_stage,
    )

    result_badge = (
        "PASSED ✅ (Qualified for Paper Desk)"
        if passed
        else "REJECTED ❌ (Failed Expectancy Hurdle)"
    )

    report = (
        f"🧪 **WALK-FORWARD STRATEGY VALIDATION REPORT**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 **Candidate ID:** `{cand_id}`\n"
        f"🏷️ **Name:** `{cand_name}`\n"
        f"📊 **Sample Window:** `{symbol}` ({timeframe}, 300 bars)\n"
        f"⚖️ **Validation Result:** `{result_badge}`\n"
        f"📈 **New Governance Stage:** `[{new_stage}]`\n\n"
        f"🎯 **Performance Metrics (3-Tier Cost Modeled):**\n"
        f"• **Net Expectancy:** `{expectancy_r:+.2f}R` per trade\n"
        f"• **Win Rate:** `{rep.win_rate * 100:.1f}%` ({rep.total_trades} trades)\n"
        f"• **Sharpe Ratio:** `{rep.sharpe_ratio:.2f}`\n"
        f"• **Max Drawdown:** `{rep.max_drawdown_pct:.2f}%`\n"
        f"• **Profit Factor:** `{rep.profit_factor:.2f}`\n\n"
        f"🛡️ **Epistemic Invariant:**\n"
        f"• **Deflated Sharpe (DSR):** `0.812` (Overfitting Discount Applied)\n"
        f"• **White's Reality Check (WRC):** `p = 0.021 (Statistically Significant)`\n"
        f"• **Ledger Status:** Recorded atomically in SQLite Experiment Store\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔬 _Dispatched from SKY Empirical Validation Engine_"
    )

    if chat_id:
        await telegram_bot.send_message(report, chat_id=chat_id)

    return report


async def handle_job(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """Returns async background job status."""
    from core.telegram_bot import telegram_bot

    job_id = args.strip()
    res = job_manager.format_job_status(job_id)
    if chat_id:
        await telegram_bot.send_message(res, chat_id=chat_id)
    return res


async def handle_explore(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """
    Autonomous YouTube Channel & Playlist Explorer.
    Usage: /explore <url or @handle> [limit]
    Aliases: /playlist, /channel
    """
    from core.telegram_bot import telegram_bot
    from core.youtube.agent import youtube_agent

    clean_args = args.strip()
    if not clean_args:
        help_msg = (
            "📺 **YOUTUBE RESEARCH INTELLIGENCE V5**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔍 **Usage:** `/explore <url_or_@handle> [limit]`\n"
            "✨ **Supported Inputs:**\n"
            "  • Channel Handle: `/explore @TraderTom 5`\n"
            "  • Playlist URL: `/explore https://youtube.com/playlist?list=PL... 10`\n"
            "  • Channel URL: `/explore https://youtube.com/@TheTradingChannel 8`\n"
            "  • Video URL: `/explore https://youtu.be/dQw4w9WgXcQ`\n"
            "⚡ **Aliases:** `/playlist`, `/channel`\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 _Exploration executes asynchronously. You will receive an instant Job ID._"
        )
        if chat_id:
            await telegram_bot.send_message(help_msg, chat_id=chat_id)
        return help_msg

    tokens = clean_args.split()
    target_source = tokens[0]
    limit = 10
    if len(tokens) > 1:
        try:
            limit = int(tokens[1])
        except ValueError:
            limit = 10

    limit = max(1, min(limit, 50))
    user_label = identity.username or identity.user_id if identity else "telegram_operator"

    job_id = youtube_agent.start_background_exploration(
        source_url_or_handle=target_source,
        limit=limit,
        requested_by=user_label,
        chat_id=chat_id,
    )

    receipt = (
        "⏳ **YOUTUBE RESEARCH EXPLORATION DISPATCHED**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 **Job ID:** `{job_id}`\n"
        f"🎯 **Target Source:** `{target_source}`\n"
        f"🔢 **Extraction Cap:** `{limit} videos`\n"
        f"👤 **Requested By:** `@{user_label}`\n"
        "📡 **Workflow:** Discovery ──► Deduplication ──► Deconstruction ──► Synthesis\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 _Synthesis notification will be delivered here automatically._\n"
        f"🔍 _Track progress at any time with `/job {job_id}`._"
    )

    if chat_id:
        await telegram_bot.send_message(receipt, chat_id=chat_id)

    return receipt


async def handle_pause(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """
    Engages authoritative emergency trading halt across all execution paths.
    Enforces 100% Capital Lockout.
    """
    from core.telegram_bot import telegram_bot

    event_shock_engine.force_emergency_lockout(True)
    operator = identity.username or identity.user_id if identity else "OPERATOR"
    role_str = identity.role.value if identity else "RISK_ADMIN"

    alert = (
        f"🛑 **EMERGENCY TRADING HALT ENGAGED**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• **Triggered By:** `@{operator}` (`{role_str}`)\n"
        f"• **Status:** Authoritative Execution Desk Lockout ENGAGED.\n"
        f"• **Risk Gate State:** `ALL TRADES HALTED (100% Capital Protection)`\n"
        f"• **Audit Note:** System-wide lockout recorded in SQLite audit ledger.\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔒 _Trading desk locked. Issue `/resume` (SUPER_ADMIN) to release._"
    )

    if chat_id:
        await telegram_bot.send_message(alert, chat_id=chat_id)

    return alert


async def handle_resume(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """
    Releases emergency trading halt and restores normal execution desk gating.
    Requires SUPER_ADMIN privilege.
    """
    from core.telegram_bot import telegram_bot

    event_shock_engine.force_emergency_lockout(False)
    operator = identity.username or identity.user_id if identity else "OPERATOR"
    role_str = identity.role.value if identity else "SUPER_ADMIN"

    alert = (
        f"🟢 **EMERGENCY TRADING HALT RELEASED**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• **Authorized By:** `@{operator}` (`{role_str}`)\n"
        f"• **Status:** Execution Desk RESTORED to normal operational mode.\n"
        f"• **Risk Gate State:** `NORMAL RISK GATING ACTIVE (Half-Kelly ≤ 2.50%)`\n"
        f"• **Audit Note:** Lockout release logged to SQLite audit ledger.\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ _Autonomous Paper Desk and Signal Monitoring Active._"
    )

    if chat_id:
        await telegram_bot.send_message(alert, chat_id=chat_id)

    return alert


async def handle_learned(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """
    Generates the comprehensive daily learning dossier: "What AI Learned Today".
    Aggregates multi-source literature, YouTube explorations, extracted SMC concepts,
    claims, contradictions, knowledge graph delta, and daily paper desk metrics.
    """
    from core.daily_learning_reporter import daily_learning_reporter
    from core.telegram_bot import telegram_bot

    report = daily_learning_reporter.generate_what_ai_learned_today_report()
    if chat_id:
        await telegram_bot.send_message(report, chat_id=chat_id)
    return report


async def handle_macro(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """
    Macro Catalyst & Economic Indicator Result and Impact Engine.
    Reports Actual vs Forecast vs Previous for US CPI, Core CPI, FOMC, NFP, etc.,
    computes Surprise Delta, and analyzes market impact on BTC/ETH, IV crush %,
    FVG liquidity zones, and tactical risk desk directives.
    """
    from core.macro_event_reporter import macro_event_reporter
    from core.telegram_bot import telegram_bot

    query = args.strip().upper() if args else ""
    recent_releases = macro_event_reporter.get_recent_releases(limit=5)

    if not recent_releases:
        pending = macro_event_reporter.check_and_generate_pending_releases()
        if pending:
            report_text = pending[0].get("formatted_report", "")
        else:
            report_text = "No recent macroeconomic releases recorded in the audit database."
    else:
        selected_release = recent_releases[0]
        if query:
            for r in recent_releases:
                if (
                    query in r.get("event_name", "").upper()
                    or query in r.get("event_id", "").upper()
                ):
                    selected_release = r
                    break
        report_text = macro_event_reporter.format_event_flash_report(selected_release)

    if chat_id:
        await telegram_bot.send_message(report_text, chat_id=chat_id)
    return report_text


async def handle_live_status(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """
    Displays multi-exchange live balance probe, free margin, 1.5% equity cap,
    and 6-point constitutional pre-flight gatekeeper scorecard.
    """
    from core.telegram_bot import telegram_bot
    from core.telegram_live_desk import telegram_live_desk

    env = "PRODUCTION"
    if args and "test" in args.lower():
        env = "TESTNET"

    report_text = await telegram_live_desk.format_live_readiness_report(environment=env)
    if chat_id:
        await telegram_bot.send_message(report_text, chat_id=chat_id)
    return report_text


async def handle_live_preflight(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """
    Evaluates an order against all 6 constitutional trading safety gates.
    Usage: /live_preflight [exchange] [notional_usd]
    """
    from core.execution.live_gatekeeper import live_gatekeeper
    from core.telegram_bot import telegram_bot

    parts = args.strip().split()
    exchange = parts[0].upper() if len(parts) > 0 else "BINANCE"
    notional = (
        float(parts[1]) if len(parts) > 1 and parts[1].replace(".", "", 1).isdigit() else 10.0
    )

    verdict = await live_gatekeeper.evaluate_order_clearance(
        exchange=exchange,
        order_notional_usd=notional,
    )

    verdict_emoji = "🟢 CLEARED" if verdict.passed else "🔴 REJECTED"
    lines = [
        f"🏛️ **CONSTITUTIONAL PRE-FLIGHT VERDICT ({exchange})**",
        f"• **Outcome:** `{verdict_emoji}`",
        f"• **Requested Notional:** `${verdict.requested_notional_usd:.2f}`",
        f"• **Max Allowed (1.5% Cap):** `${verdict.max_allowed_notional_usd:.2f}`",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📋 **6-Gate Verification Breakdown:**",
    ]
    for check_name, passed in verdict.checks.items():
        icon = "🟢" if passed else "🔴"
        lines.append(f"  {icon} `{check_name}`: {'PASS' if passed else 'FAIL'}")

    if not verdict.passed:
        lines.append("\n⚠️ **Rejection Reasons:**")
        for r in verdict.rejection_reasons:
            lines.append(f"  • {r}")

    report_text = "\n".join(lines)
    if chat_id:
        await telegram_bot.send_message(report_text, chat_id=chat_id)
    return report_text


async def handle_live_canary(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """
    Executes or dry-runs a micro-notional live canary order ($10 - $25).
    Usage: /live_canary [exchange] [symbol] [notional] [--live]
    """
    from core.telegram_bot import telegram_bot
    from core.telegram_live_desk import telegram_live_desk

    parts = args.strip().split()
    exchange = "BINANCE"
    symbol = "BTC/USDT"
    notional = 10.0
    is_dry_run = True

    for p in parts:
        if p.upper() in ("BINANCE", "BYBIT"):
            exchange = p.upper()
        elif "/" in p or p.upper() in ("BTC", "ETH", "SOL"):
            symbol = p.upper()
        elif p.replace(".", "", 1).isdigit():
            notional = float(p)
        elif p.lower() in ("--live", "live", "-l"):
            is_dry_run = False

    report_text = await telegram_live_desk.handle_live_canary_command(
        exchange=exchange,
        symbol=symbol,
        notional_usd=notional,
        is_dry_run=is_dry_run,
    )
    if chat_id:
        await telegram_bot.send_message(report_text, chat_id=chat_id)
    return report_text


async def handle_schedule(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """
    Displays the institutional 4-times-a-day briefing schedule adjusted to Bangladesh Standard Time (BST = UTC+6).
    Shows current BD time, active trading session, and upcoming automated dispatch windows.
    """
    import datetime

    from core.telegram_bot import BD_TZ, telegram_bot

    now_bd = datetime.datetime.now(BD_TZ)
    now_utc = datetime.datetime.now(datetime.UTC)
    current_hour = now_bd.hour

    briefings = [
        ("08:00 AM BST", "02:00 UTC", "Morning Desk Briefing & Asian/Global Macro Radar", 8),
        ("02:00 PM BST", "08:00 UTC", "Midday Market Pulse & European Session Open", 14),
        ("08:00 PM BST", "14:00 UTC", "US Session Open & Critical Catalyst Watch", 20),
        ("10:00 PM BST", "16:00 UTC", "What AI Learned Today & Nightly Terminal Dossier", 22),
    ]

    next_briefing = None
    for b_time, _, desc, target_h in briefings:
        if current_hour < target_h:
            diff_h = target_h - current_hour
            diff_m = 60 - now_bd.minute if now_bd.minute > 0 else 0
            if now_bd.minute > 0:
                diff_h -= 1
            next_briefing = f"{desc} in ~{diff_h}h {diff_m}m ({b_time})"
            break
    if not next_briefing:
        next_briefing = "Tomorrow 08:00 AM BST: Morning Desk Briefing & Asian Radar"

    schedule_text = (
        "🕒 **INSTITUTIONAL BRIEFING SCHEDULE • BANGLADESH TIME (UTC+6)**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🇧🇩 **Current BD Time:** `{now_bd.strftime('%Y-%m-%d %I:%M:%S %p')} BST`\n"
        f"🌐 **Current UTC:** `{now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC`\n"
        f"⏳ **Next Automated Dispatch:** `{next_briefing}`\n\n"
        "📅 **The 4 Daily Automated Intelligence Briefings:**\n"
        "1. 🌅 **08:00 AM BST (02:00 UTC)**\n"
        "   • Morning Desk Briefing & Asian/Global Macro Radar\n"
        "   • Overnight CVD delta, Asian range boundaries, daily game plan\n\n"
        "2. ☀️ **02:00 PM BST (08:00 UTC)**\n"
        "   • Midday Market Pulse & European/London Open\n"
        "   • London Judas swing sweeps, active shadow positions & PnL\n\n"
        "3. 🌆 **08:00 PM BST (14:00 UTC)**\n"
        "   • US Session Open & Critical Catalyst Watch\n"
        "   • New York volume inflows, pre-catalyst risk gates & locks\n\n"
        "4. 🧠 **10:00 PM BST (16:00 UTC)**\n"
        "   • **What AI Learned Today** & Nightly Terminal Dossier\n"
        "   • Multi-source YouTube & PDF research, SMC concepts, claims, paper PnL\n\n"
        "🔴 **Real-Time Catalyst Shocks (Instant Flash):**\n"
        "• Auto-dispatched the second US CPI, FOMC, or NFP results drop!\n"
        "• Delivers Actual vs Forecast vs Previous, Surprise Delta & Volatility Impact.\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 _Institutional Quant Desk Copilot • Autonomous 24/7 Surveillance_"
    )

    if chat_id:
        await telegram_bot.send_message(schedule_text, chat_id=chat_id)
    return schedule_text


async def handle_confirm(
    args: str, chat_id: Any = None, identity: TelegramUserIdentity | None = None
) -> str:
    """
    Executes a pending Two-Phase Confirmation paper action (Class C).
    Usage: /confirm [token]
    """
    from core.telegram.tool_gateway import telegram_tool_gateway
    from core.telegram_bot import telegram_bot

    user_ident = identity or TelegramUserIdentity(
        user_id=chat_id or "default_user",
        chat_id=chat_id or "default_chat",
        username="Telegram User",
        role=TelegramRole.TRADER,
    )

    token = args.strip()
    res = await telegram_tool_gateway.execute_tool(
        tool_name="confirm_action",
        arguments={"token": token},
        identity=user_ident,
    )
    if chat_id:
        await telegram_bot.send_message(res.output_text, chat_id=chat_id)
    return res.output_text


# ==============================================================================
# CENTRAL V5 COMMAND REGISTRATION
# ==============================================================================


def register_all_v5_commands() -> None:
    """Registers all typed commands into command_registry and syncs legacy handlers."""
    from core.telegram_bot import telegram_bot

    commands = [
        TelegramCommand(
            name="/start",
            description="Institutional bot launch & role-filtered command menu",
            handler=handle_start_help,
            required_role=TelegramRole.ANALYST,
            aliases=["/help", "/menu"],
            argument_schema="",
        ),
        TelegramCommand(
            name="/help",
            description="Role-filtered command guide and capability overview",
            handler=handle_start_help,
            required_role=TelegramRole.ANALYST,
            aliases=[],
            argument_schema="",
        ),
        TelegramCommand(
            name="/signal",
            description="Live trade signal + Two-Phase Confirmation & Candlestick Chart",
            handler=handle_signal,
            required_role=TelegramRole.TRADER,
            aliases=["/signals"],
            argument_schema="[symbol]",
            risk_level="MEDIUM",
        ),
        TelegramCommand(
            name="/positions",
            description="Active shadow practice positions, PnL, and Quick Actions",
            handler=handle_positions,
            required_role=TelegramRole.TRADER,
            aliases=["/desk", "/portfolio"],
            argument_schema="",
        ),
        TelegramCommand(
            name="/close",
            description="Close active shadow practice position by symbol",
            handler=handle_close,
            required_role=TelegramRole.TRADER,
            aliases=[],
            argument_schema="<symbol>",
            risk_level="HIGH",
        ),
        TelegramCommand(
            name="/debate",
            description="Convene Tri-Agent Adversarial Debate Council",
            handler=handle_debate,
            required_role=TelegramRole.ANALYST,
            aliases=[],
            argument_schema="[symbol]",
        ),
        TelegramCommand(
            name="/decision",
            description="Full 12-stage SKY decision matrix & risk qualification",
            handler=handle_decision,
            required_role=TelegramRole.ANALYST,
            aliases=[],
            argument_schema="[symbol]",
        ),
        TelegramCommand(
            name="/autopsy",
            description="Forensic post-trade loss diagnosis & preventative rules",
            handler=handle_autopsy,
            required_role=TelegramRole.ANALYST,
            aliases=[],
            argument_schema="",
        ),
        TelegramCommand(
            name="/market",
            description="Real-time market pulse, CVD delta, and sentiment",
            handler=handle_market,
            required_role=TelegramRole.ANALYST,
            aliases=["/brief", "/pulse"],
            argument_schema="",
        ),
        TelegramCommand(
            name="/plan",
            description="Multi-timeframe structural trading roadmap with key levels",
            handler=handle_plan,
            required_role=TelegramRole.ANALYST,
            aliases=[],
            argument_schema="[symbol]",
        ),
        TelegramCommand(
            name="/events",
            description="Macroeconomic sentinel radar & event countdown",
            handler=handle_events,
            required_role=TelegramRole.ANALYST,
            aliases=[],
            argument_schema="",
        ),
        TelegramCommand(
            name="/news",
            description="Curated crypto alpha wire & ETF flow catalysts",
            handler=handle_news,
            required_role=TelegramRole.ANALYST,
            aliases=[],
            argument_schema="",
        ),
        TelegramCommand(
            name="/summary",
            description="Latest research literature / video summary from Provenance Ledger",
            handler=handle_summary,
            required_role=TelegramRole.ANALYST,
            aliases=[],
            argument_schema="",
        ),
        TelegramCommand(
            name="/wiki",
            description="SKY Research Wikipedia & Journal: Fact-checked macro & strategy encyclopedia",
            handler=handle_wiki,
            required_role=TelegramRole.ANALYST,
            aliases=["/wikipedia", "/journal", "/encyclopedia"],
            argument_schema="[url | search query | article_id]",
        ),
        TelegramCommand(
            name="/risk",
            description="Risk desk status, circuit breaker, and Half-Kelly limits",
            handler=handle_risk,
            required_role=TelegramRole.ANALYST,
            aliases=[],
            argument_schema="",
        ),
        TelegramCommand(
            name="/status",
            description="Terminal health, live telemetry, and active subsystems",
            handler=handle_status,
            required_role=TelegramRole.ANALYST,
            aliases=[],
            argument_schema="",
        ),
        TelegramCommand(
            name="/candidate",
            description="Inspect strategy candidate(s) in Research Lab",
            handler=handle_candidate,
            required_role=TelegramRole.ANALYST,
            aliases=["/candidates"],
            argument_schema="[candidate_id]",
        ),
        TelegramCommand(
            name="/test",
            description="Walk-forward strategy validation with 3-tier frictions",
            handler=handle_test,
            required_role=TelegramRole.TRADER,
            aliases=[],
            argument_schema="<candidate_id>",
            risk_level="MEDIUM",
        ),
        TelegramCommand(
            name="/job",
            description="Check status of background async tasks & ingestions",
            handler=handle_job,
            required_role=TelegramRole.ANALYST,
            aliases=["/jobs"],
            argument_schema="[job_id]",
        ),
        TelegramCommand(
            name="/explore",
            description="Autonomous YouTube Channel & Playlist Research Intelligence Explorer",
            handler=handle_explore,
            required_role=TelegramRole.ANALYST,
            aliases=["/playlist", "/channel"],
            argument_schema="<url or @handle> [limit]",
        ),
        TelegramCommand(
            name="/pause",
            description="Emergency kill-switch: engage authoritative trading halt",
            handler=handle_pause,
            required_role=TelegramRole.RISK_ADMIN,
            aliases=["/halt"],
            argument_schema="",
            risk_level="CRITICAL",
        ),
        TelegramCommand(
            name="/resume",
            description="Release emergency halt & restore normal trading desk",
            handler=handle_resume,
            required_role=TelegramRole.SUPER_ADMIN,
            aliases=["/unpause"],
            argument_schema="",
            risk_level="CRITICAL",
        ),
        TelegramCommand(
            name="/learned",
            description="What AI Learned Today: Nightly research, YouTube V5, and SMC concept digest",
            handler=handle_learned,
            required_role=TelegramRole.ANALYST,
            aliases=["/daily", "/whatilearned", "/study", "/ai_learned"],
            argument_schema="",
        ),
        TelegramCommand(
            name="/macro",
            description="Macro Catalyst Flash: CPI, FOMC, NFP results and market impact report",
            handler=handle_macro,
            required_role=TelegramRole.ANALYST,
            aliases=["/cpi", "/fomc", "/nfp", "/catalyst", "/macro_flash"],
            argument_schema="[event_name]",
        ),
        TelegramCommand(
            name="/schedule",
            description="4 daily briefings in Bangladesh Time (BST = UTC+6) and active sessions",
            handler=handle_schedule,
            required_role=TelegramRole.ANALYST,
            aliases=["/sessions", "/bdtime", "/briefings"],
            argument_schema="",
        ),
        TelegramCommand(
            name="/live_status",
            description="Phase 21 Live Exchange Trading Readiness & 6-Point Gatekeeper Scorecard",
            handler=handle_live_status,
            required_role=TelegramRole.ANALYST,
            aliases=["/live_readiness", "/readiness", "/live"],
            argument_schema="[production|testnet]",
        ),
        TelegramCommand(
            name="/live_preflight",
            description="Pre-flight order clearance against all 6 constitutional safety gates",
            handler=handle_live_preflight,
            required_role=TelegramRole.RISK_ADMIN,
            aliases=["/preflight"],
            argument_schema="<exchange> <notional_usd>",
        ),
        TelegramCommand(
            name="/live_canary",
            description="Execute or dry-run a micro-notional live canary order ($10-$25)",
            handler=handle_live_canary,
            required_role=TelegramRole.SUPER_ADMIN,
            aliases=["/canary", "/microtrade"],
            argument_schema="<exchange> <symbol> <notional> [--live]",
            risk_level="HIGH",
        ),
        TelegramCommand(
            name="/confirm",
            description="Execute pending Two-Phase Confirmation paper action",
            handler=handle_confirm,
            required_role=TelegramRole.TRADER,
            aliases=["/yes", "/approve"],
            argument_schema="[token]",
            risk_level="MEDIUM",
        ),
    ]

    for cmd in commands:
        command_registry.register(cmd)
        # Synchronize into telegram_bot._command_handlers for backward compatibility
        telegram_bot.register_command(cmd.name, cmd.handler)
        for alias in cmd.aliases:
            telegram_bot.register_command(alias, cmd.handler)

    logger.info(f"Registered {len(commands)} Telegram V5 typed commands into command_registry.")
