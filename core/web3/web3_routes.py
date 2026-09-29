"""
core/web3/web3_routes.py
========================
FastAPI Endpoints for Web3 Watch-Only Wallets & Aggregated Portfolio Scorecard.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.web3.portfolio_aggregator import portfolio_aggregator
from core.web3.rpc_client import DEFAULT_RPC_POOLS, multi_rpc_client
from core.web3.wallet_store import (
    Web3SecurityViolationError,
    web3_wallet_store,
)

router = APIRouter(tags=["Web3 Watch-Only & Portfolio"])


class AddWalletRequest(BaseModel):
    chain: str = Field(..., description="Blockchain: ETHEREUM, ARBITRUM, BSC, POLYGON, SOLANA")
    address: str = Field(..., description="Public wallet address ONLY")
    label: str = Field("", description="Optional custom label")


@router.get("/api/web3/wallets")
async def list_wallets() -> dict[str, Any]:
    """Returns all registered watch-only public addresses."""
    wallets = web3_wallet_store.list_wallets()
    return {
        "status": "SUCCESS",
        "mode": "WATCH_ONLY_IMMUTABLE",
        "count": len(wallets),
        "wallets": [w.to_dict() for w in wallets],
    }


@router.post("/api/web3/wallets")
async def add_wallet(req: AddWalletRequest) -> dict[str, Any]:
    """
    Registers a watch-only public wallet address.
    Strictly rejects any private keys or seed phrase mnemonics.
    """
    try:
        wallet = web3_wallet_store.add_wallet(
            chain=req.chain,
            address=req.address,
            label=req.label,
        )
        return {
            "status": "SUCCESS",
            "message": f"Registered watch-only address for {wallet.chain}.",
            "wallet": wallet.to_dict(),
        }
    except Web3SecurityViolationError as sec_err:
        raise HTTPException(status_code=400, detail=str(sec_err)) from sec_err
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err)) from val_err


@router.delete("/api/web3/wallets/{address}")
async def delete_wallet(address: str) -> dict[str, Any]:
    """Removes a registered watch-only wallet."""
    success = web3_wallet_store.remove_wallet(address)
    if not success:
        raise HTTPException(status_code=404, detail="Wallet address not found.")
    return {"status": "SUCCESS", "message": f"Removed wallet {address}"}


@router.get("/api/web3/balances")
async def get_wallet_balances() -> dict[str, Any]:
    """Scans and returns live balances for all registered watch-only wallets."""
    wallets = web3_wallet_store.list_wallets()
    reports = []
    for w in wallets:
        rep = await portfolio_aggregator.scan_watch_wallet(w.chain, w.address, w.label)
        reports.append(rep.to_dict())

    return {
        "status": "SUCCESS",
        "mode": "WATCH_ONLY_IMMUTABLE",
        "count": len(reports),
        "total_watch_equity_usd": round(sum(r["total_value_usd"] for r in reports), 2),
        "balances": reports,
    }


@router.get("/api/web3/rpc-status")
async def get_rpc_status() -> dict[str, Any]:
    """Checks block height and quorum status across configured RPC clusters."""
    chains = list(DEFAULT_RPC_POOLS.keys())
    results = {}
    for c in chains:
        res = await multi_rpc_client.get_block_height_quorum(c)
        results[c] = res.to_dict()

    return {
        "status": "SUCCESS",
        "quorum_results": results,
    }


@router.get("/api/portfolio/aggregated-equity")
async def get_aggregated_equity() -> dict[str, Any]:
    """
    Returns unified portfolio scorecard separating live margin from watch-only capital.
    """
    # Sample exchange balance probe (or live connector values if present)
    exchange_balances = {"BINANCE_MARGIN": 0.0, "BYBIT_MARGIN": 0.0, "HYPERLIQUID_EQUITY": 0.0}

    scorecard = await portfolio_aggregator.get_aggregated_scorecard(exchange_balances)
    return {
        "status": "SUCCESS",
        "scorecard": scorecard.to_dict(),
    }
