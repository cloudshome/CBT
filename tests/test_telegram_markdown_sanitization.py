"""
Test suite for Telegram Markdown sanitization and entity parse fallback resilience.
Ensures Telegram notification reliability without dropping alerts or crashing on bad entities.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from core.telegram_bot import TelegramBot, sanitize_telegram_markdown


class TestTelegramMarkdownSanitization(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = TelegramBot()
        self.bot.bot_token = "123456:TEST_TOKEN"
        self.bot.chat_id = "5665135791"

    def test_deliberate_markdown_preserved(self):
        text = "🚀 *NEW SIGNAL* on `BTC/USDT`\nCheck [TradingView](https://tradingview.com)"
        sanitized = sanitize_telegram_markdown(text)
        self.assertIn("*NEW SIGNAL*", sanitized)
        self.assertIn("`BTC/USDT`", sanitized)
        self.assertIn("[TradingView](https://tradingview.com)", sanitized)

    def test_embedded_underscores_in_identifiers_escaped(self):
        text = "Specialist spec_opp_btc_usdt triggered with pos_id_99 for symbol BTC_USDT"
        sanitized = sanitize_telegram_markdown(text)
        self.assertIn("spec\\_opp\\_btc\\_usdt", sanitized)
        self.assertIn("pos\\_id\\_99", sanitized)
        self.assertIn("BTC\\_USDT", sanitized)

    def test_standalone_brackets_escaped(self):
        text = "Portfolio Risk Guardian Rejection [CORRELATED_EXPOSURE_CAP_REACHED]: Cluster limit reached."
        sanitized = sanitize_telegram_markdown(text)
        self.assertIn("\\[CORRELATED\\_EXPOSURE\\_CAP\\_REACHED\\]", sanitized)

    def test_unmatched_single_delimiter_escaped(self):
        text = "Trade note: *Unclosed bold text with one star"
        sanitized = sanitize_telegram_markdown(text)
        # The single unmatched asterisk must be escaped so Telegram doesn't fail
        self.assertIn("\\*", sanitized)

    def test_code_blocks_unmodified(self):
        code_block = '```json\n{"symbol": "ETH_USDT", "pos": [1, 2]}\n```'
        sanitized = sanitize_telegram_markdown(code_block)
        # Inside code blocks, underscores and brackets must not be mutated
        self.assertEqual(sanitized, code_block)

    @patch("aiohttp.ClientSession.post")
    async def test_send_single_payload_fallback_on_parse_error(self, mock_post):
        # 1st call fails with 400 Can't parse entities
        # 2nd call (fallback without parse_mode) succeeds with 200
        resp_err = MagicMock()
        resp_err.status = 400
        resp_err.text = AsyncMock(
            return_value='{"ok":false,"error_code":400,"description":"Bad Request: can\'t parse entities: Can\'t find end of the entity starting at byte offset 589"}'
        )

        resp_ok = MagicMock()
        resp_ok.status = 200
        resp_ok.text = AsyncMock(return_value='{"ok":true,"result":{"message_id":123}}')

        # Context manager returns resp_err first, then resp_ok
        cm1 = AsyncMock()
        cm1.__aenter__.return_value = resp_err
        cm2 = AsyncMock()
        cm2.__aenter__.return_value = resp_ok

        mock_post.side_effect = [cm1, cm2]

        result = await self.bot._send_single_payload(
            text="Unparsed *entity test",
            parse_mode="Markdown",
            chat="5665135791",
        )
        self.assertTrue(result)
        self.assertEqual(mock_post.call_count, 2)

        # Verify fallback call popped parse_mode
        fallback_call_kwargs = mock_post.call_args_list[1][1]
        self.assertNotIn("parse_mode", fallback_call_kwargs["json"])
        self.assertEqual(fallback_call_kwargs["json"]["chat_id"], "5665135791")

    @patch("aiohttp.ClientSession.post")
    async def test_send_photo_fallback_on_parse_error(self, mock_post):
        resp_err = MagicMock()
        resp_err.status = 400
        resp_err.text = AsyncMock(
            return_value='{"ok":false,"error_code":400,"description":"Bad Request: can\'t parse entities"}'
        )

        resp_ok = MagicMock()
        resp_ok.status = 200
        resp_ok.text = AsyncMock(return_value='{"ok":true,"result":{"message_id":124}}')

        cm1 = AsyncMock()
        cm1.__aenter__.return_value = resp_err
        cm2 = AsyncMock()
        cm2.__aenter__.return_value = resp_ok

        mock_post.side_effect = [cm1, cm2]

        result = await self.bot.send_photo(
            photo_bytes=b"fake_image_bytes",
            caption="Problematic caption [TEST_ENTITY]",
            chat_id="5665135791",
        )
        self.assertTrue(result)
        self.assertEqual(mock_post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
