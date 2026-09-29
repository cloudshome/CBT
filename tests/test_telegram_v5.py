"""
Comprehensive Verification Suite for Telegram V5 Subsystem.
Tests all constitutional invariants and functional requirements:
1. Hierarchical Role-Based Access Control (RBAC) & Dynamic /help filtering
2. SQLite-backed update idempotency & replay protection
3. HMAC-signed expiring action tokens & tamper rejection
4. Two-Phase interactive confirmation and atomic shadow execution
5. Emergency Kill-Switch (/pause and /resume) & risk primacy
6. Pure-Python candlestick PNG chart rasterization
7. Walk-Forward candidate validation (/test <id>) with 3-tier frictions
8. Immutable structured audit logging
"""

import time

import pytest

from core.database import db_manager
from core.event_shock_engine import event_shock_engine
from core.portfolio_shadow import portfolio_shadow
from core.telegram.audit import telegram_audit
from core.telegram.callbacks import callback_router
from core.telegram.charts import telegram_charts
from core.telegram.commands import command_registry
from core.telegram.idempotency import idempotency_manager
from core.telegram.rbac import TelegramRole, TelegramUserIdentity, rbac_registry
from core.telegram_bot import telegram_bot


@pytest.fixture(autouse=True)
def clean_rbac_registry():
    rbac_registry.reset()
    yield
    rbac_registry.reset()


# ==============================================================================
# 1. RBAC & PERMISSION HIERARCHY TESTS
# ==============================================================================


def test_rbac_role_hierarchy():
    """Verifies that higher roles strictly encompass lower permissions."""
    assert TelegramRole.UNAUTHORIZED.privilege_level == 0
    assert TelegramRole.ANALYST.privilege_level == 10
    assert TelegramRole.TRADER.privilege_level == 20
    assert TelegramRole.RISK_ADMIN.privilege_level == 30
    assert TelegramRole.SUPER_ADMIN.privilege_level == 40

    # Trader can access Trader & Analyst, but not Risk Admin
    assert TelegramRole.TRADER.can_access(TelegramRole.ANALYST) is True
    assert TelegramRole.TRADER.can_access(TelegramRole.TRADER) is True
    assert TelegramRole.TRADER.can_access(TelegramRole.RISK_ADMIN) is False
    assert TelegramRole.TRADER.can_access(TelegramRole.SUPER_ADMIN) is False

    # Super Admin can access everything
    assert TelegramRole.SUPER_ADMIN.can_access(TelegramRole.TRADER) is True
    assert TelegramRole.SUPER_ADMIN.can_access(TelegramRole.RISK_ADMIN) is True


def test_rbac_user_resolution_and_overrides(monkeypatch):
    """Verifies environment mapping of users to specific roles."""
    monkeypatch.setenv("TELEGRAM_SUPER_ADMIN_IDS", "99999")
    monkeypatch.setenv("TELEGRAM_RISK_ADMIN_IDS", "88888")
    monkeypatch.setenv("TELEGRAM_TRADER_IDS", "77777")
    monkeypatch.setenv("TELEGRAM_ANALYST_IDS", "66666")

    # Re-initialize registry with env
    reg = type(rbac_registry)()

    assert reg.resolve_user(99999).role == TelegramRole.SUPER_ADMIN
    assert reg.resolve_user(88888).role == TelegramRole.RISK_ADMIN
    assert reg.resolve_user(77777).role == TelegramRole.TRADER
    assert reg.resolve_user(66666).role == TelegramRole.ANALYST
    assert reg.resolve_user(11111).role == TelegramRole.UNAUTHORIZED


