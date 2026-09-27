"""
core/web3/rpc_client.py
=======================
Institutional Multi-RPC Quorum Client & Freshness Monitor.

Constitutional Mandate:
- Operates STRICTLY in Watch-Only read mode.
- Queries balances, token amounts, and block heights via JSON-RPC.
- Zero private key handling, zero transaction signing, zero broadcast routines.
- Multi-RPC consensus: requires >= 2 agreeing nodes to confirm state.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

import aiohttp

logger = logging.getLogger("sky.web3.rpc_client")

# Public Multi-RPC Cluster Endpoints (Redundant Failover Pools)
DEFAULT_RPC_POOLS: dict[str, list[str]] = {
    "ETHEREUM": [
        "https://cloudflare-eth.com",
        "https://rpc.ankr.com/eth",
        "https://ethereum-rpc.publicnode.com",
    ],
    "ARBITRUM": [
        "https://arb1.arbitrum.io/rpc",
        "https://rpc.ankr.com/arbitrum",
        "https://arbitrum-one-rpc.publicnode.com",
    ],
    "BSC": [
        "https://binance.llamarpc.com",
        "https://rpc.ankr.com/bsc",
        "https://bsc-rpc.publicnode.com",
    ],
    "POLYGON": [
        "https://polygon-rpc.com",
        "https://rpc.ankr.com/polygon",
        "https://polygon-bor-rpc.publicnode.com",
    ],
    "SOLANA": [
        "https://api.mainnet-beta.solana.com",
        "https://solana-rpc.publicnode.com",
        "https://rpc.ankr.com/solana",
    ],
}

# ERC-20 Standard Contract Addresses for Stablecoins
POPULAR_TOKENS: dict[str, dict[str, dict[str, Any]]] = {
    "ETHEREUM": {
        "USDT": {"address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "decimals": 6},
        "USDC": {"address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "decimals": 6},
    },
    "ARBITRUM": {
        "USDT": {"address": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9", "decimals": 6},
        "USDC": {"address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "decimals": 6},
    },
    "BSC": {
        "USDT": {"address": "0x55d398326f99059fF775485246999027B3197955", "decimals": 18},
        "USDC": {"address": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", "decimals": 18},
    },
    "POLYGON": {
        "USDT": {"address": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F", "decimals": 6},
        "USDC": {"address": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", "decimals": 6},
    },
}


class RpcFreshness(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    DEGRADED = "DEGRADED"
    DISAGREEMENT = "DISAGREEMENT"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class RpcNodeResponse:
    url: str
    success: bool
    data: Any = None
    block_height: int = 0
    latency_ms: float = 0.0
    error: str | None = None


@dataclass
class RpcQuorumResult:
    chain: str
    target: str
    metric: str
    value: float
    raw_value: Any
    quorum_status: RpcFreshness
    responding_nodes: int
    agreeing_nodes: int
    total_nodes: int
    latest_block_height: int
    mean_latency_ms: float
    timestamp_ms: int
    node_details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MultiRpcQuorumClient:
    """
    Asynchronous Multi-RPC Quorum Engine with mathematical consensus verification.
    """

    def __init__(
        self,
        custom_pools: dict[str, list[str]] | None = None,
        request_timeout_sec: float = 4.0,
    ) -> None:
        self._pools = custom_pools or DEFAULT_RPC_POOLS
        self._timeout = request_timeout_sec

    async def _post_json_rpc(
        self,
        session: aiohttp.ClientSession,
        url: str,
        method: str,
        params: list[Any],
    ) -> RpcNodeResponse:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": int(time.time() * 1000) % 1000000,
        }
        t0 = time.perf_counter()
        try:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
                headers={"Content-Type": "application/json"},
            ) as resp:
                lat = (time.perf_counter() - t0) * 1000.0
                if resp.status != 200:
                    return RpcNodeResponse(
                        url=url,
                        success=False,
                        latency_ms=lat,
                        error=f"HTTP {resp.status}",
                    )
                body = await resp.json()
                if "error" in body:
                    return RpcNodeResponse(
                        url=url,
                        success=False,
                        latency_ms=lat,
                        error=str(body["error"]),
                    )
                return RpcNodeResponse(
                    url=url,
                    success=True,
                    data=body.get("result"),
                    latency_ms=lat,
                )
        except Exception as e:  # noqa: BLE001
            lat = (time.perf_counter() - t0) * 1000.0
            return RpcNodeResponse(
                url=url,
                success=False,
                latency_ms=lat,
                error=str(e),
            )

    async def get_block_height_quorum(
        self,
        chain: str,
        session: aiohttp.ClientSession | None = None,
    ) -> RpcQuorumResult:
        chain_upper = chain.upper()
        urls = self._pools.get(chain_upper, [])
        now_ms = int(time.time() * 1000)
        if not urls:
            return RpcQuorumResult(
                chain=chain_upper,
                target="BLOCK_HEIGHT",
                metric="block_height",
                value=0.0,
                raw_value=0,
                quorum_status=RpcFreshness.UNAVAILABLE,
                responding_nodes=0,
                agreeing_nodes=0,
                total_nodes=0,
                latest_block_height=0,
                mean_latency_ms=0.0,
                timestamp_ms=now_ms,
            )

        own_session = session is None
        sess = session or aiohttp.ClientSession()

        method = "getSlot" if chain_upper == "SOLANA" else "eth_blockNumber"
        params: list[Any] = []

        try:
            tasks = [self._post_json_rpc(sess, url, method, params) for url in urls]
            responses: list[RpcNodeResponse] = await asyncio.gather(*tasks)
        finally:
            if own_session:
                await sess.close()

        valid_nodes: list[tuple[RpcNodeResponse, int]] = []
        for r in responses:
            if r.success and r.data is not None:
                try:
                    if chain_upper == "SOLANA":
                        slot = int(r.data)
                    else:
                        slot = int(str(r.data), 16) if str(r.data).startswith("0x") else int(r.data)
                    r.block_height = slot
                    valid_nodes.append((r, slot))
                except (ValueError, TypeError):
                    pass

        return self._compute_numeric_quorum(
            chain=chain_upper,
            target="BLOCK_HEIGHT",
            metric="block_height",
            all_responses=responses,
            valid_pairs=valid_nodes,
            now_ms=now_ms,
            tolerance=5.0,  # blocks
        )

    async def get_native_balance(
        self,
        chain: str,
        wallet_address: str,
        session: aiohttp.ClientSession | None = None,
    ) -> RpcQuorumResult:
        """
        Queries native balance (ETH, BNB, POL, SOL) across the quorum pool.
        """
        chain_upper = chain.upper()
        urls = self._pools.get(chain_upper, [])
        now_ms = int(time.time() * 1000)

        if not urls:
            return RpcQuorumResult(
                chain=chain_upper,
                target=wallet_address,
                metric="native_balance",
                value=0.0,
                raw_value=0,
                quorum_status=RpcFreshness.UNAVAILABLE,
                responding_nodes=0,
                agreeing_nodes=0,
                total_nodes=0,
                latest_block_height=0,
                mean_latency_ms=0.0,
                timestamp_ms=now_ms,
            )

        own_session = session is None
        sess = session or aiohttp.ClientSession()

        try:
            if chain_upper == "SOLANA":
                method = "getBalance"
                params = [wallet_address]
            else:
                method = "eth_getBalance"
                params = [wallet_address, "latest"]

            tasks = [self._post_json_rpc(sess, url, method, params) for url in urls]
            responses: list[RpcNodeResponse] = await asyncio.gather(*tasks)
        finally:
            if own_session:
                await sess.close()

        valid_nodes: list[tuple[RpcNodeResponse, float]] = []
        for r in responses:
            if r.success and r.data is not None:
                try:
                    if chain_upper == "SOLANA":
                        lamports = int(
                            r.data.get("value", 0) if isinstance(r.data, dict) else r.data
                        )
                        bal = lamports / 1e9
                    else:
                        wei = int(str(r.data), 16) if str(r.data).startswith("0x") else int(r.data)
                        bal = wei / 1e18
                    valid_nodes.append((r, bal))
                except (ValueError, TypeError):
                    pass

        return self._compute_numeric_quorum(
            chain=chain_upper,
            target=wallet_address,
            metric="native_balance",
            all_responses=responses,
            valid_pairs=valid_nodes,
            now_ms=now_ms,
            tolerance=1e-8,
        )

    async def get_erc20_balance(
        self,
        chain: str,
        token_symbol: str,
        wallet_address: str,
        session: aiohttp.ClientSession | None = None,
    ) -> RpcQuorumResult:
        """
        Queries ERC-20 token balance via standard balanceOf(address).
        """
        chain_upper = chain.upper()
        token_upper = token_symbol.upper()
        now_ms = int(time.time() * 1000)

        chain_tokens = POPULAR_TOKENS.get(chain_upper, {})
        token_meta = chain_tokens.get(token_upper)
        if not token_meta:
            raise ValueError(f"Token {token_symbol} not registered for chain {chain}")

        token_address = token_meta["address"]
        decimals = token_meta["decimals"]

        urls = self._pools.get(chain_upper, [])
        if not urls:
            return RpcQuorumResult(
                chain=chain_upper,
                target=f"{wallet_address}:{token_upper}",
                metric=f"token_balance_{token_upper}",
                value=0.0,
                raw_value=0,
                quorum_status=RpcFreshness.UNAVAILABLE,
                responding_nodes=0,
                agreeing_nodes=0,
                total_nodes=0,
                latest_block_height=0,
                mean_latency_ms=0.0,
                timestamp_ms=now_ms,
            )

        # balanceOf(address) signature: 0x70a08231
        clean_addr = wallet_address.lower().replace("0x", "").zfill(64)
        call_data = f"0x70a08231{clean_addr}"

        own_session = session is None
        sess = session or aiohttp.ClientSession()

        try:
            tasks = [
                self._post_json_rpc(
                    sess,
                    url,
                    "eth_call",
                    [{"to": token_address, "data": call_data}, "latest"],
                )
                for url in urls
            ]
            responses: list[RpcNodeResponse] = await asyncio.gather(*tasks)
        finally:
            if own_session:
                await sess.close()

        valid_nodes: list[tuple[RpcNodeResponse, float]] = []
        for r in responses:
            if r.success and r.data is not None:
                try:
                    raw_hex = str(r.data)
                    raw_int = int(raw_hex, 16) if raw_hex.startswith("0x") else int(raw_hex)
                    bal = raw_int / (10**decimals)
                    valid_nodes.append((r, bal))
                except (ValueError, TypeError):
                    pass

        return self._compute_numeric_quorum(
            chain=chain_upper,
            target=f"{wallet_address}:{token_upper}",
            metric=f"token_balance_{token_upper}",
            all_responses=responses,
            valid_pairs=valid_nodes,
            now_ms=now_ms,
            tolerance=1e-6,
        )

    def _compute_numeric_quorum(
        self,
        chain: str,
        target: str,
        metric: str,
        all_responses: list[RpcNodeResponse],
        valid_pairs: list[tuple[RpcNodeResponse, float]],
        now_ms: int,
        tolerance: float = 1e-8,
    ) -> RpcQuorumResult:
        total_nodes = len(all_responses)
        responding_nodes = len(valid_pairs)

        details = [
            {
                "url": r.url,
                "success": r.success,
                "latency_ms": round(r.latency_ms, 2),
                "error": r.error,
                "data": str(r.data)[:50] if r.data else None,
            }
            for r in all_responses
        ]

        if responding_nodes == 0:
            return RpcQuorumResult(
                chain=chain,
                target=target,
                metric=metric,
                value=0.0,
                raw_value=0,
                quorum_status=RpcFreshness.UNAVAILABLE,
                responding_nodes=0,
                agreeing_nodes=0,
                total_nodes=total_nodes,
                latest_block_height=0,
                mean_latency_ms=0.0,
                timestamp_ms=now_ms,
                node_details=details,
            )

        if responding_nodes == 1:
            r_single, val_single = valid_pairs[0]
            return RpcQuorumResult(
                chain=chain,
                target=target,
                metric=metric,
                value=round(val_single, 8),
                raw_value=val_single,
                quorum_status=RpcFreshness.DEGRADED,
                responding_nodes=1,
                agreeing_nodes=1,
                total_nodes=total_nodes,
                latest_block_height=r_single.block_height,
                mean_latency_ms=round(r_single.latency_ms, 2),
                timestamp_ms=now_ms,
                node_details=details,
            )

        # Cluster values by tolerance
        clusters: list[list[tuple[RpcNodeResponse, float]]] = []
        for pair in valid_pairs:
            placed = False
            for c in clusters:
                ref_val = c[0][1]
                if abs(pair[1] - ref_val) <= tolerance:
                    c.append(pair)
                    placed = True
                    break
            if not placed:
                clusters.append([pair])

        # Sort clusters by size descending
        clusters.sort(key=len, reverse=True)
        top_cluster = clusters[0]
        agreeing_count = len(top_cluster)

        mean_val = sum(p[1] for p in top_cluster) / len(top_cluster)
        mean_lat = sum(p[0].latency_ms for p in top_cluster) / len(top_cluster)
        max_block = max(p[0].block_height for p in top_cluster)

        # Quorum rule: >= 2 agreeing nodes
        if agreeing_count >= 2:
            status = RpcFreshness.FRESH if mean_lat < 4000.0 else RpcFreshness.STALE
        else:
            status = RpcFreshness.DISAGREEMENT

        return RpcQuorumResult(
            chain=chain,
            target=target,
            metric=metric,
            value=round(mean_val, 8),
            raw_value=mean_val,
            quorum_status=status,
            responding_nodes=responding_nodes,
            agreeing_nodes=agreeing_count,
            total_nodes=total_nodes,
            latest_block_height=max_block,
            mean_latency_ms=round(mean_lat, 2),
            timestamp_ms=now_ms,
            node_details=details,
        )


# Global singleton RPC client
multi_rpc_client = MultiRpcQuorumClient()
