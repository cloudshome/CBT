"""
core/collective/event_hash.py
=============================
Deterministic canonical serialization and cryptographic hashing for SDCC events.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_bytes(obj: Any) -> bytes:
    """
    Serializes a Python dict/object into canonical deterministic UTF-8 JSON bytes.
    - Keys are lexicographically sorted at all nesting levels.
    - Separators are compact (',' and ':').
    - Unicode is preserved without ASCII escaping.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def canonical_json_str(obj: Any) -> str:
    """Returns canonical JSON as a decoded UTF-8 string."""
    return canonical_json_bytes(obj).decode("utf-8")


def sha256_digest(data: bytes | str) -> str:
    """Computes standard hex SHA-256 hash."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def compute_payload_hash(payload: dict[str, Any]) -> str:
    """Computes SHA-256 hash of canonicalized payload."""
    return sha256_digest(canonical_json_bytes(payload))


def compute_event_hash(event_dict: dict[str, Any]) -> str:
    """
    Computes SHA-256 hash of canonicalized event envelope excluding the integrity field itself.
    """
    envelope_copy = {k: v for k, v in event_dict.items() if k != "integrity"}
    return sha256_digest(canonical_json_bytes(envelope_copy))


def verify_event_integrity(event_dict: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Validates both payload_sha256 and event_sha256 against actual content.
    Returns (True, None) if valid, or (False, reason) if corrupt/tampered.
    """
    integrity = event_dict.get("integrity")
    if not integrity or not isinstance(integrity, dict):
        return False, "Missing or invalid integrity block"

    expected_payload_hash = integrity.get("payload_sha256")
    expected_event_hash = integrity.get("event_sha256")

    if not expected_payload_hash or not expected_event_hash:
        return False, "Missing required payload_sha256 or event_sha256"

    # Verify payload
    payload = event_dict.get("payload", {})
    actual_payload_hash = compute_payload_hash(payload)
    if actual_payload_hash != expected_payload_hash:
        return (
            False,
            f"Payload hash mismatch: expected {expected_payload_hash}, actual {actual_payload_hash}",
        )

    # Verify envelope
    actual_event_hash = compute_event_hash(event_dict)
    if actual_event_hash != expected_event_hash:
        return (
            False,
            f"Event hash mismatch: expected {expected_event_hash}, actual {actual_event_hash}",
        )

    return True, None
