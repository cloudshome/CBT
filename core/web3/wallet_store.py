"""
core/web3/wallet_store.py
=========================
Watch-Only Web3 Wallet Storage with Strict Anti-Key Invariants.

Constitutional Mandate:
- Stores public wallet addresses for balance observation ONLY.
- Hard SQLite CHECK constraint: is_watch_only = 1.
- Validates address syntax (EVM 0x... 40 hex chars, Solana base58).
- Reject-closed: strictly rejects private keys, WIF strings, and seed phrase mnemonics.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.auth.security_store import security_store

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Address format validation regexes
EVM_ADDRESS_REGEX = re.compile(r"^0x[a-fA-F0-9]{40}$")
SOLANA_ADDRESS_REGEX = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

# Reject patterns for private keys and mnemonics
RAW_PRIVATE_KEY_REGEX = re.compile(r"^[a-fA-F0-9]{64}$")  # 64 hex without 0x
SEED_PHRASE_REGEX = re.compile(r"^([a-zA-Z]+\s+){11,23}[a-zA-Z]+$")  # 12-24 words


class Web3SecurityViolationError(ValueError):
    """Raised when an attempt is made to store private keys or mnemonics."""


@dataclass
class WatchWallet:
    address: str
    chain: str
    label: str
    is_watch_only: bool
    created_at: int
    last_synced_at: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Web3WalletStore:
    def __init__(self) -> None:
        self._init_db()

    def _init_db(self) -> None:
        with security_store.get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS web3_watch_wallets (
                    address TEXT PRIMARY KEY,
                    chain TEXT NOT NULL,
                    label TEXT NOT NULL,
                    is_watch_only INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    last_synced_at INTEGER NOT NULL,
                    CONSTRAINT chk_watch_only CHECK (is_watch_only = 1)
                )
                """
            )
            conn.commit()

    def validate_public_address(self, chain: str, address: str) -> str:
        """
        Validates address syntax and actively screens against private key / mnemonic entry.
        """
        clean_addr = address.strip()
        chain_upper = chain.upper()

        # Check for mnemonic injection
        if SEED_PHRASE_REGEX.match(clean_addr):
            raise Web3SecurityViolationError(
                "SECURITY REJECTION: Seed phrase / mnemonic detected. "
                "Crypto Brain Terminal operates strictly in Watch-Only mode and rejects all private seeds."
            )

        # Check for raw 64-char hex private key
        if RAW_PRIVATE_KEY_REGEX.match(clean_addr):
            raise Web3SecurityViolationError(
                "SECURITY REJECTION: Raw 32-byte private key detected. "
                "Private keys are strictly forbidden. Only public wallet addresses are permitted."
            )

        # Validate syntax by chain
        if chain_upper in ("ETHEREUM", "ARBITRUM", "BSC", "POLYGON"):
            if not EVM_ADDRESS_REGEX.match(clean_addr):
                raise ValueError(
                    f"Invalid EVM address format for {chain_upper}: {clean_addr}. "
                    f"Must start with 0x followed by 40 hex characters."
                )
            return clean_addr.lower()
        elif chain_upper == "SOLANA":
            if not SOLANA_ADDRESS_REGEX.match(clean_addr):
                raise ValueError(
                    f"Invalid Solana address format: {clean_addr}. "
                    f"Must be base58 between 32 and 44 characters."
                )
            return clean_addr
        else:
            raise ValueError(
                f"Unsupported blockchain: {chain}. Supported: ETHEREUM, ARBITRUM, BSC, POLYGON, SOLANA."
            )

    def add_wallet(self, chain: str, address: str, label: str = "") -> WatchWallet:
        normalized_addr = self.validate_public_address(chain, address)
        now_ms = int(time.time() * 1000)
        clean_label = label.strip() or f"{chain.upper()} Watch Wallet"

        with security_store.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO web3_watch_wallets (address, chain, label, is_watch_only, created_at, last_synced_at)
                VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(address) DO UPDATE SET
                    label = excluded.label,
                    chain = excluded.chain,
                    last_synced_at = excluded.last_synced_at
                """,
                (normalized_addr, chain.upper(), clean_label, now_ms, now_ms),
            )
            conn.commit()

        return WatchWallet(
            address=normalized_addr,
            chain=chain.upper(),
            label=clean_label,
            is_watch_only=True,
            created_at=now_ms,
            last_synced_at=now_ms,
        )

    def list_wallets(self) -> list[WatchWallet]:
        with security_store.get_connection() as conn:
            cur = conn.execute(
                "SELECT address, chain, label, is_watch_only, created_at, last_synced_at FROM web3_watch_wallets ORDER BY created_at ASC"
            )
            rows = cur.fetchall()

        return [
            WatchWallet(
                address=r["address"],
                chain=r["chain"],
                label=r["label"],
                is_watch_only=bool(r["is_watch_only"]),
                created_at=r["created_at"],
                last_synced_at=r["last_synced_at"],
            )
            for r in rows
        ]

    def remove_wallet(self, address: str) -> bool:
        clean_addr = address.strip().lower()
        with security_store.get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM web3_watch_wallets WHERE lower(address) = ?",
                (clean_addr,),
            )
            conn.commit()
            return cur.rowcount > 0


# Global singleton wallet store
web3_wallet_store = Web3WalletStore()
