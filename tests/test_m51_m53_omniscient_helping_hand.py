"""
Comprehensive Verification Test Suite for Milestones M51, M52, and M53
========================================================================
M51: Sub-Second Telegram Responsiveness, Event-Loop Decoupling & Markdown Sanitizer
M52: Master Terminal & Native Desk Bridge Wiring Fixes (Zero Mock, Real Microstructure)
M53: The Omniscient 28-Setup Quantitative Trading Helping Hand & Interactive Advisor
"""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from core.market_providers import HttpSessionManager
from core.native_desk_bridge import native_desk_bridge
from core.omniscient_setup_encyclopedia import omniscient_setup_engine
from core.telegram.agent_planner import telegram_agent_planner
from core.telegram.rbac import TelegramRole, TelegramUserIdentity
from core.telegram.tool_gateway import telegram_tool_gateway
from core.telegram_bot import sanitize_telegram_markdown


class TestMilestone51TelegramAndEventLoop(unittest.IsolatedAsyncioTestCase):
    """M51 Verification: Sub-second Telegram responsiveness, event loop decoupling, and Markdown sanitizer."""

    def test_markdown_sanitizer_converts_headers_bullets_and_double_asterisks(self):
        """Verifies that **, ###, and * bullets are normalized for Telegram Markdown v1 without raw leakage."""
        raw_input = (
            "### Quantitative Desk Report\n"
            "* **BTC/USDT:** **$81,750.00** (`+2.45%`)\n"
            "* **ETH/USDT:** **$2,425.00**\n"
            "Here is a [Chart Link](https://tradingview.com/chart) and `pos_id_123`.\n"
            "Specialist spec_opp_btc_usdt active with risk [MAX_EXPOSURE_REACHED]."
        )

        sanitized = sanitize_telegram_markdown(raw_input)

        # 1. No raw ### or ** must remain
        self.assertNotIn("###", sanitized)
        self.assertNotIn("**", sanitized)

        # 2. Converted headers to *Quantitative Desk Report*
        self.assertIn("*Quantitative Desk Report*", sanitized)

        # 3. Converted list asterisks to bullets with single-asterisk bold
        self.assertIn("• *BTC/USDT:* *$81,750.00*", sanitized)
        self.assertIn("• *ETH/USDT:* *$2,425.00*", sanitized)

        # 4. Valid links and code preserved
        self.assertIn("[Chart Link](https://tradingview.com/chart)", sanitized)
        self.assertIn("`pos_id_123`", sanitized)

        # 5. Word-internal underscores and standalone brackets escaped
        self.assertIn("spec\\_opp\\_btc\\_usdt", sanitized)
        self.assertIn("\\[MAX\\_EXPOSURE\\_REACHED\\]", sanitized)

    def test_line_level_delimiter_balancing_prevents_cascading_escape(self):
        """One unmatched asterisk on line 2 must not escape or corrupt valid bold on lines 1 & 3."""
        multi_line = (
            "Line 1: *Valid Bold Text*\n"
            "Line 2: Single rogue * asterisk on this line\n"
            "Line 3: *Another Valid Bold Text*"
        )
        sanitized = sanitize_telegram_markdown(multi_line)
        lines = sanitized.split("\n")

        # Line 1 preserved
        self.assertIn("*Valid Bold Text*", lines[0])
        # Line 2 rogue asterisk escaped
        self.assertIn("\\*", lines[1])
        # Line 3 preserved
        self.assertIn("*Another Valid Bold Text*", lines[2])

    async def test_http_session_manager_handles_multiple_event_loops_safely(self):
        """Verifies that HttpSessionManager keys ClientSession per event loop, preventing cross-loop RuntimeError."""
        # 1. Main loop session
        session_main = await HttpSessionManager.get_session()
        self.assertIsNotNone(session_main)
        self.assertFalse(session_main.closed)

        # 2. Worker thread with isolated loop
        async def _run_in_new_loop():
            sub_session = await HttpSessionManager.get_session()
            self.assertIsNotNone(sub_session)
            self.assertFalse(sub_session.closed)
            # Must be a distinct session instance because loop id differs
            self.assertNotEqual(id(session_main), id(sub_session))
            await HttpSessionManager.close_session()
            self.assertTrue(sub_session.closed)

        await asyncio.to_thread(asyncio.run, _run_in_new_loop())

        # Main session remains open and healthy
        self.assertFalse(session_main.closed)

    async def test_fast_greeting_intent_completes_in_sub_half_second(self):
        """Verifies greetings ('hi', 'hello', 'সালাম') return instant telemetry snapshot in < 500ms without deep RAG hangs."""
        ident = TelegramUserIdentity(user_id="test_user", role=TelegramRole.TRADER, chat_id="12345")

        # Mock ticker gateway with fast in-memory response
        with patch(
            "core.market_providers.market_gateway.get_ticker", new_callable=AsyncMock
        ) as mock_tick:
            mock_tick.return_value = {"price": 81750.0, "change_24h_pct": 2.45}

            t0 = time.perf_counter()
            resp_en = await telegram_agent_planner.handle_user_message("hi", ident)
            elapsed_en = time.perf_counter() - t0

            # Must finish in < 500ms
            self.assertLess(elapsed_en, 0.50, f"Greeting took {elapsed_en:.3f}s (target < 0.50s)")
            self.assertIn("CBT Quant Desk Copilot", resp_en)
            self.assertIn("BTC/USDT", resp_en)

            # Test Bengali greeting
            t0 = time.perf_counter()
            resp_bn = await telegram_agent_planner.handle_user_message("সালাম ভাই", ident)
            elapsed_bn = time.perf_counter() - t0
            self.assertLess(elapsed_bn, 0.50, f"Bengali greeting took {elapsed_bn:.3f}s")
            self.assertIn("সিবিটি কোয়ান্ট ডেস্ক", resp_bn)

    async def test_quant_mentor_awaits_natively_without_threadpool_deadlock(self):
        """Verifies quant_mentor.generate_response awaits compile_asset_dossier natively without ThreadPoolExecutor hangs."""
        from core.quant_mentor import quant_mentor

        with patch(
            "core.native_desk_bridge.native_desk_bridge.compile_asset_dossier",
            new_callable=AsyncMock,
        ) as mock_dossier:
            mock_dossier.return_value = MagicMock(
                current_price=82000.0,
                market_bias="BULLISH",
                confluence_score=85.0,
                fvg_zone="$81,200 – $81,500",
                ob_zone="$80,900",
                pdh=82500.0,
                pdl=80500.0,
                primary_setup=MagicMock(stop_loss=80500.0, net_ev_r=0.45),
            )

            resp = await quant_mentor.generate_response(
                user_message="BTC",
                market_telemetry={"symbol": "BTC/USDT"},
                language_preference="en",
            )
            self.assertIn("BTC/USDT", resp)
            self.assertTrue(mock_dossier.awaited)


