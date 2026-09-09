"""
core/auth/credential_vault.py
=============================
AES-256-GCM Authenticated Private API Credential Vault.

Security Invariants:
- 256-bit encryption key with AES-256-GCM AEAD authenticated encryption.
- 12-byte randomized cryptographically secure nonce per encryption.
- Tampering or bit-flipping triggers mandatory authentication tag verification failure.
- Master key derived via PBKDF2-HMAC-SHA256 (600,000 iterations, 16-byte random salt)
  or directly from 256-bit VAULT_MASTER_KEY environment variable.
- Plaintext secrets are NEVER persisted to disk or emitted in logs/tracebacks.
- Centralized sanitization masks all secrets (mask_secret("abcdef123456") -> "abcd...3456").
- In-memory note: Python immutable strings (str) cannot be physically zeroed in memory;
  bytearray buffers are zeroized where mutable representations are used.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.database import db_manager

logger = logging.getLogger("sky.credential_vault")

PBKDF2_ITERATIONS = 600_000
NONCE_LENGTH_BYTES = 12
SALT_LENGTH_BYTES = 16
KEY_LENGTH_BYTES = 32

# Centralized regex patterns for redacting credentials from logs and error strings
SECRET_PATTERNS = [
    re.compile(
        r"(?i)(api[_-]?secret|api[_-]?key|secret|password|signature|private[_-]?key|token)\s*[:=]\s*['\"]?([^'\"&\s,]+)['\"]?"
    ),
    re.compile(
        r"(?i)(X-MBX-APIKEY|X-BAPI-API-KEY|X-BAPI-SIGN|Authorization)\s*[:=]\s*['\"]?([^'\"&\s,]+)['\"]?"
    ),
    re.compile(r"(?i)(signature=)([a-f0-9]{64})"),
]


class VaultError(Exception):
    """Base exception for Credential Vault errors."""


class VaultIntegrityError(VaultError):
    """Raised when ciphertext tampering or authentication tag validation fails."""


class VaultDecryptionError(VaultError):
    """Raised when decryption fails due to invalid key or corrupted payload."""


class VaultConfigurationError(VaultError):
    """Raised when vault master key is missing or misconfigured in production."""


def mask_secret(secret: str | None, prefix_len: int = 4, suffix_len: int = 4) -> str:
    """
    Masks a secret string to prevent credential leakage.
    Example: 'abcdef123456' -> 'abcd...3456'
    """
    if not secret:
        return "NONE"
    s = str(secret).strip()
    if len(s) <= (prefix_len + suffix_len):
        return "****"
    return f"{s[:prefix_len]}...{s[-suffix_len:]}"


def sanitize_text(text: str, extra_secrets: set[str] | None = None) -> str:
    """
    Sanitizes raw text strings by redacting known secret patterns, headers, and query signatures.
    """
    if not text:
        return text
    sanitized = text
    # 1. Redact specific injected known secrets
    if extra_secrets:
        for sec in extra_secrets:
            if sec and len(sec) > 3 and sec in sanitized:
                sanitized = sanitized.replace(sec, mask_secret(sec))

    # 2. Redact key-value credential patterns
    for pat in SECRET_PATTERNS:
        sanitized = pat.sub(r"\1=[REDACTED]", sanitized)

    return sanitized


def sanitize_dict(data: dict[str, Any], extra_secrets: set[str] | None = None) -> dict[str, Any]:
    """
    Recursively masks sensitive dictionary keys (keys containing 'secret', 'key', 'token', etc.).
    """
    sensitive_keys = {
        "api_secret",
        "secret",
        "api_key",
        "password",
        "token",
        "signature",
        "private_key",
        "passphrase",
        "x-mbx-apikey",
        "x-bapi-api-key",
        "x-bapi-sign",
        "authorization",
    }
    result: dict[str, Any] = {}
    for k, v in data.items():
        k_lower = str(k).lower().strip()
        if any(s in k_lower for s in sensitive_keys):
            if isinstance(v, str):
                result[k] = mask_secret(v)
            else:
                result[k] = "[REDACTED]"
        elif isinstance(v, dict):
            result[k] = sanitize_dict(v, extra_secrets)
        elif isinstance(v, list):
            result[k] = [
                sanitize_dict(item, extra_secrets)
                if isinstance(item, dict)
                else (
                    mask_secret(item)
                    if isinstance(item, str) and any(s in k_lower for s in sensitive_keys)
                    else item
                )
                for item in v
            ]
        elif isinstance(v, str):
            result[k] = sanitize_text(v, extra_secrets)
        else:
            result[k] = v
    return result


def zeroize_bytes(buffer: bytearray) -> None:
    """
    Best-effort in-memory zeroization of mutable bytearray buffers.
    Note: Python immutable str cannot be physically overwritten in RAM.
    """
    for i in range(len(buffer)):
        buffer[i] = 0


@dataclass
class ExchangeCredential:
    exchange: str  # "BINANCE" or "BYBIT"
    environment: str  # "TESTNET" or "PRODUCTION"
    api_key: str
    api_secret: str
    passphrase: str | None = None
    is_active: bool = True
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_safe_dict(self) -> dict[str, Any]:
        """Returns metadata with masked credentials. Plaintext secrets are NEVER returned."""
        return {
            "exchange": self.exchange,
            "environment": self.environment,
            "masked_api_key": mask_secret(self.api_key),
            "has_secret": bool(self.api_secret),
            "has_passphrase": bool(self.passphrase),
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class CredentialVault:
    """
    Authenticated AES-256-GCM Private API Credential Store with optional Cloud KMS / HSM Enclave.
    """

    def __init__(self, master_key: bytes | None = None, kms_enclave: Any | None = None):
        self._explicit_master_key: bytes | None = master_key
        if kms_enclave is not None:
            self.kms_enclave = kms_enclave
        else:
            try:
                from core.auth.kms_enclave import create_kms_enclave

                self.kms_enclave = create_kms_enclave()
            except Exception:  # noqa: BLE001
                self.kms_enclave = None
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        try:
            with db_manager.get_trading_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS vault_credentials (
                        exchange TEXT NOT NULL,
                        environment TEXT NOT NULL,
                        encrypted_payload TEXT NOT NULL,
                        updated_at INTEGER NOT NULL,
                        PRIMARY KEY (exchange, environment)
                    )
                    """
                )
                conn.commit()
        except Exception as e:  # noqa: BLE001 — best-effort schema init
            logger.error(f"Could not initialize vault_credentials table: {e}")

    def _derive_key(self, salt: bytes) -> bytes:
        """
        Derives 256-bit encryption key using master secret or PBKDF2.
        """
        if self._explicit_master_key:
            if len(self._explicit_master_key) != KEY_LENGTH_BYTES:
                raise VaultConfigurationError(
                    f"Master key must be exactly {KEY_LENGTH_BYTES} bytes (256-bit)."
                )
            return self._explicit_master_key

        # 1. Check direct 32-byte master key
        env_master = os.getenv("VAULT_MASTER_KEY", "").strip()
        if env_master:
            # Try hex
            if len(env_master) == 64:
                try:
                    return bytes.fromhex(env_master)
                except ValueError:
                    pass
            # Try base64
            try:
                decoded = base64.b64decode(env_master)
                if len(decoded) == KEY_LENGTH_BYTES:
                    return decoded
            except ValueError:
                logger.debug(
                    "VAULT_MASTER_KEY was not valid base64; treating it as a raw passphrase."
                )
            # Raw string: derive via SHA-256
            return hashlib.sha256(env_master.encode("utf-8")).digest()

        # 2. Check Passphrase derivation via PBKDF2
        env_passphrase = os.getenv("VAULT_PASSPHRASE", "").strip()
        if env_passphrase:
            return hashlib.pbkdf2_hmac(
                "sha256",
                env_passphrase.encode("utf-8"),
                salt,
                PBKDF2_ITERATIONS,
                dklen=KEY_LENGTH_BYTES,
            )

        # 3. Environment check
        app_env = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).lower()
        if app_env == "production":
            raise VaultConfigurationError(
                "Production Security Guard: VAULT_MASTER_KEY or VAULT_PASSPHRASE must be configured in production."
            )

        # Dev fallback deterministic test salt
        return hashlib.pbkdf2_hmac(
            "sha256",
            b"sky_cbt_dev_default_vault_key_do_not_use_in_prod",
            salt,
            10_000,
            dklen=KEY_LENGTH_BYTES,
        )

    def encrypt(self, plaintext_bytes: bytes) -> str:
        """
        Encrypts plaintext bytes with AES-256-GCM.
        If KMS Enclave is active, uses envelope encryption (Version 2).
        Otherwise uses PBKDF2/VAULT_MASTER_KEY (Version 1).
        """
        if self.kms_enclave is not None:
            dek, encrypted_dek = self.kms_enclave.generate_dek()
            nonce = os.urandom(NONCE_LENGTH_BYTES)
            try:
                aesgcm = AESGCM(bytes(dek))
                ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext_bytes, associated_data=None)
                payload = {
                    "version": 2,
                    "kdf": f"kms_envelope_{self.kms_enclave.provider_name.lower()}",
                    "key_id": self.kms_enclave.key_id,
                    "encrypted_dek": encrypted_dek.hex(),
                    "nonce": nonce.hex(),
                    "ciphertext": ciphertext_with_tag.hex(),
                }
                return json.dumps(payload)
            finally:
                self.kms_enclave.safe_zeroize(dek)

        salt = os.urandom(SALT_LENGTH_BYTES)
        nonce = os.urandom(NONCE_LENGTH_BYTES)
        derived_key = self._derive_key(salt)

        aesgcm = AESGCM(derived_key)
        # AESGCM.encrypt computes ciphertext with 16-byte authentication tag appended
        ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext_bytes, associated_data=None)

        payload = {
            "version": 1,
            "kdf": "pbkdf2_hmac_sha256",
            "salt": salt.hex(),
            "nonce": nonce.hex(),
            "ciphertext": ciphertext_with_tag.hex(),
        }
        return json.dumps(payload)

    def decrypt(self, encrypted_json_str: str) -> bytes:
        """
        Decrypts JSON ciphertext, verifying authentication tag.
        Handles both Version 1 (PBKDF2) and Version 2 (KMS Envelope) payloads.
        Tampering raises VaultIntegrityError.
        """
        try:
            payload = json.loads(encrypted_json_str)
        except Exception as e:
            raise VaultIntegrityError("Malformed vault payload: Invalid JSON.") from e

        if not isinstance(payload, dict) or "nonce" not in payload or "ciphertext" not in payload:
            raise VaultIntegrityError(
                "Malformed vault payload: Missing required AEAD envelope fields."
            )

        # Version 2: KMS Envelope
        if payload.get("version") == 2 and "encrypted_dek" in payload:
            enclave = self.kms_enclave
            if enclave is None:
                try:
                    from core.auth.kms_enclave import create_kms_enclave

                    enclave = create_kms_enclave()
                except Exception as e:
                    raise VaultDecryptionError(
                        f"Failed to create KMS Enclave for decryption: {e}"
                    ) from e

            if enclave is None:
                raise VaultDecryptionError(
                    "Payload encrypted under Cloud KMS Envelope, but no KMS Enclave provider is configured."
                )

            try:
                ciphertext_dek = bytes.fromhex(payload["encrypted_dek"])
                nonce = bytes.fromhex(payload["nonce"])
                ciphertext_with_tag = bytes.fromhex(payload["ciphertext"])
            except Exception as e:
                raise VaultIntegrityError("Malformed vault payload: Hex decoding failed.") from e

            if len(nonce) != NONCE_LENGTH_BYTES:
                raise VaultIntegrityError(
                    f"Invalid nonce length ({len(nonce)} != {NONCE_LENGTH_BYTES})."
                )

            dek = enclave.decrypt_dek(ciphertext_dek)
            try:
                aesgcm = AESGCM(bytes(dek))
                return aesgcm.decrypt(nonce, ciphertext_with_tag, associated_data=None)
            except Exception as e:
                raise VaultIntegrityError(
                    "AEAD Tag Verification Failed: KMS-encrypted ciphertext has been tampered with."
                ) from e
            finally:
                enclave.safe_zeroize(dek)

        # Version 1: PBKDF2 / Master Key
        if "salt" not in payload:
            raise VaultIntegrityError(
                "Malformed vault payload: Missing 'salt' in Version 1 envelope."
            )

        try:
            salt = bytes.fromhex(payload["salt"])
            nonce = bytes.fromhex(payload["nonce"])
            ciphertext_with_tag = bytes.fromhex(payload["ciphertext"])
        except Exception as e:
            raise VaultIntegrityError("Malformed vault payload: Hex decoding failed.") from e

        if len(nonce) != NONCE_LENGTH_BYTES:
            raise VaultIntegrityError(
                f"Invalid nonce length ({len(nonce)} != {NONCE_LENGTH_BYTES})."
            )

        derived_key = self._derive_key(salt)
        aesgcm = AESGCM(derived_key)

        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext_with_tag, associated_data=None)
            return plaintext
        except Exception as e:
            # Cryptography raises InvalidTag when authentication tag does not match
            raise VaultIntegrityError(
                "AEAD Tag Verification Failed: Ciphertext has been tampered with or master key is incorrect."
            ) from e

    def store_credential(self, credential: ExchangeCredential) -> None:
        """
        Encrypts and stores exchange credential in vault.
        """
        exch = credential.exchange.upper().strip()
        env = credential.environment.upper().strip()

        if exch not in ("BINANCE", "BYBIT"):
            raise ValueError(f"Unsupported exchange venue: {exch}")
        if env not in ("TESTNET", "PRODUCTION"):
            raise ValueError(f"Unsupported environment: {env}")

        data = {
            "exchange": exch,
            "environment": env,
            "api_key": credential.api_key,
            "api_secret": credential.api_secret,
            "passphrase": credential.passphrase,
            "is_active": credential.is_active,
            "created_at": credential.created_at,
            "updated_at": int(time.time() * 1000),
        }
        raw_bytes = json.dumps(data).encode("utf-8")
        encrypted_str = self.encrypt(raw_bytes)
        now_ms = int(time.time() * 1000)

        with db_manager.get_trading_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO vault_credentials (exchange, environment, encrypted_payload, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (exch, env, encrypted_str, now_ms),
            )
            conn.commit()

        logger.info(
            f"Credential securely stored in vault for {exch} [{env}] (API Key: {mask_secret(credential.api_key)})"
        )

    def get_credential(self, exchange: str, environment: str) -> ExchangeCredential | None:
        """
        Retrieves and decrypts an exchange credential. Returns None if not found or inactive.
        """
        exch = exchange.upper().strip()
        env = environment.upper().strip()

        with db_manager.get_trading_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT encrypted_payload FROM vault_credentials WHERE exchange = ? AND environment = ?",
                (exch, env),
            )
            row = cursor.fetchone()

        if not row:
            return None

        encrypted_str = row["encrypted_payload"]
        decrypted_bytes = self.decrypt(encrypted_str)
        data = json.loads(decrypted_bytes.decode("utf-8"))

        return ExchangeCredential(
            exchange=data["exchange"],
            environment=data["environment"],
            api_key=data["api_key"],
            api_secret=data["api_secret"],
            passphrase=data.get("passphrase"),
            is_active=data.get("is_active", True),
            created_at=data.get("created_at", int(time.time() * 1000)),
            updated_at=data.get("updated_at", int(time.time() * 1000)),
        )

    def delete_credential(self, exchange: str, environment: str) -> bool:
        """
        Removes an exchange credential from vault.
        """
        exch = exchange.upper().strip()
        env = environment.upper().strip()
        with db_manager.get_trading_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM vault_credentials WHERE exchange = ? AND environment = ?",
                (exch, env),
            )
            conn.commit()
            return cursor.rowcount > 0

    def list_credentials(self) -> list[dict[str, Any]]:
        """
        Returns safe metadata for all configured exchange credentials.
        Plaintext secrets are NEVER returned.
        """
        with db_manager.get_trading_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT exchange, environment, encrypted_payload, updated_at FROM vault_credentials"
            )
            rows = cursor.fetchall()

        results: list[dict[str, Any]] = []
        for r in rows:
            try:
                decrypted_bytes = self.decrypt(r["encrypted_payload"])
                data = json.loads(decrypted_bytes.decode("utf-8"))
                results.append(
                    {
                        "exchange": r["exchange"],
                        "environment": r["environment"],
                        "masked_api_key": mask_secret(data.get("api_key")),
                        "is_active": data.get("is_active", True),
                        "has_secret": bool(data.get("api_secret")),
                        "has_passphrase": bool(data.get("passphrase")),
                        "updated_at": r["updated_at"],
                    }
                )
            except Exception as e:  # noqa: BLE001 — per-credential corruption guard
                results.append(
                    {
                        "exchange": r["exchange"],
                        "environment": r["environment"],
                        "masked_api_key": "CORRUPTED_CIPHERTEXT",
                        "is_active": False,
                        "error": str(e),
                        "updated_at": r["updated_at"],
                    }
                )
        return results


# Global singleton vault instance
credential_vault = CredentialVault()
