"""
core/collective/lease_manager.py
================================
Primary Execution Lease Manager with Epoch Fencing Tokens.

Guarantees:
1. Mutex Fencing: Only one node holds valid live execution authority.
2. Fencing Token: Monotonically increasing counter rejects stale / zombie requests.
3. Epoch Isolation: Leases are bound to node epochs.
4. Fail-Closed Default: If lease is absent, expired, or contested, live execution is strictly BLOCKED.
   Paper trading, research simulations, and UI monitoring continue normally.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.collective.identity import NodeIdentity, node_identity_manager

logger = logging.getLogger("sky.collective.lease_manager")

DEFAULT_LEASE_DURATION_SECONDS = 300  # 5 minutes


@dataclass
class ExecutionLease:
    """Cryptographic lease granting single-node live execution authority."""

    lease_id: str
    node_id: str
    node_epoch: int
    fencing_token: int
    issued_at: str
    expires_at: str
    heartbeat_at: str
    active: bool = True

    def is_valid(self, at_time: datetime.datetime | None = None) -> bool:
        """Checks whether the lease is currently active and within its expiration window."""
        if not self.active:
            return False
        now = at_time or datetime.datetime.now(datetime.UTC)
        try:
            exp = datetime.datetime.fromisoformat(self.expires_at)
            return now < exp
        except (ValueError, TypeError):
            return False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionLease:
        return cls(
            lease_id=data["lease_id"],
            node_id=data["node_id"],
            node_epoch=data.get("node_epoch", 1),
            fencing_token=data.get("fencing_token", 1),
            issued_at=data["issued_at"],
            expires_at=data["expires_at"],
            heartbeat_at=data["heartbeat_at"],
            active=data.get("active", True),
        )


class LeaseManager:
    """Coordinates local and distributed lease acquisition, renewal, and fencing verification."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path(os.getenv("DATA_DIR", "data")) / "collective"
        self.lease_dir = self.base_dir / "lease"
        self.lease_file = self.lease_dir / "execution_lease.json"
        self.lease_dir.mkdir(parents=True, exist_ok=True)

    def get_current_lease(self) -> ExecutionLease | None:
        """Loads the current stored lease if it exists."""
        if not self.lease_file.exists():
            return None
        try:
            with open(self.lease_file, encoding="utf-8") as f:
                data = json.load(f)
            return ExecutionLease.from_dict(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load execution lease: %s", exc)
            return None

    def acquire_or_renew_lease(
        self,
        identity: NodeIdentity | None = None,
        duration_seconds: int = DEFAULT_LEASE_DURATION_SECONDS,
        force: bool = False,
    ) -> ExecutionLease:
        """
        Acquires or extends the primary execution lease for the local node.
        Fails closed if contested by another active node with a higher epoch or non-expired lease.
        """
        ident = identity or node_identity_manager.get_or_create_identity()
        current = self.get_current_lease()

        now = datetime.datetime.now(datetime.UTC)
        now_iso = now.isoformat()
        exp_iso = (now + datetime.timedelta(seconds=duration_seconds)).isoformat()

        # Check existing lease ownership
        if current and current.is_valid(now):
            if current.node_id != ident.node_id and not force:
                logger.error(
                    "Cannot acquire lease: Active lease held by '%s' (expires: %s)",
                    current.node_id,
                    current.expires_at,
                )
                raise PermissionError(
                    f"Execution lease currently held by peer node '{current.node_id}'. "
                    f"Live execution locked until expiration: {current.expires_at}"
                )
            # Renewing local lease
            fencing_token = current.fencing_token + 1
        else:
            # New lease or previous expired
            fencing_token = (current.fencing_token + 1) if current else 1

        new_lease = ExecutionLease(
            lease_id=f"lease_{uuid.uuid4().hex[:12]}",
            node_id=ident.node_id,
            node_epoch=ident.node_epoch,
            fencing_token=fencing_token,
            issued_at=now_iso,
            expires_at=exp_iso,
            heartbeat_at=now_iso,
            active=True,
        )

        with open(self.lease_file, "w", encoding="utf-8") as f:
            json.dump(new_lease.to_dict(), f, indent=2)

        logger.info(
            "Acquired execution lease '%s' for node '%s' (token=%d, expires=%s)",
            new_lease.lease_id,
            ident.node_id,
            fencing_token,
            exp_iso,
        )
        return new_lease

    def release_lease(self, identity: NodeIdentity | None = None) -> bool:
        """Voluntarily relinquishes the execution lease."""
        current = self.get_current_lease()
        if not current:
            return False
        ident = identity or node_identity_manager.get_or_create_identity()
        if current.node_id != ident.node_id:
            logger.warning("Cannot release lease: held by peer '%s'", current.node_id)
            return False

        current.active = False
        with open(self.lease_file, "w", encoding="utf-8") as f:
            json.dump(current.to_dict(), f, indent=2)
        logger.info("Released execution lease for node '%s'", ident.node_id)
        return True

    def verify_live_execution_authority(
        self,
        node_id: str,
        lease_id: str,
        node_epoch: int,
        fencing_token: int,
    ) -> tuple[bool, str]:
        """
        Fencing Verification Gate:
        Rejects stale requests, mismatched epochs, expired leases, or invalid tokens.
        """
        lease = self.get_current_lease()
        if not lease:
            return False, "FAIL_CLOSED: No execution lease found on this cluster node."

        if not lease.is_valid():
            return False, f"FAIL_CLOSED: Execution lease expired at {lease.expires_at}."

        if lease.node_id != node_id:
            return (
                False,
                f"FAIL_CLOSED: Lease owner is '{lease.node_id}', requested by '{node_id}'.",
            )

        if lease.lease_id != lease_id:
            return (
                False,
                f"FAIL_CLOSED: Lease ID mismatch (expected '{lease.lease_id}', got '{lease_id}').",
            )

        if lease.node_epoch != node_epoch:
            return (
                False,
                f"FAIL_CLOSED: Node epoch mismatch (active {lease.node_epoch}, request {node_epoch}).",
            )

        if fencing_token < lease.fencing_token:
            return (
                False,
                f"FAIL_CLOSED: Stale fencing token {fencing_token} < active {lease.fencing_token}.",
            )

        return True, "AUTHORIZED"


# Global singleton
lease_manager = LeaseManager()
