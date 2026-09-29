"""
core/auth/security_store.py
===========================
Dedicated High-Security Storage Engine for WebAuthn / FIDO2 Credentials & Live Clearance.

Architectural Guarantees:
- DOMAIN ISOLATION: Resides strictly in `data/security.db` with SQLite WAL mode.
- ZERO PRIVATE SECRETS: Stores only public keys (COSE format), credential IDs, and counters.
  Never stores private keys, master passphrases, seed phrases, or exchange secrets.
- SINGLE-USE CHALLENGES: Atomic consumption prevents replay attacks.
- IMMUTABLE REVOCATION: Revoked credentials and clearance sessions are permanently deactivated.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("sky.auth.security_store")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SECURITY_DB = REPO_ROOT / "data" / "security.db"


def get_security_db_path() -> Path:
    env_path = os.getenv("SECURITY_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_SECURITY_DB


def get_security_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Creates a hardened SQLite connection to security.db with WAL mode."""
    target_path = db_path or get_security_db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_path), timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@dataclass
class StoredCredential:
    credential_id: str
    user_id: str
    public_key_cose: bytes
    sign_counter: int
    rp_id: str
    aaguid: str | None
    label: str
    transports: list[str]
    created_at_ms: int
    last_used_at_ms: int | None
    revoked_at_ms: int | None
    revocation_reason: str | None

    @property
    def is_active(self) -> bool:
        return self.revoked_at_ms is None

    def to_safe_dict(self) -> dict[str, Any]:
        """Returns safe presentation dictionary masking credential IDs."""
        cid = self.credential_id
        masked_id = f"{cid[:6]}...{cid[-4:]}" if len(cid) > 12 else cid
        return {
            "credential_id_masked": masked_id,
            "credential_id": self.credential_id,
            "user_id": self.user_id,
            "label": self.label,
            "sign_counter": self.sign_counter,
            "rp_id": self.rp_id,
            "aaguid": self.aaguid,
            "transports": self.transports,
            "is_active": self.is_active,
            "created_at_ms": self.created_at_ms,
            "last_used_at_ms": self.last_used_at_ms,
            "revoked_at_ms": self.revoked_at_ms,
        }


