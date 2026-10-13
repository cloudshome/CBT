"""
tests/test_telegram_intelligence_nl.py
======================================
Comprehensive verification suite for Telegram Bot natural language conversational intelligence,
live ticker dossier, bilingual English/Bengali market overview, and fault-tolerant telemetry synthesis.
"""

import pytest
import time

from core.telegram.agent_planner import telegram_agent_planner
from core.telegram.rbac import TelegramRole, TelegramUserIdentity, rbac_registry
from core.telegram.tool_gateway import telegram_tool_gateway
from core.telegram_bot import telegram_bot


@pytest.fixture
def superadmin_identity():
    uid = 999001
    rbac_registry.register_user_role(uid, TelegramRole.SUPER_ADMIN)
    return TelegramUserIdentity(
        user_id=uid,
        chat_id=uid,
        username="superadmin_test",
        role=TelegramRole.SUPER_ADMIN,
    )


def test_intent_resolution_standalone_tickers():
    """Verifies that single symbol mentions immediately resolve to live ticker dossiers."""
    tickers = ["BTC", "btc", "bitcoin", "ETH", "eth", "ethereum", "SOL", "sol", "solana", "GOLD", "gold", "xau", "বিটকয়েন", "ইথেরিয়াম"]
    for t in tickers:
        dec = telegram_agent_planner.resolve_intent(t, "user_1")
        assert dec.intent == "GET_PRICE_OR_DOSSIER", f"Failed for {t}: {dec.intent}"
        assert dec.tool_name == "get_live_ticker_dossier"
        assert dec.tool_args is not None
        assert "symbol" in dec.tool_args


def test_intent_resolution_price_queries():
    """Verifies that natural language price questions map to live ticker dossiers."""
    price_queries = [
        ("btc price", "BTC/USDT", "en"),
        ("bitcoin price", "BTC/USDT", "en"),
        ("price of btc", "BTC/USDT", "en"),
        ("eth price", "ETH/USDT", "en"),
        ("sol price", "SOL/USDT", "en"),
        ("gold price", "XAU/USD", "en"),
        ("বিটকয়েনের দাম কত", "BTC/USDT", "bn"),
        ("ইথেরিয়াম দাম", "ETH/USDT", "bn"),
        ("dam koto", "BTC/USDT", "bn"),
    ]
    for q, expected_sym, expected_lang in price_queries:
        dec = telegram_agent_planner.resolve_intent(q, "user_1")
        assert dec.intent == "GET_PRICE_OR_DOSSIER", f"Failed for {q}"
        assert dec.tool_name == "get_live_ticker_dossier"
        assert dec.tool_args["symbol"] == expected_sym
        assert dec.tool_args["language"] == expected_lang


def test_intent_resolution_market_overview():
    """Verifies market state and overview questions resolve to get_market_overview."""
    market_queries = [
        ("market", "en"),
        ("market overview", "en"),
        ("crypto market", "en"),
        ("how is the market", "en"),
        ("মার্কেট কেমন", "bn"),
        ("মার্কেটের অবস্থা কি", "bn"),
        ("মার্কেট আপডেট", "bn"),
    ]
    for q, expected_lang in market_queries:
        dec = telegram_agent_planner.resolve_intent(q, "user_1")
        assert dec.intent == "GET_MARKET_OVERVIEW", f"Failed for {q}"
        assert dec.tool_name == "get_market_overview"
        assert dec.tool_args["language"] == expected_lang


def test_intent_resolution_account_and_concepts():
    """Verifies account balance, equity, and concept inquiries resolve accurately."""
    dec_bal = telegram_agent_planner.resolve_intent("balance", "user_1")
    assert dec_bal.intent == "GET_ACCOUNT_RISK"
    assert dec_bal.tool_name == "get_account_risk_overview"

    dec_eq = telegram_agent_planner.resolve_intent("ব্যালেন্স কত", "user_1")
    assert dec_eq.intent == "GET_ACCOUNT_RISK"
    assert dec_eq.tool_name == "get_account_risk_overview"

    dec_cpt = telegram_agent_planner.resolve_intent("concepts", "user_1")
    assert dec_cpt.intent == "GET_CONCEPTS"
    assert dec_cpt.tool_name == "get_concept_intelligence"

    dec_m32 = telegram_agent_planner.resolve_intent("active concepts", "user_1")
    assert dec_m32.intent == "GET_CONCEPTS"


@pytest.mark.asyncio
async def test_tool_gateway_live_ticker_dossier_en_and_bn(superadmin_identity):
    """Verifies that get_live_ticker_dossier produces institutional outputs in English and Bengali."""
    res_en = await telegram_tool_gateway.execute_tool(
        tool_name="get_live_ticker_dossier",
        arguments={"symbol": "BTC/USDT", "language": "en"},
        identity=superadmin_identity,
    )
    assert res_en.success is True
    assert "LIVE DOSSIER" in res_en.output_text
    assert "Live Mark Price" in res_en.output_text
    assert "24h Session Range" in res_en.output_text
    assert "Fair Value Gap Support" in res_en.output_text

    res_bn = await telegram_tool_gateway.execute_tool(
        tool_name="get_live_ticker_dossier",
        arguments={"symbol": "BTC/USDT", "language": "bn"},
        identity=superadmin_identity,
    )
    assert res_bn.success is True
    assert "লাইভ মার্কেট ইন্টেলিজেন্স" in res_bn.output_text
    assert "বর্তমান প্রাইজ" in res_bn.output_text
    assert "২৪ ঘণ্টার রেঞ্জ" in res_bn.output_text


