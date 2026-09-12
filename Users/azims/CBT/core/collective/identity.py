"""
core/collective/identity.py
===========================
Node identity, cryptographic keypair generation, and verification for SDCC.

Guarantees:
1. Permanent node_id surviving software and schema upgrades.
2. Ed25519 cryptographic signing for manifests and sync packages.
3. Strict separation: Private keys are NEVER exported or synchronized.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import platform
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

logger = logging.getLogger("sky.collective.identity")

PROTOCOL_VERSION = 1
SCHEMA_VERSION = 1


@dataclass
class NodeIdentity:
    """Represents a node's immutable cryptographic identity."""

    node_id: str
    installation_id: str
    public_key_hex: str
    created_at: str
    schema_version: int = SCHEMA_VERSION
    protocol_version: int = PROTOCOL_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)
    _private_key: ed25519.Ed25519PrivateKey | None = field(default=None, repr=False)

    def sign(self, message: bytes | str) -> str:
        """Signs a message using the node's Ed25519 private key. Returns hex string."""
        if not self._private_key:
            raise RuntimeError(f"Private key not available for node {self.node_id}. Cannot sign.")
        if isinstance(message, str):
            data = message.encode("utf-8")
        else:
            data = message
        signature = self._private_key.sign(data)
        return signature.hex()

    def verify(
        self,
        message: bytes | str,
        signature_hex: str,
        public_key_hex: str | None = None,
    ) -> bool:
        """Verifies a signature against this node's public key or a specified public key."""
        target_pub_hex = public_key_hex or self.public_key_hex
        try:
            pub_bytes = bytes.fromhex(target_pub_hex)
            sig_bytes = bytes.fromhex(signature_hex)
            pub_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
            data = message.encode("utf-8") if isinstance(message, str) else message
            pub_key.verify(sig_bytes, data)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Signature verification failed: {exc}")
            return False

    def to_public_dict(self) -> dict[str, Any]:
        """Returns safe public identity dictionary without private credentials."""
        return {
            "node_id": self.node_id,
            "installation_id": self.installation_id,
            "public_key": self.public_key_hex,
            "created_at": self.created_at,
            "schema_version": self.schema_version,
            "protocol_version": self.protocol_version,
            "metadata": self.metadata,
        }

    def to_dict(self, include_private: bool = False) -> dict[str, Any]:
        """Serializes identity for local storage."""
        data = self.to_public_dict()
        if include_private and self._private_key:
            priv_bytes = self._private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
            data["private_key"] = priv_bytes.hex()
        return data


class NodeIdentityManager:
    """Manages creation, storage, and retrieval of node identities."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path(os.getenv("DATA_DIR", "data")) / "collective"
        self.node_dir = self.base_dir / "node"
        self.identity_file = self.node_dir / "node_identity.json"

    def get_or_create_identity(self, node_id: str | None = None) -> NodeIdentity:
        """Loads an existing identity or creates a new persistent identity."""
        existing = self.load_identity()
        if existing:
            # If user explicitly passed node_id and it differs, log warning and preserve or update if uninitialized
            if node_id and existing.node_id != node_id:
                logger.warning(
                    f"Node identity already exists as '{existing.node_id}'; ignoring requested '{node_id}' to preserve immutability."
                )
            return existing

        # Create new identity
        effective_node_id = (
            node_id
            or os.getenv("SKY_NODE_ID")
            or ("OFFICE-01" if platform.system() == "Windows" else "HOME-01")
        )
        return self.create_identity(effective_node_id)

    def create_identity(self, node_id: str) -> NodeIdentity:
        """Creates and persists a brand-new Ed25519 identity."""
        self.node_dir.mkdir(parents=True, exist_ok=True)

        priv_key = ed25519.Ed25519PrivateKey.generate()
        pub_key = priv_key.public_key()

        pub_bytes = pub_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        now_iso = datetime.datetime.now(datetime.UTC).isoformat()
        installation_id = str(uuid.uuid4())

        metadata = {
            "platform": platform.platform(),
            "hostname": platform.node(),
            "python_version": platform.python_version(),
        }

        identity = NodeIdentity(
            node_id=node_id,
            installation_id=installation_id,
            public_key_hex=pub_bytes.hex(),
            created_at=now_iso,
            schema_version=SCHEMA_VERSION,
            protocol_version=PROTOCOL_VERSION,
            metadata=metadata,
            _private_key=priv_key,
        )

        # Save to local node file
        payload = identity.to_dict(include_private=True)
        with open(self.identity_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        logger.info(
            f"Generated new permanent node identity for '{node_id}' at {self.identity_file}"
        )
        return identity

    def load_identity(self) -> NodeIdentity | None:
        """Loads node identity from storage if available."""
        if not self.identity_file.exists():
            return None

        try:
            with open(self.identity_file, encoding="utf-8") as f:
                data = json.load(f)

            priv_key = None
            if "private_key" in data:
                priv_bytes = bytes.fromhex(data["private_key"])
                priv_key = ed25519.Ed25519PrivateKey.from_private_bytes(priv_bytes)

            return NodeIdentity(
                node_id=data["node_id"],
                installation_id=data["installation_id"],
                public_key_hex=data["public_key"],
                created_at=data["created_at"],
                schema_version=data.get("schema_version", SCHEMA_VERSION),
                protocol_version=data.get("protocol_version", PROTOCOL_VERSION),
                metadata=data.get("metadata", {}),
                _private_key=priv_key,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Failed to load node identity from {self.identity_file}: {exc}")
            return None


# Global identity manager instance
node_identity_manager = NodeIdentityManager()