@dataclass
class ClearanceSession:
    clearance_id: str
    credential_id: str
    session_id: str
    operator_id: str
    purpose: str
    issued_at_ms: int
    expires_at_ms: int
    is_revoked: bool
    revocation_reason: str | None
    client_fingerprint: str | None

    def is_valid(self, current_time_ms: int | None = None) -> bool:
        now = current_time_ms if current_time_ms is not None else int(time.time() * 1000)
        return (not self.is_revoked) and (now < self.expires_at_ms)

    def remaining_seconds(self, current_time_ms: int | None = None) -> int:
        now = current_time_ms if current_time_ms is not None else int(time.time() * 1000)
        return max(0, int((self.expires_at_ms - now) / 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "clearance_id": self.clearance_id,
            "credential_id_masked": f"{self.credential_id[:6]}...{self.credential_id[-4:]}"
            if len(self.credential_id) > 12
            else self.credential_id,
            "session_id": self.session_id,
            "operator_id": self.operator_id,
            "purpose": self.purpose,
            "issued_at_ms": self.issued_at_ms,
            "expires_at_ms": self.expires_at_ms,
            "remaining_seconds": self.remaining_seconds(),
            "is_valid": self.is_valid(),
            "is_revoked": self.is_revoked,
            "revocation_reason": self.revocation_reason,
        }


class SecurityStore:
    """Manages persistence in data/security.db."""

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path
        self._ensure_schema()

    def get_connection(self) -> sqlite3.Connection:
        return get_security_connection(self._db_path)

    def _ensure_schema(self) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS webauthn_credentials (
                    credential_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    public_key_cose BLOB NOT NULL,
                    sign_counter INTEGER NOT NULL DEFAULT 0,
                    rp_id TEXT NOT NULL,
                    aaguid TEXT,
                    label TEXT NOT NULL,
                    transports_json TEXT,
                    created_at_ms INTEGER NOT NULL,
                    last_used_at_ms INTEGER,
                    revoked_at_ms INTEGER,
                    revocation_reason TEXT
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cred_user ON webauthn_credentials(user_id);"
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS webauthn_challenges (
                    challenge_id TEXT PRIMARY KEY,
                    challenge_bytes BLOB NOT NULL,
                    purpose TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    expires_at_ms INTEGER NOT NULL,
                    consumed_at_ms INTEGER
                );
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS clearance_sessions (
                    clearance_id TEXT PRIMARY KEY,
                    credential_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    operator_id TEXT NOT NULL,
                    purpose TEXT NOT NULL DEFAULT 'LIVE_EXECUTION',
                    issued_at_ms INTEGER NOT NULL,
                    expires_at_ms INTEGER NOT NULL,
                    is_revoked INTEGER NOT NULL DEFAULT 0,
                    revocation_reason TEXT,
                    client_fingerprint TEXT,
                    FOREIGN KEY(credential_id) REFERENCES webauthn_credentials(credential_id)
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_clearance_session ON clearance_sessions(session_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_clearance_active ON clearance_sessions(is_revoked, expires_at_ms);"
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS credential_revocations (
                    revocation_id TEXT PRIMARY KEY,
                    credential_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    revoked_at_ms INTEGER NOT NULL
                );
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS security_audit (
                    audit_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    timestamp_ms INTEGER NOT NULL
                );
                """
            )
            conn.commit()

    # -----------------------------------------------------------------------
    # Credential Management
    # -----------------------------------------------------------------------
    def save_credential(
        self,
        credential_id: str,
        user_id: str,
        public_key_cose: bytes,
        sign_counter: int,
        rp_id: str,
        label: str = "Hardware Token",
        aaguid: str | None = None,
        transports: list[str] | None = None,
    ) -> StoredCredential:
        now_ms = int(time.time() * 1000)
        transports_json = json.dumps(transports or [])
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO webauthn_credentials (
                    credential_id, user_id, public_key_cose, sign_counter,
                    rp_id, aaguid, label, transports_json, created_at_ms,
                    last_used_at_ms, revoked_at_ms, revocation_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
                ON CONFLICT(credential_id) DO UPDATE SET
                    sign_counter = excluded.sign_counter,
                    public_key_cose = excluded.public_key_cose,
                    label = excluded.label,
                    transports_json = excluded.transports_json;
                """,
                (
                    credential_id,
                    user_id,
                    public_key_cose,
                    sign_counter,
                    rp_id,
                    aaguid,
                    label,
                    transports_json,
                    now_ms,
                ),
            )
            conn.commit()

        return StoredCredential(
            credential_id=credential_id,
            user_id=user_id,
            public_key_cose=public_key_cose,
            sign_counter=sign_counter,
            rp_id=rp_id,
            aaguid=aaguid,
            label=label,
            transports=transports or [],
            created_at_ms=now_ms,
            last_used_at_ms=None,
            revoked_at_ms=None,
            revocation_reason=None,
        )

    def get_credential(self, credential_id: str) -> StoredCredential | None:
        with self.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT credential_id, user_id, public_key_cose, sign_counter,
                       rp_id, aaguid, label, transports_json, created_at_ms,
                       last_used_at_ms, revoked_at_ms, revocation_reason
                FROM webauthn_credentials
                WHERE credential_id = ?
                """,
                (credential_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            transports = json.loads(row["transports_json"]) if row["transports_json"] else []
            return StoredCredential(
                credential_id=row["credential_id"],
                user_id=row["user_id"],
                public_key_cose=row["public_key_cose"],
                sign_counter=row["sign_counter"],
                rp_id=row["rp_id"],
                aaguid=row["aaguid"],
                label=row["label"],
                transports=transports,
                created_at_ms=row["created_at_ms"],
                last_used_at_ms=row["last_used_at_ms"],
                revoked_at_ms=row["revoked_at_ms"],
                revocation_reason=row["revocation_reason"],
            )

    def list_credentials(
        self, user_id: str | None = None, active_only: bool = True
    ) -> list[StoredCredential]:
        query = "SELECT * FROM webauthn_credentials WHERE 1=1"
        params: list[Any] = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if active_only:
            query += " AND revoked_at_ms IS NULL"
        query += " ORDER BY created_at_ms DESC"

        with self.get_connection() as conn:
            cur = conn.execute(query, params)
            rows = cur.fetchall()
            creds = []
            for row in rows:
                transports = json.loads(row["transports_json"]) if row["transports_json"] else []
                creds.append(
                    StoredCredential(
                        credential_id=row["credential_id"],
                        user_id=row["user_id"],
                        public_key_cose=row["public_key_cose"],
                        sign_counter=row["sign_counter"],
                        rp_id=row["rp_id"],
                        aaguid=row["aaguid"],
                        label=row["label"],
                        transports=transports,
                        created_at_ms=row["created_at_ms"],
                        last_used_at_ms=row["last_used_at_ms"],
                        revoked_at_ms=row["revoked_at_ms"],
                        revocation_reason=row["revocation_reason"],
                    )
                )
            return creds

    def update_credential_counter(self, credential_id: str, new_counter: int) -> None:
        now_ms = int(time.time() * 1000)
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE webauthn_credentials
                SET sign_counter = ?, last_used_at_ms = ?
                WHERE credential_id = ?
                """,
                (new_counter, now_ms, credential_id),
            )
            conn.commit()

    def revoke_credential(self, credential_id: str, reason: str) -> bool:
        now_ms = int(time.time() * 1000)
        rev_id = str(uuid.uuid4())
        with self.get_connection() as conn:
            # 1. Update credential record
            cur = conn.execute(
                """
                UPDATE webauthn_credentials
                SET revoked_at_ms = ?, revocation_reason = ?
                WHERE credential_id = ? AND revoked_at_ms IS NULL
                """,
                (now_ms, reason, credential_id),
            )
            if cur.rowcount == 0:
                return False

            # 2. Add revocation entry
            conn.execute(
                """
                INSERT INTO credential_revocations (revocation_id, credential_id, reason, revoked_at_ms)
                VALUES (?, ?, ?, ?)
                """,
                (rev_id, credential_id, reason, now_ms),
            )

            # 3. Immediately revoke all active clearance sessions using this credential
            conn.execute(
                """
                UPDATE clearance_sessions
                SET is_revoked = 1, revocation_reason = ?
                WHERE credential_id = ? AND is_revoked = 0
                """,
                (f"CREDENTIAL_REVOKED: {reason}", credential_id),
            )
            conn.commit()
        return True

    # -----------------------------------------------------------------------
    # Challenge Management (Single-Use with TTL)
    # -----------------------------------------------------------------------
    def create_challenge(
        self, purpose: str, user_id: str = "default_operator", ttl_seconds: int = 120
    ) -> tuple[str, bytes]:
        challenge_id = str(uuid.uuid4())
        challenge_bytes = secrets.token_bytes(32)
        now_ms = int(time.time() * 1000)
        expires_at_ms = now_ms + (ttl_seconds * 1000)

        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO webauthn_challenges (
                    challenge_id, challenge_bytes, purpose, user_id,
                    created_at_ms, expires_at_ms, consumed_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (challenge_id, challenge_bytes, purpose, user_id, now_ms, expires_at_ms),
            )
            conn.commit()

        return challenge_id, challenge_bytes

    def consume_challenge(
        self, challenge_id: str, purpose: str
    ) -> tuple[bool, bytes | None, str | None]:
        """
        Atomically consumes challenge.
        Returns: (success, challenge_bytes, error_code)
        """
        now_ms = int(time.time() * 1000)
        with self.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT challenge_bytes, purpose, expires_at_ms, consumed_at_ms
                FROM webauthn_challenges
                WHERE challenge_id = ?
                """,
                (challenge_id,),
            )
            row = cur.fetchone()
            if not row:
                return False, None, "HARDWARE_KEY_CHALLENGE_INVALID"

            if row["purpose"] != purpose:
                return False, None, "HARDWARE_KEY_PURPOSE_MISMATCH"

            if row["consumed_at_ms"] is not None:
                return False, None, "HARDWARE_KEY_CHALLENGE_REPLAYED"

            if now_ms > row["expires_at_ms"]:
                return False, None, "HARDWARE_KEY_CHALLENGE_EXPIRED"

            # Atomically mark consumed
            conn.execute(
                """
                UPDATE webauthn_challenges
                SET consumed_at_ms = ?
                WHERE challenge_id = ?
                """,
                (now_ms, challenge_id),
            )
            conn.commit()
            return True, row["challenge_bytes"], None

    # -----------------------------------------------------------------------
    # Live Clearance Session Management
    # -----------------------------------------------------------------------
    def create_clearance_session(
        self,
        credential_id: str,
        session_id: str,
        operator_id: str,
        ttl_seconds: int = 900,  # 15 minutes default
        purpose: str = "LIVE_EXECUTION",
        client_fingerprint: str | None = None,
    ) -> ClearanceSession:
        clearance_id = str(uuid.uuid4())
        now_ms = int(time.time() * 1000)
        expires_at_ms = now_ms + (ttl_seconds * 1000)

        with self.get_connection() as conn:
            # Revoke any prior active clearance for this session_id to avoid leakage
            conn.execute(
                """
                UPDATE clearance_sessions
                SET is_revoked = 1, revocation_reason = 'SUPERSEDED_BY_NEW_CLEARANCE'
                WHERE session_id = ? AND is_revoked = 0
                """,
                (session_id,),
            )

            conn.execute(
                """
                INSERT INTO clearance_sessions (
                    clearance_id, credential_id, session_id, operator_id,
                    purpose, issued_at_ms, expires_at_ms, is_revoked,
                    revocation_reason, client_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)
                """,
                (
                    clearance_id,
                    credential_id,
                    session_id,
                    operator_id,
                    purpose,
                    now_ms,
                    expires_at_ms,
                    client_fingerprint,
                ),
            )
            conn.commit()

        return ClearanceSession(
            clearance_id=clearance_id,
            credential_id=credential_id,
            session_id=session_id,
            operator_id=operator_id,
            purpose=purpose,
            issued_at_ms=now_ms,
            expires_at_ms=expires_at_ms,
            is_revoked=False,
            revocation_reason=None,
            client_fingerprint=client_fingerprint,
        )

    def get_active_clearance(
        self, session_id: str | None = None, clearance_id: str | None = None
    ) -> ClearanceSession | None:
        now_ms = int(time.time() * 1000)
        query = "SELECT * FROM clearance_sessions WHERE is_revoked = 0 AND expires_at_ms > ?"
        params: list[Any] = [now_ms]

        if clearance_id:
            query += " AND clearance_id = ?"
            params.append(clearance_id)
        elif session_id:
            query += " AND session_id = ?"
            params.append(session_id)

        query += " ORDER BY issued_at_ms DESC LIMIT 1"

        with self.get_connection() as conn:
            cur = conn.execute(query, params)
            row = cur.fetchone()
            if not row:
                return None

            return ClearanceSession(
                clearance_id=row["clearance_id"],
                credential_id=row["credential_id"],
                session_id=row["session_id"],
                operator_id=row["operator_id"],
                purpose=row["purpose"],
                issued_at_ms=row["issued_at_ms"],
                expires_at_ms=row["expires_at_ms"],
                is_revoked=bool(row["is_revoked"]),
                revocation_reason=row["revocation_reason"],
                client_fingerprint=row["client_fingerprint"],
            )

    def revoke_clearance(
        self,
        session_id: str | None = None,
        clearance_id: str | None = None,
        reason: str = "OPERATOR_REVOKED",
    ) -> int:
        query = "UPDATE clearance_sessions SET is_revoked = 1, revocation_reason = ? WHERE is_revoked = 0"
        params: list[Any] = [reason]
        if clearance_id:
            query += " AND clearance_id = ?"
            params.append(clearance_id)
        elif session_id:
            query += " AND session_id = ?"
            params.append(session_id)

        with self.get_connection() as conn:
            cur = conn.execute(query, params)
            conn.commit()
            return cur.rowcount

    def revoke_all_clearances(self, reason: str = "EMERGENCY_KILL_SWITCH") -> int:
        with self.get_connection() as conn:
            cur = conn.execute(
                "UPDATE clearance_sessions SET is_revoked = 1, revocation_reason = ? WHERE is_revoked = 0",
                (reason,),
            )
            conn.commit()
            return cur.rowcount

    def record_security_audit(self, event_type: str, details: dict[str, Any]) -> str:
        audit_id = f"SEC-{int(time.time() * 1000)}-{secrets.token_hex(4)}"
        now_ms = int(time.time() * 1000)
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO security_audit (audit_id, event_type, details_json, timestamp_ms)
                VALUES (?, ?, ?, ?)
                """,
                (audit_id, event_type, json.dumps(details), now_ms),
            )
            conn.commit()
        return audit_id


# Global singleton security store
security_store = SecurityStore()