@pytest.mark.asyncio
async def test_rbac_command_authorization_enforcement():
    """Verifies typed command enforcement rejects lower roles and accepts authorized roles."""
    # Configure custom test identities
    analyst_user = 60001
    trader_user = 70001
    risk_user = 80001
    super_user = 90001

    rbac_registry.register_user_role(analyst_user, TelegramRole.ANALYST)
    rbac_registry.register_user_role(trader_user, TelegramRole.TRADER)
    rbac_registry.register_user_role(risk_user, TelegramRole.RISK_ADMIN)
    rbac_registry.register_user_role(super_user, TelegramRole.SUPER_ADMIN)

    # 1. Analyst attempting TRADER command (/close) -> REJECTED
    up_analyst_close = {
        "update_id": int(time.time() * 1000) + 1,
        "message": {"text": "/close BTC", "chat": {"id": 123}, "from": {"id": analyst_user}},
    }
    res_denied = await telegram_bot.handle_webhook_update(up_analyst_close)
    assert res_denied["status"] == "AUTH_DENIED"
    assert res_denied["command"] == "/close"

    # 2. Trader running TRADER command (/positions) -> EXECUTED
    up_trader = {
        "update_id": int(time.time() * 1000) + 2,
        "message": {"text": "/positions", "chat": {"id": 123}, "from": {"id": trader_user}},
    }
    res_trader = await telegram_bot.handle_webhook_update(up_trader)
    assert res_trader["status"] == "EXECUTED"

    # 3. Trader attempting RISK_ADMIN command (/pause) -> REJECTED
    up_trader_pause = {
        "update_id": int(time.time() * 1000) + 3,
        "message": {"text": "/pause", "chat": {"id": 123}, "from": {"id": trader_user}},
    }
    res_pause_denied = await telegram_bot.handle_webhook_update(up_trader_pause)
    assert res_pause_denied["status"] == "AUTH_DENIED"

    # 4. Risk Admin running /pause -> EXECUTED
    up_risk_pause = {
        "update_id": int(time.time() * 1000) + 4,
        "message": {"text": "/pause", "chat": {"id": 123}, "from": {"id": risk_user}},
    }
    res_pause = await telegram_bot.handle_webhook_update(up_risk_pause)
    assert res_pause["status"] == "EXECUTED"
    assert "EMERGENCY TRADING HALT ENGAGED" in res_pause["response"]

    # 5. Risk Admin attempting SUPER_ADMIN command (/resume) -> REJECTED
    up_risk_resume = {
        "update_id": int(time.time() * 1000) + 5,
        "message": {"text": "/resume", "chat": {"id": 123}, "from": {"id": risk_user}},
    }
    res_resume_denied = await telegram_bot.handle_webhook_update(up_risk_resume)
    assert res_resume_denied["status"] == "AUTH_DENIED"

    # 6. Super Admin running /resume -> EXECUTED
    up_super_resume = {
        "update_id": int(time.time() * 1000) + 6,
        "message": {"text": "/resume", "chat": {"id": 123}, "from": {"id": super_user}},
    }
    res_resume = await telegram_bot.handle_webhook_update(up_super_resume)
    assert res_resume["status"] == "EXECUTED"
    assert "EMERGENCY TRADING HALT RELEASED" in res_resume["response"]


def test_dynamic_role_filtered_help():
    """Verifies that /help dynamically conceals privileged commands from lower roles."""
    analyst_identity = TelegramUserIdentity(user_id="1", chat_id="1", role=TelegramRole.ANALYST)
    trader_identity = TelegramUserIdentity(user_id="2", chat_id="2", role=TelegramRole.TRADER)
    super_identity = TelegramUserIdentity(user_id="3", chat_id="3", role=TelegramRole.SUPER_ADMIN)

    analyst_help = command_registry.generate_help_menu(analyst_identity)
    trader_help = command_registry.generate_help_menu(trader_identity)
    super_help = command_registry.generate_help_menu(super_identity)

    # Analyst must NOT see /pause or /signal
    assert "/pause" not in analyst_help
    assert "/signal" not in analyst_help
    assert "/market" in analyst_help

    # Trader sees /signal and /positions, but NOT /pause or /resume
    assert "/signal" in trader_help
    assert "/positions" in trader_help
    assert "/pause" not in trader_help
    assert "/resume" not in trader_help

    # Super Admin sees all commands
    assert "/signal" in super_help
    assert "/pause" in super_help
    assert "/resume" in super_help


# ==============================================================================
# 2. IDEMPOTENCY & REPLAY PROTECTION TESTS
# ==============================================================================


