"""
core/auth/hardware_key.py
=========================
FIDO2 / WebAuthn Hardware Security Key Manager & Live Execution Clearance Engine.

Governance Classification: CLASS H (LIVE / PAPER BOUNDARY)
=============================================================================
CRITICAL ARCHITECTURAL INVARIANT:
Hardware security key verification authorizes a TEMPORARY LIVE CLEARANCE SESSION.
It DOES NOT directly authorize an individual order. Every order must still
independently clear all deterministic risk gates, position sizing bounds,
portfolio heat limits, and the master kill switch.

WebAuthn Correctness Invariants:
- W3C Level 3 standard protocol verification via `webauthn` library.
- Single-use challenge binding (atomic consumption prevents replay).
- Strict Origin and RP ID / RP ID Hash validation.
- User Presence (UP) enforcement; User Verification (UV) per policy.
- WebAuthn-compliant counter semantics: allows zero-counter authenticators,
  detects counter rollbacks as potential cloning attacks.
- Dedicated `security.db` isolation: zero private keys stored or logged.
- Safe metadata-only audit emission to `audit_bus`.
=============================================================================
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.base64url_to_bytes import base64url_to_bytes
from webauthn.helpers.bytes_to_base64url import bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
)

from core.audit_bus import audit_bus
from core.auth.security_store import (
    ClearanceSession,
    DaemonLease,
    SecurityStore,
    StoredCredential,
    security_store,
)

logger = logging.getLogger("sky.auth.hardware_key")

DEFAULT_RP_ID = os.getenv("WEBAUTHN_RP_ID", "127.0.0.1")
DEFAULT_RP_NAME = os.getenv("WEBAUTHN_RP_NAME", "Crypto Brain Terminal (CBT)")
DEFAULT_ALLOWED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://localhost",
    "http://127.0.0.1",
    "app://ctb-terminal",
]
if os.getenv("WEBAUTHN_ORIGIN"):
    DEFAULT_ALLOWED_ORIGINS.extend(
        [orig.strip() for orig in os.getenv("WEBAUTHN_ORIGIN", "").split(",") if orig.strip()]
    )

CLEARANCE_TTL_SECONDS = int(os.getenv("LIVE_CLEARANCE_TTL_SECONDS", "900"))  # 15 minutes


class HardwareKeyError(Exception):
    """Base exception for hardware security key errors."""


class HardwareKeyChallengeError(HardwareKeyError):
    """Raised when a challenge is missing, expired, or replayed."""


class HardwareKeyAssertionError(HardwareKeyError):
    """Raised when WebAuthn assertion verification fails."""


class HardwareKeyCounterAnomalyError(HardwareKeyError):
    """Raised when authenticator counter rollback indicates potential cloning attack."""


class HardwareKeyRevokedError(HardwareKeyError):
    """Raised when an operation targets a revoked credential."""


def get_host_fingerprint() -> str:
    """Computes deterministic host machine fingerprint for daemon lease binding."""
    import hashlib
    import platform
    import socket

    raw = f"{socket.gethostname()}_{platform.node()}_{platform.machine()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class HardwareKeyManager:
    """Authoritative FIDO2 / WebAuthn Hardware Security Key Manager."""

    def __init__(
        self,
        store: SecurityStore | None = None,
        rp_id: str = DEFAULT_RP_ID,
        rp_name: str = DEFAULT_RP_NAME,
        allowed_origins: list[str] | None = None,
        clearance_ttl_seconds: int = CLEARANCE_TTL_SECONDS,
        require_user_verification: bool = False,
    ):
        self.store = store or security_store
        self.rp_id = rp_id
        self.rp_name = rp_name
        self.allowed_origins = allowed_origins or list(DEFAULT_ALLOWED_ORIGINS)
        self.clearance_ttl_seconds = clearance_ttl_seconds
        self.require_user_verification = require_user_verification

    # -----------------------------------------------------------------------
    # Registration Ceremony
    # -----------------------------------------------------------------------
    def get_registration_options(
        self,
        user_id: str = "default_operator",
        username: str = "operator",
        display_name: str = "CBT Operator",
    ) -> dict[str, Any]:
        """Generates WebAuthn registration options with a durable single-use challenge."""
        challenge_id, challenge_bytes = self.store.create_challenge(
            purpose="REGISTRATION", user_id=user_id, ttl_seconds=120
        )

        existing_creds = self.store.list_credentials(user_id=user_id, active_only=True)
        exclude_credentials = [
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
            for c in existing_creds
        ]

        options = generate_registration_options(
            rp_id=self.rp_id,
            rp_name=self.rp_name,
            user_id=user_id.encode("utf-8"),
            user_name=username,
            user_display_name=display_name,
            challenge=challenge_bytes,
            exclude_credentials=exclude_credentials if exclude_credentials else None,
            authenticator_selection=AuthenticatorSelectionCriteria(
                user_verification=UserVerificationRequirement.PREFERRED
            ),
        )

        options_json_str = options_to_json(options)
        options_dict = json.loads(options_json_str)

        try:
            audit_bus.emit_event(
                event_type="FIDO2_REGISTRATION_INIT",
                symbol="SECURITY",
                reason=f"WebAuthn registration challenge generated for user '{user_id}'",
                severity="INFO",
                details={"challenge_id": challenge_id, "user_id": user_id, "rp_id": self.rp_id},
            )
        except Exception as exc:
            logger.debug(f"Audit bus logging error: {exc}")

        return {
            "challenge_id": challenge_id,
            "options": options_dict,
        }

    def verify_registration(
        self,
        challenge_id: str,
        credential_data: dict[str, Any] | str,
        label: str = "Hardware Key",
        user_id: str = "default_operator",
    ) -> StoredCredential:
        """Verifies WebAuthn registration response and records new credential."""
        success, challenge_bytes, error_code = self.store.consume_challenge(
            challenge_id, purpose="REGISTRATION"
        )
        if not success or challenge_bytes is None:
            raise HardwareKeyChallengeError(error_code or "HARDWARE_KEY_CHALLENGE_INVALID")

        try:
            verified_reg = verify_registration_response(
                credential=credential_data,
                expected_challenge=challenge_bytes,
                expected_rp_id=self.rp_id,
                expected_origin=self.allowed_origins,
                require_user_presence=True,
                require_user_verification=self.require_user_verification,
            )
        except InvalidRegistrationResponse as exc:
            logger.warning(f"FIDO2 registration verification failed: {exc}")
            try:
                audit_bus.emit_event(
                    event_type="FIDO2_REGISTRATION_FAILED",
                    symbol="SECURITY",
                    reason=f"Registration verification failed: {exc}",
                    severity="WARNING",
                    details={"challenge_id": challenge_id, "user_id": user_id},
                )
            except Exception as log_err:
                logger.debug("Failed to record incident: %s", log_err)
            raise HardwareKeyAssertionError(f"HARDWARE_KEY_REGISTRATION_INVALID: {exc}") from exc

        credential_id_b64 = bytes_to_base64url(verified_reg.credential_id)
        aaguid_str = str(verified_reg.aaguid) if verified_reg.aaguid else None

        stored_cred = self.store.save_credential(
            credential_id=credential_id_b64,
            user_id=user_id,
            public_key_cose=verified_reg.credential_public_key,
            sign_counter=verified_reg.sign_count,
            rp_id=self.rp_id,
            label=label,
            aaguid=aaguid_str,
        )

        try:
            audit_bus.emit_event(
                event_type="FIDO2_CREDENTIAL_REGISTERED",
                symbol="SECURITY",
                reason=f"New FIDO2 credential enrolled: {stored_cred.to_safe_dict()['credential_id_masked']}",
                severity="INFO",
                details={
                    "credential_id_masked": stored_cred.to_safe_dict()["credential_id_masked"],
                    "label": label,
                    "user_id": user_id,
                    "rp_id": self.rp_id,
                    "sign_count": verified_reg.sign_count,
                },
            )
        except Exception as exc:
            logger.debug(f"Audit bus logging error: {exc}")

        return stored_cred

    # -----------------------------------------------------------------------
    # Authentication & Live Clearance Ceremony
    # -----------------------------------------------------------------------
    def get_authentication_options(self, user_id: str | None = None) -> dict[str, Any]:
        """Generates WebAuthn assertion challenge for Live Execution Clearance."""
        challenge_id, challenge_bytes = self.store.create_challenge(
            purpose="AUTHENTICATION", user_id=user_id or "default_operator", ttl_seconds=120
        )

        creds = self.store.list_credentials(user_id=user_id, active_only=True)
        if not creds:
            raise HardwareKeyRevokedError(
                "HARDWARE_KEY_NO_CREDENTIALS: No active hardware security keys registered. Enrollment required."
            )

        allow_credentials = [
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id)) for c in creds
        ]

        options = generate_authentication_options(
            rp_id=self.rp_id,
            challenge=challenge_bytes,
            allow_credentials=allow_credentials,
            user_verification=UserVerificationRequirement.PREFERRED,
        )

        options_json_str = options_to_json(options)
        options_dict = json.loads(options_json_str)

        try:
            audit_bus.emit_event(
                event_type="FIDO2_AUTHENTICATION_INIT",
                symbol="SECURITY",
                reason="Live clearance challenge generated",
                severity="INFO",
                details={"challenge_id": challenge_id, "rp_id": self.rp_id},
            )
        except Exception as exc:
            logger.debug(f"Audit bus logging error: {exc}")

        return {
            "challenge_id": challenge_id,
            "options": options_dict,
        }

    def verify_authentication_and_issue_clearance(
        self,
        challenge_id: str,
        credential_data: dict[str, Any] | str,
        session_id: str,
        operator_id: str = "default_operator",
        client_fingerprint: str | None = None,
    ) -> ClearanceSession:
        """
        Verifies assertion from physical security key and issues a short-lived Live Clearance Session.
        Enforces counter semantics and replay protection.
        """
        success, challenge_bytes, error_code = self.store.consume_challenge(
            challenge_id, purpose="AUTHENTICATION"
        )
        if not success or challenge_bytes is None:
            raise HardwareKeyChallengeError(error_code or "HARDWARE_KEY_CHALLENGE_INVALID")

        # Parse credential ID from response payload
        if isinstance(credential_data, str):
            try:
                cred_dict = json.loads(credential_data)
            except Exception as exc:
                raise HardwareKeyAssertionError("Malformed credential JSON") from exc
        else:
            cred_dict = credential_data

        raw_id_b64 = cred_dict.get("id") or cred_dict.get("rawId")
        if not raw_id_b64:
            raise HardwareKeyAssertionError(
                "HARDWARE_KEY_CREDENTIAL_ID_MISSING: Missing credential id"
            )

        stored_cred = self.store.get_credential(raw_id_b64)
        if not stored_cred:
            raise HardwareKeyAssertionError(
                "HARDWARE_KEY_UNKNOWN_CREDENTIAL: Presented credential not found in security database"
            )
        if not stored_cred.is_active:
            raise HardwareKeyRevokedError(
                f"HARDWARE_KEY_CREDENTIAL_REVOKED: Key was revoked: {stored_cred.revocation_reason}"
            )

        try:
            verified_auth = verify_authentication_response(
                credential=credential_data,
                expected_challenge=challenge_bytes,
                expected_rp_id=self.rp_id,
                expected_origin=self.allowed_origins,
                credential_public_key=stored_cred.public_key_cose,
                credential_current_sign_count=stored_cred.sign_counter,
                require_user_verification=self.require_user_verification,
            )
        except InvalidAuthenticationResponse as exc:
            err_msg = str(exc)
            logger.warning(f"FIDO2 authentication verification failed: {err_msg}")
            # Detect counter anomaly explicitly
            if "Response sign count of" in err_msg and "was not greater than" in err_msg:
                try:
                    audit_bus.emit_event(
                        event_type="FIDO2_COUNTER_ANOMALY_DETECTED",
                        symbol="SECURITY",
                        reason=f"Cloned token / replay detected: {err_msg}",
                        severity="CRITICAL",
                        details={
                            "credential_id_masked": stored_cred.to_safe_dict()[
                                "credential_id_masked"
                            ],
                            "stored_counter": stored_cred.sign_counter,
                        },
                    )
                except Exception as log_err:
                    logger.debug("Failed to record incident: %s", log_err)
                raise HardwareKeyCounterAnomalyError(
                    f"HARDWARE_KEY_COUNTER_ANOMALY: {err_msg}"
                ) from exc

            try:
                audit_bus.emit_event(
                    event_type="FIDO2_ASSERTION_FAILED",
                    symbol="SECURITY",
                    reason=f"Assertion failed: {err_msg}",
                    severity="WARNING",
                    details={
                        "credential_id_masked": stored_cred.to_safe_dict()["credential_id_masked"],
                        "challenge_id": challenge_id,
                    },
                )
            except Exception as log_err:
                logger.debug("Failed to record incident: %s", log_err)
            raise HardwareKeyAssertionError(f"HARDWARE_KEY_ASSERTION_INVALID: {err_msg}") from exc

        # Update counter
        self.store.update_credential_counter(
            credential_id=stored_cred.credential_id, new_counter=verified_auth.new_sign_count
        )

        # Issue Live Clearance Session
        clearance = self.store.create_clearance_session(
            credential_id=stored_cred.credential_id,
            session_id=session_id,
            operator_id=operator_id,
            ttl_seconds=self.clearance_ttl_seconds,
            purpose="LIVE_EXECUTION",
            client_fingerprint=client_fingerprint,
        )

        try:
            audit_bus.emit_event(
                event_type="FIDO2_LIVE_CLEARANCE_GRANTED",
                symbol="SECURITY",
                reason=(
                    f"Physical key verified for operator '{operator_id}'. "
                    f"Live clearance active for {self.clearance_ttl_seconds}s."
                ),
                severity="INFO",
                details={
                    "clearance_id": clearance.clearance_id,
                    "session_id": session_id,
                    "operator_id": operator_id,
                    "credential_id_masked": stored_cred.to_safe_dict()["credential_id_masked"],
                    "expires_at_ms": clearance.expires_at_ms,
                    "ttl_seconds": self.clearance_ttl_seconds,
                    "user_verified": verified_auth.user_verified,
                },
            )
        except Exception as exc:
            logger.debug(f"Audit bus logging error: {exc}")

        return clearance

    # -----------------------------------------------------------------------
    # Verification & Querying
    # -----------------------------------------------------------------------
    def check_live_clearance(
        self,
        session_id: str | None = None,
        tier: str | None = None,
        is_autonomous: bool = False,
    ) -> tuple[bool, ClearanceSession | DaemonLease | None, str | None]:
        """
        Checks if an active, valid Live Clearance Session or Daemon Lease exists.
        For unattended daemon runs in Tier 1 (Canary) or Tier 2 (Micro Live),
        allows validation via cryptographic Daemon Lease.
        Returns: (is_cleared, clearance_or_lease, error_reason_code)
        """
        # 1. Autonomous execution under Tier 1/2 can use active Daemon Lease
        if is_autonomous and tier in ("TIER_1_CANARY", "TIER_2_MICRO_LIVE"):
            is_leased, lease, reason = self.check_daemon_lease(tier=tier)
            if is_leased and lease is not None:
                return True, lease, None
            # If daemon lease not found/invalid and session_id not provided, return lease reason
            if not session_id:
                return False, None, reason or "DAEMON_LEASE_REQUIRED"

        # 2. Interactive session or Tier 3/4 requires physical clearance session
        clearance = self.store.get_active_clearance(session_id=session_id)
        if not clearance:
            active_creds = self.store.list_credentials(active_only=True)
            if not active_creds:
                return False, None, "HARDWARE_KEY_NO_CREDENTIALS"
            return False, None, "HARDWARE_KEY_CLEARANCE_REQUIRED"

        if not clearance.is_valid():
            if clearance.is_revoked:
                return (
                    False,
                    clearance,
                    f"HARDWARE_KEY_CREDENTIAL_REVOKED: {clearance.revocation_reason}",
                )
            return False, clearance, "HARDWARE_KEY_CLEARANCE_EXPIRED"

        if clearance.purpose != "LIVE_EXECUTION":
            return False, clearance, f"HARDWARE_KEY_PURPOSE_MISMATCH: {clearance.purpose}"

        return True, clearance, None

    def create_daemon_lease(
        self,
        credential_id: str,
        operator_id: str = "default_operator",
        tier_cap: str = "TIER_1_CANARY",
        max_daily_loss_pct: float = 0.03,
        ttl_seconds: int = 86400,
        pid: int | None = None,
        host_fingerprint: str | None = None,
    ) -> DaemonLease:
        """Issues a cryptographic Operator Daemon Lease bound to PID, host, and tier cap."""
        import hashlib

        target_pid = pid or os.getpid()
        target_fp = host_fingerprint or get_host_fingerprint()

        stored_cred = self.store.get_credential(credential_id)
        if not stored_cred or not stored_cred.is_active:
            raise HardwareKeyRevokedError(
                "HARDWARE_KEY_CREDENTIAL_REVOKED: Cannot lease revoked credential"
            )

        sig_payload = f"{credential_id}:{operator_id}:{target_pid}:{target_fp}:{tier_cap}:{max_daily_loss_pct}"
        sig_digest = hashlib.sha256(sig_payload.encode()).hexdigest()

        lease = self.store.create_daemon_lease(
            credential_id=credential_id,
            operator_id=operator_id,
            pid=target_pid,
            host_fingerprint=target_fp,
            tier_cap=tier_cap,
            max_daily_loss_pct=max_daily_loss_pct,
            ttl_seconds=ttl_seconds,
            signature_digest=sig_digest,
        )
        try:
            audit_bus.emit_event(
                event_type="FIDO2_DAEMON_LEASE_ISSUED",
                symbol="SECURITY",
                reason=f"Cryptographic Daemon Lease issued for PID {target_pid} at tier {tier_cap}",
                severity="INFO",
                details=lease.to_dict(),
            )
        except Exception as exc:
            logger.debug(f"Audit bus logging error: {exc}")
        return lease

    def check_daemon_lease(
        self,
        tier: str = "TIER_1_CANARY",
        pid: int | None = None,
        host_fingerprint: str | None = None,
    ) -> tuple[bool, DaemonLease | None, str | None]:
        """Validates whether an active cryptographic Daemon Lease is valid for current process and tier."""
        target_pid = pid or os.getpid()
        target_fp = host_fingerprint or get_host_fingerprint()
        lease = self.store.get_latest_daemon_lease(pid=target_pid, host_fingerprint=target_fp)
        if not lease:
            return False, None, "DAEMON_LEASE_NOT_FOUND"

        if not lease.is_valid():
            if lease.is_revoked:
                return False, lease, f"DAEMON_LEASE_REVOKED: {lease.revocation_reason}"
            return False, lease, "DAEMON_LEASE_EXPIRED"

        allowed_tiers = ["TIER_1_CANARY", "TIER_2_MICRO_LIVE"]
        if tier not in allowed_tiers:
            return (
                False,
                lease,
                f"DAEMON_LEASE_TIER_EXCEEDED: Tier {tier} requires physical FIDO2 tap",
            )

        if lease.tier_cap == "TIER_1_CANARY" and tier == "TIER_2_MICRO_LIVE":
            return False, lease, "DAEMON_LEASE_TIER_CAP_EXCEEDED: Lease capped at TIER_1_CANARY"

        return True, lease, None

    def revoke_all_daemon_leases(self, reason: str = "EMERGENCY_KILL_SWITCH") -> int:
        """Irrevocably revokes all active daemon leases in memory and durable storage."""
        count = self.store.revoke_all_daemon_leases(reason=reason)
        try:
            audit_bus.emit_event(
                event_type="FIDO2_DAEMON_LEASES_REVOKED",
                symbol="SECURITY",
                reason=f"All active daemon leases revoked: {reason}",
                severity="WARNING",
                details={"reason": reason, "revoked_count": count},
            )
        except Exception as exc:
            logger.debug(f"Audit bus logging error: {exc}")
        return count

    def revoke_clearance(
        self, session_id: str | None = None, reason: str = "OPERATOR_REVOKED"
    ) -> int:
        count = self.store.revoke_clearance(session_id=session_id, reason=reason)
        try:
            audit_bus.emit_event(
                event_type="FIDO2_CLEARANCE_REVOKED",
                symbol="SECURITY",
                reason=f"Live clearance revoked for session: {session_id or 'all'}. Reason: {reason}",
                severity="WARNING",
                details={"session_id": session_id, "reason": reason},
            )
        except Exception as exc:
            logger.debug(f"Audit bus logging error: {exc}")
        return count

    def revoke_credential(self, credential_id: str, reason: str = "OPERATOR_REVOKED") -> bool:
        success = self.store.revoke_credential(credential_id, reason=reason)
        if success:
            try:
                masked = (
                    f"{credential_id[:6]}...{credential_id[-4:]}"
                    if len(credential_id) > 12
                    else credential_id
                )
                audit_bus.emit_event(
                    event_type="FIDO2_CREDENTIAL_REVOKED",
                    symbol="SECURITY",
                    reason=f"Hardware key credential {masked} revoked. All active clearances invalidated.",
                    severity="CRITICAL",
                    details={"credential_id_masked": masked, "reason": reason},
                )
            except Exception as exc:
                logger.debug(f"Audit bus logging error: {exc}")
        return success

    def get_security_posture(self, session_id: str | None = None) -> dict[str, Any]:
        """Returns non-sensitive security overview for dashboard / terminal HUD."""
        creds = self.store.list_credentials(active_only=True)
        is_cleared, active_clearance, reason_code = self.check_live_clearance(session_id=session_id)
        return {
            "webauthn_enabled": True,
            "registered_keys_count": len(creds),
            "credentials": [c.to_safe_dict() for c in creds],
            "live_clearance_active": is_cleared,
            "clearance_session": active_clearance.to_dict() if active_clearance else None,
            "rejection_reason_code": reason_code,
            "policy": {
                "rp_id": self.rp_id,
                "ttl_seconds": self.clearance_ttl_seconds,
                "user_verification_required": self.require_user_verification,
            },
        }


# Global singleton manager
hardware_key_manager = HardwareKeyManager()