class TestMilestone52MasterTerminalAndNativeDeskBridge(unittest.IsolatedAsyncioTestCase):
    """M52 Verification: Eliminating silent AttributeErrors and mock math in native desk bridge and terminal routes."""

    async def test_native_desk_bridge_cvd_call_and_microstructure_telemetry(self):
        """Verifies that native_desk_bridge calls cvd_absorption_engine.analyze_orderflow correctly without TypeError."""
        candles = [
            {
                "timestamp": 1700000000 + i * 900,
                "open": 80000 + i * 10,
                "high": 80020 + i * 10,
                "low": 79990 + i * 10,
                "close": 80015 + i * 10,
                "volume": 100.0,
            }
            for i in range(40)
        ]

        with patch("core.data_streamer.data_streamer.get_candles", return_value=candles):
            dossier = await native_desk_bridge.compile_asset_dossier("BTC/USDT", "15m")

            # 1. Macro vitals must be populated without AttributeError
            self.assertIn("dxy", dossier.macro_vitals)
            self.assertIn("us10y", dossier.macro_vitals)
            self.assertIn("macro_regime", dossier.macro_vitals)
            self.assertIsNotNone(dossier.macro_vitals["dxy"])

            # 2. Microstructure state must have real orderflow / CVD state (not silent fallback failure)
            micro = dossier.microstructure_state
            self.assertIn("cvd_absorption", micro)
            self.assertIn("orderbook_imbalance", micro)
            self.assertIn("funding_rate", micro)
            self.assertIn(
                micro["cvd_absorption"], ("BULLISH_ABSORPTION", "BEARISH_ABSORPTION", "NEUTRAL")
            )

    async def test_terminal_routes_smc_pattern_scan_and_dynamic_mitigation(self):
        """Verifies GET /api/terminal/telemetry calls smc_engine.scan() and returns real, non-fabricated metrics."""
        from core.terminal_routes import get_master_terminal_telemetry

        # Mock candles to pass through scan
        candles = [
            {
                "timestamp": 1700000000 + i * 900,
                "open": 80000 + i * 5,
                "high": 80030 + i * 5,
                "low": 79980 + i * 5,
                "close": 80020 + i * 5,
                "volume": 150.0,
            }
            for i in range(50)
        ]

        with (
            patch("core.data_streamer.data_streamer.get_candles", return_value=candles),
            patch(
                "core.market_providers.market_gateway.get_ticker", new_callable=AsyncMock
            ) as mock_tick,
        ):
            mock_tick.return_value = {"price": 80500.0, "change_24h_pct": 1.85}

            res = await get_master_terminal_telemetry(symbol="BTCUSDT", timeframe="15m")

            # 1. Must return structured telemetry
            self.assertIn("market", res)
            self.assertIn("orderFlow", res)
            self.assertIn("confluence", res)
            self.assertIn("styleSignals", res)
            self.assertIn("mtfMatrix", res["market"])
            self.assertIn("smcStructures", res["market"])

            # 2. Real MTF Heatmap metrics
            mtf = res["market"]["mtfMatrix"]
            self.assertEqual(len(mtf), 9)
            for m in mtf:
                self.assertIn("timeframe", m)
                self.assertIn("rsi", m)
                self.assertIn("vwapSigma", m)
                self.assertIn("score", m)

            # 3. Derivatives vitals
            dv = res["orderFlow"]["derivativesVitals"]
            self.assertIn("openInterestUsd", dv)
            self.assertIn("l2DepthImbalancePct", dv)
            self.assertIn("bidsPercentage", dv)
            self.assertIn("asksPercentage", dv)