def test_idempotency_manager_atomic_locking():
    """Verifies that duplicate updates are blocked atomically."""
    test_key = f"telegram:12345:67890:{int(time.time())}:status"

    # First acquisition succeeds
    assert idempotency_manager.check_and_acquire(test_key) is True

    # Immediate second acquisition fails (locked / in-flight)
    assert idempotency_manager.check_and_acquire(test_key) is False

    # Mark completed
    idempotency_manager.mark_completed(test_key)

    # Third acquisition still blocked (already completed)
    assert idempotency_manager.check_and_acquire(test_key) is False


@pytest.mark.asyncio
async def test_webhook_idempotency_replay_defense():
    """Verifies that duplicate webhook updates from Telegram are rejected."""
    dup_update_id = int(time.time() * 1000) + 777
    test_user_id = 987654321
    rbac_registry.register_user(test_user_id, TelegramRole.ANALYST)
    update = {
        "update_id": dup_update_id,
        "message": {"text": "/status", "chat": {"id": test_user_id}},
    }

    # First dispatch executes
    res1 = await telegram_bot.handle_webhook_update(update)
    assert res1["status"] == "EXECUTED"

    # Second identical update dispatch is dropped as DUPLICATE_UPDATE
    res2 = await telegram_bot.handle_webhook_update(update)
    assert res2["status"] == "SKIPPED"
    assert res2["reason"] == "DUPLICATE_UPDATE"


# ==============================================================================
# 3. EXPIRING ACTION TOKENS & HMAC SIGNATURE TESTS
# ==============================================================================


def test_action_token_hmac_verification_and_expiry():
    """Verifies cryptographic signature generation, expiry, and tampering detection."""
    payload = {"symbol": "BTC/USDT", "size": 0.5, "direction": "LONG"}
    tok = callback_router.create_action_token(
        "STAGE_CONFIRM_ENTRY", "user_1", "chat_1", payload, ttl_seconds=2
    )

    # 1. Valid token succeeds
    valid, reason = tok.is_valid(expected_user="user_1")
    assert valid is True
    assert reason in ("OK", "VALID")

    # 2. User mismatch rejected
    valid, reason = tok.is_valid(expected_user="intruder_99")
    assert valid is False
    assert reason == "USER_MISMATCH"

    # 3. Payload tampering rejected
    tampered_tok = callback_router.get_action_token(tok.token_id)
    assert tampered_tok is not None
    tampered_tok.payload["size"] = 1000.0  # Attempt unauthorized size alteration
    valid, reason = tampered_tok.is_valid(expected_user="user_1")
    assert valid is False
    assert "SIGNATURE" in reason

    # 4. Token expiration rejected
    time.sleep(2.1)
    valid, reason = tok.is_valid(expected_user="user_1")
    assert valid is False
    assert "EXPIRED" in reason


# ==============================================================================
# 4. TWO-PHASE CONFIRMATION & ATOMIC EXECUTION TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_two_phase_confirmation_lifecycle():
    """Verifies Phase 1 (Arm) -> Phase 2 (Confirmation Card) -> Execution in Shadow Ledger."""
    portfolio_shadow.reset_all_positions()
    user_id = 70002
    chat_id = 55555
    rbac_registry.register_user_role(user_id, TelegramRole.TRADER)

    sig = {
        "symbol": "BTC/USDT",
        "direction": "LONG",
        "entry_price": 89200.0,
        "stop_loss": 88100.0,
        "tp1": 91000.0,
        "kelly_allocation_pct": 2.0,
    }

    # Step 1: Create initial Phase 1 token
    tok_enter = callback_router.create_action_token(
        "STAGE_CONFIRM_ENTRY", user_id, chat_id, sig, ttl_seconds=60
    )

    # Step 2: Operator clicks "Enter Paper Trade" button -> handle_callback_query
    cb_phase1 = {
        "id": "cb_query_1",
        "from": {"id": user_id},
        "message": {"chat": {"id": chat_id}},
        "data": f"act:{tok_enter.token_id}",
    }
    res_phase1 = await telegram_bot.handle_callback_query(cb_phase1)
    assert res_phase1["status"] == "CONFIRMATION_DISPATCHED"
    confirm_token_id = res_phase1["token_id"]

    # Step 3: Operator confirms execution -> CONFIRM_EXECUTE
    cb_phase2 = {
        "id": "cb_query_2",
        "from": {"id": user_id},
        "message": {"chat": {"id": chat_id}},
        "data": f"act:{confirm_token_id}",
    }
    res_phase2 = await telegram_bot.handle_callback_query(cb_phase2)
    assert res_phase2["status"] == "EXECUTION_ATTEMPTED"
    assert res_phase2["result"]["status"] == "EXECUTED"

    # Step 4: Verify trade is recorded in Shadow Portfolio
    open_pos = portfolio_shadow.get_open_positions()
    assert len(open_pos) == 1
    assert open_pos[0]["symbol"] == "BTC/USDT"

    # Step 5: Replaying the same confirmation token is rejected (one-time use)
    res_replay = await telegram_bot.handle_callback_query(cb_phase2)
    assert res_replay["status"] == "EXPIRED_OR_NOT_FOUND"


