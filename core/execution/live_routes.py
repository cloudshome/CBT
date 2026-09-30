"""
core/execution/live_routes.py
=============================
Milestone 21 FastAPI Router: Live Account Readiness, Gatekeeper & Canary Endpoints.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.auth import require_api_key
from core.auth.credential_vault import credential_vault
from core.execution.account_probe import account_probe
from core.execution.live_canary_runner import CanaryRunRequest, live_canary_runner
from core.execution.live_gatekeeper import live_gatekeeper

logger = logging.getLogger("sky.execution.live_routes")

router = APIRouter(prefix="/api/execution", tags=["Live Execution Gatekeeper"])


class LivePreflightCheckRequest(BaseModel):
    exchange: str = Field(default="BINANCE", description="BINANCE or BYBIT")
    order_notional_usd: float = Field(default=10.0, description="Requested order notional in USD")
    environment: str = Field(default="PRODUCTION", description="PRODUCTION or TESTNET")
    session_id: str | None = Field(default=None, description="Optional client session ID")


class CanaryExecuteRequest(BaseModel):
    exchange: str = Field(default="BINANCE", description="BINANCE or BYBIT")
    symbol: str = Field(default="BTC/USDT", description="Target symbol")
    notional_usd: float = Field(default=10.0, ge=5.0, le=25.0, description="Canary size in USD")
    side: str = Field(default="BUY", description="BUY or SELL")
    order_type: str = Field(default="LIMIT", description="LIMIT or MARKET")
    price: float | None = Field(default=None, description="Optional limit price")
    stop_loss_price: float | None = Field(
        default=None, description="Optional stop-loss price for risk ceiling calculation"
    )
    environment: str = Field(default="PRODUCTION", description="PRODUCTION or TESTNET")
    is_dry_run: bool = Field(default=True, description="Safe dry-run simulation mode")
    strategy_id: str = Field(
        default="STRAT_SMC_INSTITUTIONAL", description="Strategy identifier for Gate 7 clearance"
    )
    session_id: str | None = Field(default=None, description="Optional client session ID")


@router.get("/account-readiness")
async def get_account_readiness(
    environment: str = Query("PRODUCTION", description="PRODUCTION or TESTNET"),
):
    """
    Returns real-time multi-exchange balance probe, free margin,
    constitutional 1.5% single-trade equity cap, and 6.0% portfolio heat limits.
    """
    summary = await account_probe.get_portfolio_readiness(environment=environment)
    return {
        "status": "SUCCESS",
        "timestamp_ms": summary.timestamp_ms,
        "vault_unlocked": summary.vault_unlocked,
        "total_portfolio_equity_usd": summary.total_portfolio_equity_usd,
        "total_free_cash_usd": summary.total_free_cash_usd,
        "single_trade_equity_cap_usd": summary.single_trade_equity_cap_usd,
        "max_portfolio_heat_usd": summary.max_portfolio_heat_usd,
        "active_exchanges": summary.active_exchanges,
        "exchange_statuses": {
            k: {
                "exchange": v.exchange,
                "environment": v.environment,
                "is_connected": v.is_connected,
                "latency_ms": v.latency_ms,
                "total_equity_usd": v.total_equity_usd,
                "free_cash_usd": v.free_cash_usd,
                "locked_margin_usd": v.locked_margin_usd,
                "error_message": v.error_message,
                "balances_count": len(v.balances),
            }
            for k, v in summary.exchange_statuses.items()
        },
        "is_ready_for_canary_trade": summary.is_ready_for_canary_trade,
        "reasons": summary.reasons,
    }


@router.post("/live-gatekeeper/check")
async def evaluate_gatekeeper_clearance(req: LivePreflightCheckRequest):
    """
    Executes all 6 non-bypassable constitutional preflight checks:
    1. Vault key derivation check
    2. Master Kill Switch status
    3. Exchange connectivity & clock drift (<500ms)
    4. 3.0% daily drawdown stop
    5. 1.5% single-trade equity cap conformity
    6. LIVE_TRADING_ENABLED authorization
    """
    verdict = await live_gatekeeper.evaluate_order_clearance(
        exchange=req.exchange,
        order_notional_usd=req.order_notional_usd,
        environment=req.environment,
        session_id=req.session_id,
    )
    return {
        "status": "SUCCESS",
        "verdict": asdict(verdict),
    }


@router.post("/live-canary/run", dependencies=[Depends(require_api_key)])
async def run_live_canary_order(req: CanaryExecuteRequest):
    """
    Executes or dry-runs a micro-notional live canary order ($10 - $25).
    Enforces all 8 constitutional checks and fail-closed safety.
    """
    canary_req = CanaryRunRequest(
        exchange=req.exchange,
        symbol=req.symbol,
        notional_usd=req.notional_usd,
        side=req.side,
        order_type=req.order_type,
        price=req.price,
        stop_loss_price=req.stop_loss_price,
        environment=req.environment,
        is_dry_run=req.is_dry_run,
        strategy_id=req.strategy_id,
        session_id=req.session_id,
    )
    res = await live_canary_runner.execute_canary_order(canary_req)
    return {
        "status": "SUCCESS" if res.success else "GATED",
        "result": res.to_dict(),
    }


class VaultVerifyRequest(BaseModel):
    exchange: str = Field(default="BINANCE", description="BINANCE or BYBIT")
    environment: str = Field(default="PRODUCTION", description="PRODUCTION or TESTNET")


class VaultRevokeRequest(BaseModel):
    exchange: str = Field(default="BINANCE", description="BINANCE or BYBIT")
    environment: str = Field(default="PRODUCTION", description="PRODUCTION or TESTNET")


@router.post("/vault/verify", dependencies=[Depends(require_api_key)])
async def verify_vault_credential_endpoint(req: VaultVerifyRequest):
    """
    Authenticated multi-tier probe validating API key connectivity, signing, and permissions.
    Asserts positive proof that withdrawals are strictly disabled.
    Never returns raw exchange response bodies or secrets.
    """
    res = await credential_vault.verify_credential_connectivity(
        exchange=req.exchange, environment=req.environment
    )
    return {
        "status": "SUCCESS" if res.status == "PASS" else "FAILED",
        "verification": res.to_safe_dict(),
    }


@router.delete("/vault/credential", dependencies=[Depends(require_api_key)])
async def revoke_vault_credential_endpoint(req: VaultRevokeRequest):
    """
    Revokes an exchange credential:
    Flushes database, invalidates in-memory capability cache, and closes active connector sessions.
    """
    deleted = credential_vault.revoke_credential(req.exchange, req.environment)
    return {
        "status": "SUCCESS" if deleted else "NOT_FOUND",
        "message": f"Credential for {req.exchange} [{req.environment}] revoked and capabilities invalidated.",
        "deleted": deleted,
    }


@router.get("/live-canary/status")
async def get_live_canary_status():
    """Returns the current operational canary boundaries and readiness posture."""
    readiness = await account_probe.get_portfolio_readiness()
    return {
        "status": "OPERATIONAL",
        "min_canary_notional_usd": live_canary_runner.min_canary_notional_usd,
        "max_canary_notional_usd": live_canary_runner.max_canary_notional_usd,
        "vault_unlocked": readiness.vault_unlocked,
        "is_ready_for_canary": readiness.is_ready_for_canary_trade,
        "single_trade_cap_usd": readiness.single_trade_equity_cap_usd,
        "reasons": readiness.reasons,
        "timestamp_ms": int(time.time() * 1000),
    }


# =====================================================================
# Phase 22 Milestone 1: Live State, Panic Flatten & Position Control
# =====================================================================


class PanicCloseRequest(BaseModel):
    exchange: str = Field(default="BINANCE", description="BINANCE or BYBIT")
    symbol: str = Field(default="BTCUSDT", description="Target symbol")
    environment: str = Field(default="TESTNET", description="TESTNET or PRODUCTION")
    reason: str = Field(default="OPERATOR_PANIC", description="Reason for panic liquidation")


class MoveToBreakevenRequest(BaseModel):
    exchange: str = Field(default="BINANCE", description="BINANCE or BYBIT")
    symbol: str = Field(default="BTCUSDT", description="Target symbol")
    environment: str = Field(default="TESTNET", description="TESTNET or PRODUCTION")


class CancelLiveOrderRequest(BaseModel):
    exchange: str = Field(default="BINANCE", description="BINANCE or BYBIT")
    symbol: str = Field(default="BTCUSDT", description="Target symbol")
    order_id: str = Field(description="Exchange order ID to cancel")
    client_order_id: str | None = Field(default=None, description="Optional client order ID")
    environment: str = Field(default="TESTNET", description="TESTNET or PRODUCTION")


class CancelAllOrdersRequest(BaseModel):
    exchange: str = Field(default="BINANCE", description="BINANCE or BYBIT")
    symbol: str = Field(default="BTCUSDT", description="Target symbol")
    environment: str = Field(default="TESTNET", description="TESTNET or PRODUCTION")


class ProtectedOrderRequest(BaseModel):
    exchange: str = Field(default="BINANCE", description="BINANCE or BYBIT")
    symbol: str = Field(default="BTCUSDT", description="Target symbol")
    side: str = Field(default="BUY", description="BUY or SELL")
    quantity: float = Field(gt=0.0, description="Order quantity")
    tp_price: float = Field(gt=0.0, description="Take profit price")
    sl_price: float = Field(gt=0.0, description="Stop loss price")
    sl_limit_price: float | None = Field(default=None, description="Optional SL limit price")
    price: float | None = Field(default=None, description="Optional limit price for entry")
    order_type: str = Field(default="LIMIT", description="LIMIT or MARKET")
    environment: str = Field(default="TESTNET", description="TESTNET or PRODUCTION")
    strategy_id: str = Field(default="MANUAL_COCKPIT", description="Originating strategy ID")
    session_id: str | None = Field(
        default=None, description="Optional client session ID for Gate 8 clearance"
    )


@router.get("/live/state")
async def get_live_execution_state(
    exchange: str = Query("BINANCE", description="BINANCE or BYBIT"),
    environment: str = Query("TESTNET", description="TESTNET or PRODUCTION"),
    symbol: str | None = Query(None, description="Optional symbol filter"),
):
    """
    Returns single authoritative execution snapshot:
    - Active open positions with mark price, unrealized PnL, risk-R ratio
    - Canonical protection status: 🟢 PROTECTED vs 🔴 UNPROTECTED
    - Active working orders table
    - Active protection brackets
    - Risk state (kill switch, vault unlock status)
    """
    from core.execution.order_reconciliation import canonical_reconciler

    snapshot = await canonical_reconciler.reconcile_state(
        exchange=exchange,
        environment=environment,
        symbol_filter=symbol,
    )
    return {
        "status": "SUCCESS",
        "snapshot": snapshot.to_dict(),
    }


@router.post("/live/panic-close", dependencies=[Depends(require_api_key)])
async def execute_live_panic_close(req: PanicCloseRequest):
    """
    Independent Emergency Panic Close.
    Cancels all orders -> queries live balance -> market flattens inventory -> verifies 0.0 flat state.
    """
    from core.execution.bracket_manager import live_bracket_manager

    res = await live_bracket_manager.emergency_panic_close(
        exchange=req.exchange,
        symbol=req.symbol,
        environment=req.environment,
        reason=req.reason,
    )
    return {
        "status": "SUCCESS" if res.success else "FAILED",
        "result": res.to_dict(),
    }


@router.post("/live/bracket/breakeven", dependencies=[Depends(require_api_key)])
async def move_bracket_to_breakeven(req: MoveToBreakevenRequest):
    """
    Moves Stop Loss to Break-Even (Entry Price) with ZERO unprotected gap.
    """
    from core.execution.bracket_manager import live_bracket_manager

    res = await live_bracket_manager.move_to_breakeven(
        symbol=req.symbol,
        exchange=req.exchange,
        environment=req.environment,
    )
    return {
        "status": "SUCCESS" if res.success else "FAILED",
        "result": res.to_dict(),
    }


@router.post("/live/order/cancel", dependencies=[Depends(require_api_key)])
async def cancel_live_order(req: CancelLiveOrderRequest):
    """Cancels a specific live working order."""
    from core.execution.bracket_manager import live_bracket_manager

    res = await live_bracket_manager.cancel_order(
        symbol=req.symbol,
        order_id=req.order_id,
        client_order_id=req.client_order_id,
        exchange=req.exchange,
        environment=req.environment,
    )
    return {
        "status": "SUCCESS",
        "result": res,
    }


@router.post("/live/orders/cancel-all", dependencies=[Depends(require_api_key)])
async def cancel_all_live_orders(req: CancelAllOrdersRequest):
    """Cancels all active open orders for a symbol."""
    from core.execution.bracket_manager import live_bracket_manager

    res = await live_bracket_manager.cancel_all_orders(
        symbol=req.symbol,
        exchange=req.exchange,
        environment=req.environment,
    )
    return {
        "status": "SUCCESS",
        "result": res,
    }


@router.post("/live/protected-order", dependencies=[Depends(require_api_key)])
async def submit_protected_live_order(req: ProtectedOrderRequest):
    """
    Submits a live entry order through the Protected-Entry State Machine.
    Hard fail-closed: If protection cannot be confirmed after fill, position is automatically flattened.
    Enforces Gate 8 Human Live Clearance in PRODUCTION environment.
    """
    if req.environment.upper() == "PRODUCTION":
        from core.auth.hardware_key import hardware_key_manager

        is_cleared, clearance, reason_code = hardware_key_manager.check_live_clearance(
            session_id=req.session_id
        )
        if not is_cleared:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": reason_code or "HARDWARE_KEY_CLEARANCE_REQUIRED",
                    "message": "Production execution requires an active WebAuthn/FIDO2 hardware security key clearance session.",
                },
            )

    from core.execution.bracket_manager import live_bracket_manager

    ctx = await live_bracket_manager.enter_protected_trade(
        symbol=req.symbol,
        side=req.side,
        quantity=req.quantity,
        tp_price=req.tp_price,
        sl_price=req.sl_price,
        sl_limit_price=req.sl_limit_price,
        requested_price=req.price,
        order_type=req.order_type,
        exchange=req.exchange,
        environment=req.environment,
        strategy_id=req.strategy_id,
    )
    return {
        "status": "SUCCESS" if ctx.state.value in ("PROTECTED", "ENTRY_SUBMITTED") else "ESCALATED",
        "context": ctx.to_dict(),
    }


@router.get("/live/provenance/{execution_id}")
async def get_execution_provenance(execution_id: str):
    """Queries cryptographic lineage and verifies SHA-256 hash integrity."""
    from core.execution.execution_provenance import execution_provenance_tracker

    record = execution_provenance_tracker.get_provenance(execution_id)
    if not record:
        return {"status": "NOT_FOUND", "execution_id": execution_id}

    is_valid = execution_provenance_tracker.verify_lineage(execution_id)
    return {
        "status": "SUCCESS",
        "is_valid": is_valid,
        "provenance": record.to_dict(),
    }


# =============================================================================
# Milestone 22.3: Capital Escalation & Walk-Forward Risk Governance Endpoints
# =============================================================================
class EscalationEvaluateRequest(BaseModel):
    strategy_id: str = Field(default="STRAT_SMC_INSTITUTIONAL")
    sharpe: float = Field(default=0.0)
    trade_count: int = Field(default=0)
    trials_count: int = Field(default=10)
    max_drawdown: float = Field(default=0.0)
    slippage_bps: float = Field(default=0.0)
    regime_count: int = Field(default=1)
    skewness: float = Field(default=0.0)
    kurtosis: float = Field(default=3.0)


class ActivateEligibleRequest(BaseModel):
    strategy_id: str = Field(default="STRAT_SMC_INSTITUTIONAL")
    operator: str = Field(default="OPERATOR_DESK")


class ClampTierRequest(BaseModel):
    strategy_id: str = Field(default="STRAT_SMC_INSTITUTIONAL")
    target_tier: str = Field(description="Target tier enum string to clamp downward to")
    reason: str = Field(description="Mandatory justification for administrative downward clamp")
    operator: str = Field(default="OPERATOR_DESK")


class AuthorizeProductionRequest(BaseModel):
    strategy_id: str = Field(default="STRAT_SMC_INSTITUTIONAL")
    hmac_signature: str = Field(
        description="HMAC-SHA256 signature of strategy_id:payload:timestamp"
    )
    auth_payload: str = Field(description="Payload token signed by cold key")
    secret_key: str = Field(description="Verification secret")
    timestamp_ms: int = Field(description="Token generation timestamp ms")


@router.get("/escalation/status")
async def get_capital_escalation_status(
    strategy_id: str = Query("STRAT_SMC_INSTITUTIONAL", description="Strategy identifier"),
):
    """Returns real-time Capital Escalation status, 8-state ladder, limits, and decision audit logs."""
    from core.execution.capital_governor import capital_governor

    return {
        "status": "SUCCESS",
        "escalation": capital_governor.get_escalation_report(strategy_id),
    }


@router.post("/escalation/evaluate")
async def evaluate_capital_escalation(req: EscalationEvaluateRequest):
    """
    Evaluates 6-pillar walk-forward evidence stack for promotion eligibility.
    Advances strictly to *_ELIGIBLE (never automatic real capital).
    """
    from core.execution.capital_governor import capital_governor

    evidence = {
        "sharpe": req.sharpe,
        "trade_count": req.trade_count,
        "trials_count": req.trials_count,
        "max_drawdown": req.max_drawdown,
        "slippage_bps": req.slippage_bps,
        "regime_count": req.regime_count,
        "skewness": req.skewness,
        "kurtosis": req.kurtosis,
    }
    result = capital_governor.evaluate_escalation(strategy_id=req.strategy_id, evidence=evidence)
    return {
        "status": "SUCCESS",
        "evaluation": result,
    }


@router.post("/escalation/activate-eligible", dependencies=[Depends(require_api_key)])
async def activate_eligible_tier(req: ActivateEligibleRequest):
    """
    Explicitly activates an *_ELIGIBLE state into its live execution tier counterpart.
    """
    from core.execution.capital_governor import capital_governor

    try:
        res = capital_governor.activate_eligible_tier(
            strategy_id=req.strategy_id, operator=req.operator
        )
        return {"status": "SUCCESS", "result": res}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/escalation/clamp", dependencies=[Depends(require_api_key)])
async def clamp_capital_tier(req: ClampTierRequest):
    """
    Administratively clamps a capital tier strictly DOWNWARD.
    Rejects any upward manual promotion request with HTTP 400.
    """
    from core.execution.capital_governor import capital_governor

    try:
        res = capital_governor.clamp_tier_downward(
            target_tier_str=req.target_tier,
            reason=req.reason,
            strategy_id=req.strategy_id,
            operator=req.operator,
        )
        return {"status": "SUCCESS", "result": res}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/escalation/authorize-production", dependencies=[Depends(require_api_key)])
async def authorize_production_tier(req: AuthorizeProductionRequest):
    """
    Cryptographically authorizes Tier 8 (Production) using an HMAC-SHA256 token.
    Cannot be reached autonomously.
    """
    from core.execution.capital_governor import capital_governor

    try:
        res = capital_governor.authorize_production_tier(
            strategy_id=req.strategy_id,
            hmac_signature=req.hmac_signature,
            auth_payload=req.auth_payload,
            secret_key=req.secret_key,
            timestamp_ms=req.timestamp_ms,
        )
        return {"status": "SUCCESS", "result": res}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
