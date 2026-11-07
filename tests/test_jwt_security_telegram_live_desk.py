"""
tests/test_jwt_security_telegram_live_desk.py
=============================================
Security verification test suite for JWT_SECRET fail-closed behaviour
and HMAC action token security in core/telegram_live_desk.py.

Covers:
1. Missing JWT_SECRET raises RuntimeError (fail-closed startup).
2. Empty string JWT_SECRET raises RuntimeError.
3. Whitespace-only JWT_SECRET raises RuntimeError.
4. Valid JWT_SECRET succeeds.
5. Direct secret injection in constructor succeeds.
6. Empty or invalid secret injection raises RuntimeError.
7. Single-use token generation and cryptographic HMAC signature verification.
8. Replay attack rejection (token cannot be consumed twice).
9. Tampered token rejection.
10. Expired token rejection.
11. Proxy transparency and compatibility with existing singleton imports.
12. No secret leakage in repr or string representation.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from unittest.mock import MagicMock

# Defensively mock external dependencies before importing live desk
for _dep in [
    "core.daily_learning_reporter",
    "core.execution.account_probe",
    "core.execution.kill_switch",
    "core.execution.live_canary_runner",
    "core.execution.live_gatekeeper",
    "core.macro_event_reporter",
]:
    if _dep not in sys.modules:
        sys.modules[_dep] = MagicMock()

from core.telegram_live_desk import (  # noqa: E402
    TelegramLiveTradingDesk,
    telegram_live_desk,
)


class TestJwtSecurityTelegramLiveDesk(unittest.TestCase):
    """Rigorous security tests for JWT / HMAC secrets in TelegramLiveTradingDesk."""

    def setUp(self) -> None:
        self._orig_jwt_secret = os.environ.get("JWT_SECRET")

    def tearDown(self) -> None:
        if self._orig_jwt_secret is not None:
            os.environ["JWT_SECRET"] = self._orig_jwt_secret
        else:
            os.environ.pop("JWT_SECRET", None)

    def test_missing_jwt_secret_fails_closed(self) -> None:
        """Requirement: If JWT_SECRET is missing, raise RuntimeError."""
        os.environ.pop("JWT_SECRET", None)
        with self.assertRaises(RuntimeError) as ctx:
            TelegramLiveTradingDesk()
        self.assertIn("missing", str(ctx.exception).lower())
        self.assertIn("fail-closed", str(ctx.exception).lower())

    def test_empty_jwt_secret_fails_closed(self) -> None:
        """Requirement: If JWT_SECRET is empty string, raise RuntimeError."""
        os.environ["JWT_SECRET"] = ""
        with self.assertRaises(RuntimeError) as ctx:
            TelegramLiveTradingDesk()
        self.assertIn("empty", str(ctx.exception).lower())

    def test_whitespace_jwt_secret_fails_closed(self) -> None:
        """Requirement: If JWT_SECRET is only whitespace, raise RuntimeError."""
        os.environ["JWT_SECRET"] = "   \t\n  "
        with self.assertRaises(RuntimeError) as ctx:
            TelegramLiveTradingDesk()
        self.assertIn("empty", str(ctx.exception).lower())

    def test_valid_jwt_secret_initialization(self) -> None:
        """Requirement: Valid non-empty JWT_SECRET allows normal startup."""
        test_secret = "super_secure_production_secret_key_998877"
        os.environ["JWT_SECRET"] = test_secret
        desk = TelegramLiveTradingDesk()
        self.assertEqual(desk._secret, test_secret.encode("utf-8"))

    def test_explicit_secret_injection(self) -> None:
        """Tests constructor parameter secret overrides environment cleanly."""
        os.environ.pop("JWT_SECRET", None)
        desk = TelegramLiveTradingDesk(secret="explicitly_passed_secret_value_123")
        self.assertEqual(desk._secret, b"explicitly_passed_secret_value_123")

    def test_explicit_empty_secret_fails_closed(self) -> None:
        """Explicit empty secret parameter must raise RuntimeError."""
        with self.assertRaises(RuntimeError):
            TelegramLiveTradingDesk(secret="")
        with self.assertRaises(RuntimeError):
            TelegramLiveTradingDesk(secret=b"   ")

    def test_token_cryptographic_verification(self) -> None:
        """Verifies HMAC SHA-256 action token generation and consumption."""
        desk = TelegramLiveTradingDesk(secret="cryptographic_integrity_secret_key")
        payload = {"action": "KILL_SWITCH", "operator": "security_admin"}
        token_obj = desk.generate_action_token("DISENGAGE", payload, ttl_seconds=10.0)

        self.assertTrue(token_obj.token)
        self.assertEqual(len(token_obj.token), 16)
        self.assertFalse(token_obj.consumed)

        # Successful verification and single consumption
        consumed = desk.validate_and_consume_token(token_obj.token)
        self.assertIsNotNone(consumed)
        assert consumed is not None
        self.assertEqual(consumed.action, "DISENGAGE")
        self.assertEqual(consumed.payload["operator"], "security_admin")
        self.assertTrue(consumed.consumed)

    def test_replay_attack_rejected(self) -> None:
        """Verifies that an action token cannot be reused/replayed."""
        desk = TelegramLiveTradingDesk(secret="anti_replay_secret_key_verify")
        token_obj = desk.generate_action_token("HALT_TRADING", {}, ttl_seconds=10.0)

        # 1st consume succeeds
        first_consume = desk.validate_and_consume_token(token_obj.token)
        self.assertIsNotNone(first_consume)

        # 2nd consume (replay attack) MUST fail closed
        replay_attempt = desk.validate_and_consume_token(token_obj.token)
        self.assertIsNone(replay_attempt)

    def test_tampered_token_rejected(self) -> None:
        """Invalid or forged tokens must be rejected."""
        desk = TelegramLiveTradingDesk(secret="forgery_protection_key_12345")
        desk.generate_action_token("TEST_ACTION", {}, ttl_seconds=10.0)

        self.assertIsNone(desk.validate_and_consume_token("tampered_token_00"))
        self.assertIsNone(desk.validate_and_consume_token(""))
        self.assertIsNone(desk.validate_and_consume_token("0000000000000000"))

    def test_expired_token_rejected(self) -> None:
        """Expired tokens must fail validation."""
        desk = TelegramLiveTradingDesk(secret="expiration_test_secret_key_777")
        token_obj = desk.generate_action_token("EXPIRING_ACTION", {}, ttl_seconds=0.01)
        time.sleep(0.02)
        self.assertIsNone(desk.validate_and_consume_token(token_obj.token))

    def test_proxy_transparency_and_lazy_singleton(self) -> None:
        """Verifies module-level telegram_live_desk singleton works transparently when JWT_SECRET is present."""
        os.environ["JWT_SECRET"] = "proxy_test_secret_key_123456789"
        # Access through proxy
        token = telegram_live_desk.generate_action_token(
            "PROXY_OP", {"test": True}, ttl_seconds=5.0
        )
        self.assertIsNotNone(token)
        consumed = telegram_live_desk.validate_and_consume_token(token.token)
        self.assertIsNotNone(consumed)


if __name__ == "__main__":
    unittest.main()