# ==============================================================================
# 5. EMERGENCY KILL-SWITCH & RISK GATE INTERCEPT TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_emergency_halt_intercepts_trade_execution():
    """Verifies that an emergency lockout engaged via /pause strictly blocks execution."""
    user_id = 90002
    rbac_registry.register_user_role(user_id, TelegramRole.SUPER_ADMIN)

    # 1. Engage Emergency Pause
    event_shock_engine.force_emergency_lockout(True)
    assert event_shock_engine.evaluate_risk_state().trading_lockout is True

    # 2. Attempt paper trade execution while halted
    sig = {
        "symbol": "ETH/USDT",
        "direction": "LONG",
        "entry_price": 2750.0,
        "stop_loss": 2700.0,
        "tp1": 2850.0,
        "kelly_allocation_pct": 1.5,
    }
    exec_attempt = telegram_bot.state_mind.auto_execute_paper_trade(sig)
    assert exec_attempt["status"] == "BLOCKED"
    assert "Event Lockout active" in exec_attempt["reason"]

    # 3. Release Pause via Super Admin
    event_shock_engine.force_emergency_lockout(False)
    assert event_shock_engine.evaluate_risk_state().trading_lockout is False


# ==============================================================================
# 6. PURE-PYTHON CANDLESTICK PNG GENERATOR TESTS
# ==============================================================================


def test_pure_python_candlestick_png_rasterization():
    """Verifies valid PNG binary generation with zero external C-dependencies."""
    from core.data_streamer import data_streamer

    candles = data_streamer.generate_synthetic_candles("BTC/USDT", "15m", count=40)
    png_bytes = telegram_charts.generate_signal_chart(
        candles=candles,
        entry=89000.0,
        sl=88000.0,
        tp1=91500.0,
        symbol="BTC/USDT",
        width=640,
        height=360,
    )

    # Valid PNG Magic bytes
    assert len(png_bytes) > 200
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    # Contains IHDR and IEND chunks
    assert b"IHDR" in png_bytes
    assert b"IDAT" in png_bytes
    assert b"IEND" in png_bytes


