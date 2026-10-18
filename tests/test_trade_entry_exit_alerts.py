"""
Test suite for Trade Entry & Exit Telegram Alerts and History Logging.
Verifies date/time formatting, entry/exit reason persistence, and API exposure.
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app import app
from core.portfolio_shadow import portfolio_shadow
from core.telegram.rbac import TelegramRole, TelegramUserIdentity
from core.telegram_bot import telegram_bot


class TestTradeEntryExitAlerts(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        portfolio_shadow.reset_all_positions()

    def tearDown(self):
        portfolio_shadow.reset_all_positions()

    async def test_telegram_entry_alert_formatting(self):
        with patch.object(telegram_bot, "send_message", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            trade_data = {
                "position_id": "POS_BTC_TEST_001",
                "symbol": "BTC/USDT",
                "direction": "LONG",
                "size": 0.5,
                "entry_price": 68500.0,
                "stop_loss": 67200.0,
                "take_profit": 71500.0,
                "opened_at": 1775462400000,
                "entry_reason": "H4 Demand Zone + 15m MSS Displacement",
            }

            sent = await telegram_bot.send_trade_entry_alert(trade_data)
            self.assertTrue(sent)
            mock_send.assert_called_once()
            sent_text = mock_send.call_args[0][0]

            self.assertIn("NEW TRADE ENTERED | BTC/USDT", sent_text)
            self.assertIn("LONG", sent_text)
            self.assertIn("68,500.00", sent_text)
            self.assertIn("67,200.00", sent_text)
            self.assertIn("71,500.00", sent_text)
            self.assertIn("H4 Demand Zone + 15m MSS Displacement", sent_text)
            self.assertIn("Date & Time (তারিখ ও সময়):", sent_text)

            # Verify inline keyboard action buttons attached
            reply_markup = mock_send.call_args[1].get("reply_markup")
            self.assertIsNotNone(reply_markup)
            buttons = reply_markup["inline_keyboard"][0]
            self.assertEqual(buttons[0]["callback_data"], "close:POS_BTC_TEST_001")
            self.assertEqual(buttons[1]["callback_data"], "be:POS_BTC_TEST_001")

    async def test_telegram_exit_alert_formatting(self):
        with patch.object(telegram_bot, "send_message", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True

            trade_data = {
                "position_id": "POS_BTC_TEST_001",
                "symbol": "BTC/USDT",
                "direction": "LONG",
                "entry_price": 68500.0,
                "exit_price": 71500.0,
                "realized_pnl": 1500.0,
                "exit_reason": "TAKE_PROFIT_HIT",
                "entry_reason": "H4 Demand Zone + 15m MSS Displacement",
                "opened_at": 1775462400000,
                "closed_at": 1775470000000,
            }

            sent = await telegram_bot.send_trade_exit_alert(trade_data)
            self.assertTrue(sent)
            mock_send.assert_called_once()
            sent_text = mock_send.call_args[0][0]

            self.assertIn("TRADE CLOSED | BTC/USDT", sent_text)
            self.assertIn("PROFIT", sent_text)
            self.assertIn("+$1,500.00", sent_text)
            self.assertIn("Take-Profit Target Hit", sent_text)
            self.assertIn("H4 Demand Zone + 15m MSS Displacement", sent_text)
            self.assertIn("Entry Time (প্রবেশ সময়):", sent_text)
            self.assertIn("Exit Time (প্রস্থান সময়):", sent_text)

    def test_shadow_position_lifecycle_with_reasons(self):
        with (
            patch.object(telegram_bot, "notify_trade_entry_sync") as mock_entry_notify,
            patch.object(telegram_bot, "notify_trade_exit_sync") as mock_exit_notify,
        ):
            # 1. Open Position
            reason_entry = "Confluence of daily trend and hourly FVG sweep"
            pos_id = portfolio_shadow.open_position(
                symbol="ETH/USDT",
                direction="LONG",
                size=2.0,
                entry_price=3400.0,
                stop_loss=3300.0,
                take_profit=3650.0,
                entry_reason=reason_entry,
            )

            mock_entry_notify.assert_called_once()
            entry_call_arg = mock_entry_notify.call_args[0][0]
            self.assertEqual(entry_call_arg["entry_reason"], reason_entry)
            self.assertEqual(entry_call_arg["position_id"], pos_id)

            # Verify DB stored entry_reason
            open_positions = portfolio_shadow.get_open_positions()
            matching = [p for p in open_positions if p["position_id"] == pos_id]
            self.assertEqual(len(matching), 1)
            self.assertEqual(matching[0]["entry_reason"], reason_entry)
            self.assertIsNone(matching[0]["exit_reason"])

            # 2. Close Position
            reason_exit = "Manual profit secure before CPI news event"
            success = portfolio_shadow.close_position(
                position_id=pos_id,
                exit_price=3550.0,
                exit_reason=reason_exit,
            )
            self.assertTrue(success)

            mock_exit_notify.assert_called_once()
            exit_call_arg = mock_exit_notify.call_args[0][0]
            self.assertEqual(exit_call_arg["exit_reason"], reason_exit)
            self.assertEqual(exit_call_arg["entry_reason"], reason_entry)

            # Verify DB stored exit_reason
            all_positions = portfolio_shadow.get_all_positions()
            closed_matching = [p for p in all_positions if p["position_id"] == pos_id]
            self.assertEqual(len(closed_matching), 1)
            self.assertEqual(closed_matching[0]["status"], "CLOSED")
            self.assertEqual(closed_matching[0]["entry_reason"], reason_entry)
            self.assertEqual(closed_matching[0]["exit_reason"], reason_exit)

    def test_api_desk_overview_contains_formatted_date_time_and_reasons(self):
        client = TestClient(app)

        # Open a position with custom reason
        pos_id = portfolio_shadow.open_position(
            symbol="SOL/USDT",
            direction="LONG",
            size=10.0,
            entry_price=150.0,
            stop_loss=140.0,
            take_profit=180.0,
            entry_reason="Key Support bounce + Bullish Divergence",
        )

        res = client.get("/api/paper/desk-overview")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Check current positions
        current_pos = [p for p in data["current"] if p["id"] == pos_id]
        self.assertEqual(len(current_pos), 1)
        self.assertIn("openedAtFormatted", current_pos[0])
        self.assertTrue(current_pos[0]["openedAtFormatted"].endswith("UTC"))
        self.assertEqual(current_pos[0]["entryReason"], "Key Support bounce + Bullish Divergence")

        # Close position
        portfolio_shadow.close_position(
            position_id=pos_id,
            exit_price=175.0,
            exit_reason="TP2 TARGET REACHED",
        )

        res_after = client.get("/api/paper/desk-overview")
        self.assertEqual(res_after.status_code, 200)
        data_after = res_after.json()

        # Check past positions
        past_pos = [p for p in data_after["past"] if p["id"] == pos_id]
        self.assertEqual(len(past_pos), 1)
        self.assertIn("openedAtFormatted", past_pos[0])
        self.assertIn("closedAtFormatted", past_pos[0])
        self.assertEqual(past_pos[0]["entryReason"], "Key Support bounce + Bullish Divergence")
        self.assertEqual(past_pos[0]["exitReason"], "TP2 TARGET REACHED")

    def test_telegram_close_by_position_id_and_symbol(self):
        # 1. Open two positions
        pos1 = portfolio_shadow.open_position(
            symbol="BTC/USDT",
            direction="LONG",
            size=0.1,
            entry_price=65000.0,
            stop_loss=64000.0,
            take_profit=68000.0,
            entry_reason="Breakout test 1",
        )
        pos2 = portfolio_shadow.open_position(
            symbol="ETH/USDT",
            direction="SHORT",
            size=1.0,
            entry_price=3500.0,
            stop_loss=3600.0,
            take_profit=3200.0,
            entry_reason="Breakout test 2",
        )

        # 2. Close by exact Position ID
        res_id = telegram_bot.state_mind.close_position_by_symbol(pos1)
        self.assertIn("POSITION CLOSED FROM TELEGRAM", res_id)
        self.assertIn(pos1, res_id)
        self.assertIn("TELEGRAM_MANUAL_CLOSE", res_id)

        # Verify only pos2 remains open
        remaining = portfolio_shadow.get_open_positions()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["position_id"], pos2)

        # 3. Close by Symbol "ETH"
        res_sym = telegram_bot.state_mind.close_position_by_symbol("ETH")
        self.assertIn("POSITION CLOSED FROM TELEGRAM", res_sym)
        self.assertIn("ETH/USDT", res_sym)
        self.assertIn(pos2, res_sym)

        # Verify all positions closed
        self.assertEqual(len(portfolio_shadow.get_open_positions()), 0)

        # 4. Attempt close when no positions are open
        res_empty = telegram_bot.state_mind.close_position_by_symbol()
        self.assertIn("No active open paper positions", res_empty)

    async def test_telegram_one_click_close_and_breakeven_callbacks(self):
        # Setup open position
        pos_id = portfolio_shadow.open_position(
            symbol="SOL/USDT",
            direction="LONG",
            size=5.0,
            entry_price=160.0,
            stop_loss=150.0,
            take_profit=190.0,
            entry_reason="1-Click Callback Test",
        )

        identity = TelegramUserIdentity(
            user_id=12345,
            chat_id=67890,
            role=TelegramRole.TRADER,
        )

        with (
            patch.object(telegram_bot, "send_message", new_callable=AsyncMock) as mock_send,
            patch.object(telegram_bot, "answer_callback_query", new_callable=AsyncMock) as mock_ans,
            patch("core.telegram.rbac.rbac_registry.is_authorized", return_value=(True, identity)),
        ):
            mock_send.return_value = True
            mock_ans.return_value = True

            # 1. Test "be:<pos_id>" 1-click Breakeven callback
            cb_be = {
                "id": "cb_001",
                "from": {"id": 12345},
                "message": {"chat": {"id": 67890}},
                "data": f"be:{pos_id}",
            }
            res_be = await telegram_bot.handle_callback_query(cb_be)
            self.assertEqual(res_be["status"], "BREAKEVEN_APPLIED")
            self.assertEqual(res_be["position_id"], pos_id)
            mock_ans.assert_called_with("cb_001", "SL moved to breakeven.")

            # Check that stop loss was updated to entry price (160.0)
            open_pos = [
                p for p in portfolio_shadow.get_open_positions() if p["position_id"] == pos_id
            ]
            self.assertEqual(len(open_pos), 1)
            self.assertEqual(open_pos[0]["stop_loss"], 160.0)

            # 2. Test "close:<pos_id>" 1-click Close callback
            cb_close = {
                "id": "cb_002",
                "from": {"id": 12345},
                "message": {"chat": {"id": 67890}},
                "data": f"close:{pos_id}",
            }
            res_close = await telegram_bot.handle_callback_query(cb_close)
            self.assertEqual(res_close["status"], "POSITION_CLOSED")
            self.assertEqual(res_close["position_id"], pos_id)
            mock_ans.assert_called_with("cb_002", "Trade closed.")

            # Verify position is closed
            remaining = [
                p for p in portfolio_shadow.get_open_positions() if p["position_id"] == pos_id
            ]
            self.assertEqual(len(remaining), 0)
