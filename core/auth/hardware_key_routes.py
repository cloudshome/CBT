"""
core/auth/hardware_key_routes.py
================================
FastAPI REST API Routes for WebAuthn / FIDO2 Hardware Key Management & Live Clearance.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from core.auth import require_api_key
from core.auth.hardware_key import (
    HardwareKeyAssertionError,
    HardwareKeyChallengeError,
    HardwareKeyCounterAnomalyError,
    HardwareKeyRevokedError,
    hardware_key_manager,
)

logger = logging.getLogger("sky.auth.hardware_key_routes")

hardware_key_router = APIRouter(
    prefix="/api/auth/hardware-key", tags=["Hardware Security Key & Live Clearance"]
)


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------
class RegisterOptionsRequest(BaseModel):
    user_id: str = Field(default="default_operator", description="Operator User ID")
    username: str = Field(default="operator", description="Operator username")
    display_name: str = Field(default="CBT Institutional Operator", description="Display name")


class RegisterVerifyRequest(BaseModel):
    challenge_id: str = Field(..., description="Challenge ID issued by /register/options")
    credential: dict[str, Any] = Field(
        ..., description="RegistrationCredential JSON from navigator.credentials.create"
    )
    label: str = Field(
        default="YubiKey / Hardware Token", description="Human-readable device label"
    )
    user_id: str = Field(default="default_operator", description="Operator User ID")


class AuthenticateOptionsRequest(BaseModel):
    user_id: str | None = Field(default=None, description="Optional User ID")


class AuthenticateVerifyRequest(BaseModel):
    challenge_id: str = Field(..., description="Challenge ID issued by /authenticate/options")
    credential: dict[str, Any] = Field(
        ..., description="AuthenticationCredential JSON from navigator.credentials.get"
    )
    session_id: str = Field(
        default="desktop_session", description="Unique client session ID to bind clearance to"
    )
    operator_id: str = Field(default="default_operator", description="Operator identity")


class RevokeClearanceRequest(BaseModel):
    session_id: str | None = Field(default=None, description="Session ID to revoke")
    clearance_id: str | None = Field(default=None, description="Specific clearance ID to revoke")
    reason: str = Field(default="OPERATOR_MANUAL_REVOCATION", description="Reason for revocation")


class RevokeCredentialRequest(BaseModel):
    credential_id: str = Field(..., description="Credential ID to permanently revoke")
    reason: str = Field(
        default="OPERATOR_REVOKED_TOKEN", description="Reason for credential revocation"
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@hardware_key_router.get("/status")
async def get_hardware_key_status(session_id: str = Query("desktop_session")):
    """Returns security posture, registered hardware keys count, and live clearance status."""
    return {
        "status": "SUCCESS",
        "posture": hardware_key_manager.get_security_posture(session_id=session_id),
    }


@hardware_key_router.post("/register/options")
async def get_registration_options_endpoint(req: RegisterOptionsRequest):
    """Issues WebAuthn registration options with single-use challenge."""
    try:
        res = hardware_key_manager.get_registration_options(
            user_id=req.user_id,
            username=req.username,
            display_name=req.display_name,
        )
        return {
            "status": "SUCCESS",
            "challenge_id": res["challenge_id"],
            "options": res["options"],
        }
    except Exception as exc:
        logger.error(f"Failed to generate registration options: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "REGISTRATION_OPTIONS_ERROR", "message": str(exc)},
        ) from exc


@hardware_key_router.post("/register/verify")
async def verify_registration_endpoint(req: RegisterVerifyRequest):
    """Verifies WebAuthn attestation response and stores credential in security.db."""
    try:
        stored = hardware_key_manager.verify_registration(
            challenge_id=req.challenge_id,
            credential_data=req.credential,
            label=req.label,
            user_id=req.user_id,
        )
        return {
            "status": "SUCCESS",
            "message": f"Hardware security key '{req.label}' enrolled successfully.",
            "credential": stored.to_safe_dict(),
        }
    except HardwareKeyChallengeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "CHALLENGE_INVALID", "message": str(exc)},
        ) from exc
    except HardwareKeyAssertionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "ATTESTATION_INVALID", "message": str(exc)},
        ) from exc
    except Exception as exc:
        logger.error(f"Unexpected error during registration verification: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "REGISTRATION_FAILED", "message": str(exc)},
        ) from exc


@hardware_key_router.post("/authenticate/options")
async def get_authentication_options_endpoint(req: AuthenticateOptionsRequest):
    """Issues WebAuthn assertion challenge for Live Execution Clearance."""
    try:
        res = hardware_key_manager.get_authentication_options(user_id=req.user_id)
        return {
            "status": "SUCCESS",
            "challenge_id": res["challenge_id"],
            "options": res["options"],
        }
    except HardwareKeyRevokedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "NO_CREDENTIALS", "message": str(exc)},
        ) from exc
    except Exception as exc:
        logger.error(f"Failed to generate authentication options: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "AUTHENTICATION_OPTIONS_ERROR", "message": str(exc)},
        ) from exc


@hardware_key_router.post("/authenticate/verify")
async def verify_authentication_endpoint(req: AuthenticateVerifyRequest, request: Request):
    """
    Verifies physical key touch and issues a session-bound Live Clearance Session.
    Enforces anti-cloning counter semantics.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "ctb-desktop")
    fingerprint = f"{client_ip}:{user_agent[:32]}"

    try:
        clearance = hardware_key_manager.verify_authentication_and_issue_clearance(
            challenge_id=req.challenge_id,
            credential_data=req.credential,
            session_id=req.session_id,
            operator_id=req.operator_id,
            client_fingerprint=fingerprint,
        )
        return {
            "status": "SUCCESS",
            "message": "Physical hardware key verified. Live Execution Clearance granted.",
            "clearance": clearance.to_dict(),
        }
    except HardwareKeyCounterAnomalyError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "HARDWARE_KEY_COUNTER_ANOMALY", "message": str(exc)},
        ) from exc
    except HardwareKeyChallengeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "CHALLENGE_INVALID", "message": str(exc)},
        ) from exc
    except HardwareKeyRevokedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "CREDENTIAL_REVOKED", "message": str(exc)},
        ) from exc
    except HardwareKeyAssertionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "ASSERTION_INVALID", "message": str(exc)},
        ) from exc
    except Exception as exc:
        logger.error(f"Unexpected error during clearance verification: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "VERIFICATION_FAILED", "message": str(exc)},
        ) from exc


@hardware_key_router.post("/clearance/revoke")
async def revoke_clearance_endpoint(req: RevokeClearanceRequest):
    """Revokes active Live Clearance session immediately."""
    count = hardware_key_manager.revoke_clearance(
        session_id=req.session_id,
        reason=req.reason,
    )
    return {
        "status": "SUCCESS",
        "action": "CLEARANCE_REVOKED",
        "message": f"Revoked {count} active clearance session(s).",
        "revoked_count": count,
    }


@hardware_key_router.post("/credential/revoke", dependencies=[Depends(require_api_key)])
async def revoke_credential_endpoint(req: RevokeCredentialRequest):
    """Permanently revokes a registered hardware security key."""
    success = hardware_key_manager.revoke_credential(
        credential_id=req.credential_id,
        reason=req.reason,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "CREDENTIAL_NOT_FOUND",
                "message": "Credential not found or already revoked.",
            },
        )
    return {
        "status": "SUCCESS",
        "message": f"Credential {req.credential_id[:6]}... successfully revoked.",
        "revoked": True,
    }