# ==============================================================================
# 7. WALK-FORWARD VALIDATION TRIGGER (/test <id>) TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_walk_forward_strategy_validation_command():
    """Verifies that /test triggers sandbox backtesting and updates SQLite stage."""
    trader_id = 70003
    rbac_registry.register_user_role(trader_id, TelegramRole.TRADER)

    # Seed a candidate in Research Lab
    cand_id = f"CAND_TEST_{int(time.time())}"
    with db_manager.get_brain_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO research_provenance_ledger
            (knowledge_id, source_type, title, author_creator, ingested_at, confidence_score, status)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "K-TEST-1",
                "RESEARCH",
                "Mean Reversion Study",
                "Quant Researcher",
                int(time.time() * 1000),
                0.0,
                "QUARANTINED",
            ),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO strategy_candidates
            (candidate_id, knowledge_id, strategy_name, hypothesis, entry_rules, exit_rules, parameter_bounds, required_indicators, validation_stage, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                cand_id,
                "K-TEST-1",
                "Mean Reversion Alpha",
                "15m RSI + FVG mean reversion strategy",
                '{"rule": "rsi < 30"}',
                '{"rule": "rsi > 50"}',
                "{}",
                "{}",
                "UNTESTED",
                int(time.time() * 1000),
            ),
        )
        conn.commit()

    update = {
        "update_id": int(time.time() * 1000) + 888,
        "message": {"text": f"/test {cand_id}", "chat": {"id": 12345}, "from": {"id": trader_id}},
    }

    res = await telegram_bot.handle_webhook_update(update)
    assert res["status"] == "EXECUTED"
    assert "WALK-FORWARD STRATEGY VALIDATION REPORT" in res["response"]
    assert cand_id in res["response"]
    assert "Performance Metrics (3-Tier Cost Modeled)" in res["response"]

    # Verify stage updated in SQLite
    with db_manager.get_brain_conn() as conn:
        row = conn.execute(
            "SELECT validation_stage FROM strategy_candidates WHERE candidate_id = ?", (cand_id,)
        ).fetchone()
        assert row is not None
        assert row["validation_stage"] in ("WALK_FORWARD_TESTED", "REJECTED")


# ==============================================================================
# 8. STRUCTURED AUDIT LOGGING TESTS
# ==============================================================================


def test_telegram_audit_logging_to_sqlite():
    """Verifies that commands, auth denials, and callbacks are recorded in SQLite audit ledger."""
    identity = TelegramUserIdentity(
        user_id="user_audit_test", chat_id="chat_1", role=TelegramRole.TRADER
    )

    # Log command execution
    telegram_audit.log_command_execution(
        identity, "/signal", "BTC/USDT", execution_result="EXECUTED"
    )

    # Log denial
    telegram_audit.log_auth_denied(identity, "/pause", "RISK_ADMIN")

    # Log callback
    telegram_audit.log_callback_action(identity, "CONFIRM_EXECUTE", "tok_abc123", "EXECUTED")

    # Verify rows in system_audit_events table
    with db_manager.get_trading_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM system_audit_events WHERE details_json LIKE '%user_audit_test%' ORDER BY timestamp DESC LIMIT 5;"
        ).fetchall()
        assert len(rows) >= 3
        events = [r["event_type"] for r in rows]
        assert "TELEGRAM_COMMAND" in events
        assert "TELEGRAM_AUTH_DENIED" in events
        assert "TELEGRAM_CALLBACK" in events


# ==============================================================================
# 9. TELEGRAM CHARACTER LIMIT & CHUNKING TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_telegram_message_chunking_and_limits():
    """Verifies that messages exceeding the 4000-character safe ceiling are automatically chunked."""
    from unittest.mock import AsyncMock, patch

    # 1. Short text stays as single chunk
    short_text = "Quantitative Market Intelligence Analysis"
    chunks = telegram_bot._split_message_chunks(short_text, max_chars=4000)
    assert len(chunks) == 1
    assert chunks[0] == short_text

    # 2. Long text (>4000 chars) is split into clean chunks <= 4000 chars
    long_para = "SMC liquidity sweep and orderbook imbalance analysis. " * 100  # ~5500 chars
    assert len(long_para) > 4000
    chunks = telegram_bot._split_message_chunks(long_para, max_chars=4000)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c) <= 4000

    # 3. send_message sends sequential chunks when text exceeds limit
    with (
        patch.object(telegram_bot, "_send_single_payload", new_callable=AsyncMock) as mock_send,
        patch.object(telegram_bot, "bot_token", "123456:mock_token_for_ci"),
    ):
        mock_send.return_value = True
        sent = await telegram_bot.send_message(
            text=long_para,
            parse_mode="Markdown",
            chat_id=12345,
        )
        assert sent is True
        assert mock_send.call_count >= 2
        # Final chunk should contain Part 2
        call_args_list = mock_send.call_args_list
        assert any("[Part 2/" in str(call) for call in call_args_list)