class TestMilestone53OmniscientHelpingHand(unittest.IsolatedAsyncioTestCase):
    """M53 Verification: The Omniscient 28-Setup Quantitative Trading Helping Hand."""

    def test_canonical_28_setups_registry_integrity(self):
        """Verifies all 28 setups are registered across all 6 families with bilingual metadata."""
        catalog = omniscient_setup_engine.catalog
        self.assertEqual(len(catalog), 28, f"Expected exactly 28 setups, found {len(catalog)}")

        families_found = set(s.family for s in catalog)
        self.assertEqual(len(families_found), 6, "Must encompass all 6 Setup Families")

        # Verify key individual setups exist
        s1 = omniscient_setup_engine.get_setup(1)
        self.assertEqual(s1.setup_id, "ICT_SILVER_BULLET_SWEEP_MSS_FVG")
        self.assertIn("Silver Bullet", s1.name_en)

        s9 = omniscient_setup_engine.get_setup(9)
        self.assertEqual(s9.setup_id, "CVD_ABSORPTION_DIVERGENCE")

        s18 = omniscient_setup_engine.get_setup(18)
        self.assertEqual(s18.setup_id, "WYCKOFF_SPRING_UTAD")

        s22 = omniscient_setup_engine.get_setup(22)
        self.assertEqual(s22.setup_id, "STRUCTURAL_CANDLESTICK_TRIGGER")

        s25 = omniscient_setup_engine.get_setup(25)
        self.assertEqual(s25.setup_id, "CROSS_ASSET_SMT_DIVERGENCE")

        s26 = omniscient_setup_engine.get_setup(26)
        self.assertEqual(s26.setup_id, "DEVILS_ADVOCATE_NO_TRADE_FILTER")

        s27 = omniscient_setup_engine.get_setup(27)
        self.assertEqual(s27.setup_id, "OPTIMAL_DCA_LIMIT_LADDER")

        s28 = omniscient_setup_engine.get_setup(28)
        self.assertEqual(s28.setup_id, "OPEN_POSITION_RATCHET_COPILOT")

    async def test_omniscient_scanner_evaluates_real_candles_and_smt(self):
        """Verifies that omniscient_setup_engine.scan() evaluates closed candles, SMT divergence, and returns helping hand dossier."""
        # Synthesize BTC candles (sweeping a low)
        btc_candles = [
            {
                "timestamp": 1700000000 + i * 900,
                "open": 81000 - i * 15,
                "high": 81020 - i * 15,
                "low": 80970 - i * 15,
                "close": 80980 - i * 15,
                "volume": 200.0,
            }
            for i in range(35)
        ]
        # Last candle sweeps lower
        btc_candles.append(
            {
                "timestamp": 1700031500,
                "open": 80450,
                "high": 80480,
                "low": 80320,
                "close": 80460,
                "volume": 500.0,
            }
        )

        # Synthesize ETH candles (holding a higher low -> Bullish SMT Divergence)
        eth_candles = [
            {
                "timestamp": 1700000000 + i * 900,
                "open": 2400 + i * 2,
                "high": 2410 + i * 2,
                "low": 2395 + i * 2,
                "close": 2405 + i * 2,
                "volume": 80.0,
            }
            for i in range(35)
        ]
        eth_candles.append(
            {
                "timestamp": 1700031500,
                "open": 2470,
                "high": 2485,
                "low": 2465,
                "close": 2480,
                "volume": 120.0,
            }
        )

        dossier = await omniscient_setup_engine.scan(
            symbol="BTC/USDT",
            timeframe="15m",
            candles=btc_candles,
            correlated_candles=eth_candles,
        )

        self.assertEqual(dossier.symbol, "BTC/USDT")
        self.assertGreater(dossier.current_price, 0)
        self.assertIn(dossier.optimal_action, ("EXECUTE_NOW", "SET_LIMIT_LADDER", "STAY_IN_CASH"))
        self.assertIsNotNone(dossier.best_setup)
        self.assertTrue(len(dossier.limit_ladder) > 0)
        self.assertIn("SMT", dossier.smt_divergence_summary)

    async def test_telegram_setups_command_and_planner_intent(self):
        """Verifies /setups command and natural language intent ('কোন সেটআপ আছে', 'what setups are active') invoke scan_omniscient_setups."""
        ident = TelegramUserIdentity(user_id="trader_1", role=TelegramRole.TRADER, chat_id="99999")

        # 1. Natural language intent resolution
        decision_en = telegram_agent_planner.resolve_intent(
            "what setups are active on btc?", ident.user_id
        )
        self.assertEqual(decision_en.tool_name, "scan_omniscient_setups")
        self.assertEqual(decision_en.tool_args.get("symbol"), "BTC/USDT")

        decision_bn = telegram_agent_planner.resolve_intent("কোন সেটআপ আছে এখন?", ident.user_id)
        self.assertEqual(decision_bn.tool_name, "scan_omniscient_setups")

        # 2. Tool gateway execution
        result = await telegram_tool_gateway.execute_tool(
            tool_name="scan_omniscient_setups",
            arguments={"symbol": "BTC/USDT", "timeframe": "15m"},
            identity=ident,
        )
        self.assertTrue(result.success)
        self.assertIn("CBT Trading Helping Hand", result.output_text)
        self.assertIn("RECOMMENDED ACTION:", result.output_text)
        self.assertIn("OPTIMAL 3-TRANCHE", result.output_text)

    def test_trading_dictionary_seeds_canonical_setup_terms(self):
        """Verifies trading dictionary seeds foundational setup terms with bilingual definitions."""
        from core.knowledge_os.trading_dictionary import trading_dictionary

        for term_id in (
            "smt_divergence",
            "wyckoff_spring",
            "silver_bullet",
            "ote",
            "mitigation_block",
            "volume_profile_vpoc",
            "bollinger_keltner_squeeze",
            "oi_price_triad",
        ):
            term = trading_dictionary.get_term(term_id)
            self.assertIsNotNone(term, f"Dictionary term '{term_id}' must be seeded")
            self.assertTrue(len(term.definition_en) > 20)
            self.assertTrue(len(term.definition_bn) > 20)


if __name__ == "__main__":
    unittest.main()