@pytest.mark.asyncio
async def test_tool_gateway_market_overview_en_and_bn(superadmin_identity):
    """Verifies that get_market_overview presents cross-asset metrics in English and Bengali."""
    res_en = await telegram_tool_gateway.execute_tool(
        tool_name="get_market_overview",
        arguments={"language": "en"},
        identity=superadmin_identity,
    )
    assert res_en.success is True
    assert "CROSS-ASSET MARKET INTELLIGENCE" in res_en.output_text
    assert "BTC/USDT" in res_en.output_text
    assert "ETH/USDT" in res_en.output_text

    res_bn = await telegram_tool_gateway.execute_tool(
        tool_name="get_market_overview",
        arguments={"language": "bn"},
        identity=superadmin_identity,
    )
    assert res_bn.success is True
    assert "গ্লোবাল মার্কেট ওভারভিউ" in res_bn.output_text
    assert "BTC/USDT" in res_bn.output_text


@pytest.mark.asyncio
async def test_tool_gateway_account_risk_and_concepts(superadmin_identity):
    """Verifies account risk governance and concept intelligence tools."""
    res_risk = await telegram_tool_gateway.execute_tool(
        tool_name="get_account_risk_overview",
        arguments={},
        identity=superadmin_identity,
    )
    assert res_risk.success is True
    assert "Virtual Equity" in res_risk.output_text
    assert "REAL_CAPITAL_ENABLED = False" in res_risk.output_text

    res_cpt = await telegram_tool_gateway.execute_tool(
        tool_name="get_concept_intelligence",
        arguments={},
        identity=superadmin_identity,
    )
    assert res_cpt.success is True
    assert "CBT / SKY TRADING CONCEPT INTELLIGENCE" in res_cpt.output_text
    assert "M32 VERIFIED" in res_cpt.output_text


@pytest.mark.asyncio
async def test_end_to_end_webhook_natural_language_pipeline():
    """Verifies that TelegramBotDispatcher handles natural language incoming messages without falling into canned fallback."""
    uid = 999002
    rbac_registry.register_user_role(uid, TelegramRole.SUPER_ADMIN)

    # 1. Test "BTC"
    up_btc = {
        "update_id": int(time.time() * 1000) + 1,
        "message": {"text": "BTC", "chat": {"id": uid}, "from": {"id": uid, "username": "test_trader"}},
    }
    res_btc = await telegram_bot.handle_webhook_update(up_btc)
    assert res_btc["status"] == "AI_CONVERSATION_EXECUTED"
    assert "LIVE DOSSIER" in res_btc["response"]
    assert "I am monitoring live telemetry. Our risk desk is enforcing strict Half-Kelly" not in res_btc["response"]

    # 2. Test "btc price"
    up_price = {
        "update_id": int(time.time() * 1000) + 2,
        "message": {"text": "btc price", "chat": {"id": uid}, "from": {"id": uid, "username": "test_trader"}},
    }
    res_price = await telegram_bot.handle_webhook_update(up_price)
    assert res_price["status"] == "AI_CONVERSATION_EXECUTED"
    assert "LIVE DOSSIER" in res_price["response"]
    assert "I am monitoring live telemetry. Our risk desk is enforcing strict Half-Kelly" not in res_price["response"]

    # 3. Test Bengali "বিটকয়েনের দাম কত"
    up_bn = {
        "update_id": int(time.time() * 1000) + 3,
        "message": {"text": "বিটকয়েনের দাম কত", "chat": {"id": uid}, "from": {"id": uid, "username": "test_trader"}},
    }
    res_bn = await telegram_bot.handle_webhook_update(up_bn)
    assert res_bn["status"] == "AI_CONVERSATION_EXECUTED"
    assert "লাইভ মার্কেট ইন্টেলিজেন্স" in res_bn["response"]


@pytest.mark.asyncio
async def test_intent_resolution_swarm_and_collector():
    uid = 999003
    d1 = telegram_agent_planner.resolve_intent("ডেডিকেটেড এজেন্টদের অবস্থা কি?", uid)
    assert d1.tool_name == "get_mastermind_swarm_status"

    d2 = telegram_agent_planner.resolve_intent("কালেক্টর কি ডাটা কালেক্ট করেছে?", uid)
    assert d2.tool_name == "get_autonomous_collector_status"

    d3 = telegram_agent_planner.resolve_intent("অনলাইন ডাটা কালেক্ট করো", uid)
    assert d3.tool_name == "trigger_autonomous_crawl"


@pytest.mark.asyncio
async def test_typed_commands_swarm_collector_crawl():
    from core.telegram.handlers import handle_swarm, handle_collector, handle_crawl
    from core.telegram.rbac import TelegramUserIdentity

    identity = TelegramUserIdentity(user_id=999004, chat_id=999004, role=TelegramRole.SUPER_ADMIN)

    # 1. /swarm
    swarm_res = await handle_swarm("", identity=identity)
    assert "MASTERMIND ARBITER COUNCIL" in swarm_res
    assert "Active Specialists" in swarm_res
    assert "spec_btc_macro" in swarm_res

    # 2. /collector
    collector_res = await handle_collector("", identity=identity)
    assert "AUTONOMOUS ONLINE DATA COLLECTOR" in collector_res
    assert "Active Intelligence Feeds" in collector_res

    # 3. /crawl
    crawl_res = await handle_crawl("", identity=identity)
    assert "AUTONOMOUS CRAWL CYCLE COMPLETE" in crawl_res


