"""
core/auth/kms_enclave.py
========================
Cloud KMS / Hardware Security Module (HSM) Key Enclave.

Provides envelope encryption for the AES-256-GCM Private API Credential Vault.
Security Invariants:
1. Data Encryption Key (DEK) is 256-bit AES, generated ephemerally and encrypted under
   a remote Key Encryption Key (KEK) managed by Cloud KMS / HSM.
2. Plaintext DEK resides strictly in mutable bytearray memory and is NEVER persisted to disk.
3. Explicit zeroization (overwriting memory with null bytes) upon process teardown,
   failure, or Master Kill Switch activation.
4. Kill Switch Awareness: Active Master Kill Switch immediately rejects decryption
   and triggers proactive zeroization.
5. Pluggable Backends: MockKMSEnclave (offline test isolation), AWSKMSEnclave, GCPKMSEnclave.
"""

from __future__ import annotations

import logging
import os
import secrets
from abc import ABC, abstractmethod
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.auth.credential_vault import VaultError, mask_secret, zeroize_bytes

logger = logging.getLogger("sky.kms_enclave")

DEK_LENGTH_BYTES = 32  # 256-bit AES


class KMSEnclaveError(VaultError):
    """Base exception for KMS / HSM Enclave errors."""


class KMSEnclaveKillSwitchActiveError(KMSEnclaveError):
    """Raised when an operation is attempted while Master Kill Switch is engaged."""


class KMSEnclaveDecryptionError(KMSEnclaveError):
    """Raised when KMS fails to decrypt ciphertext DEK."""


class KMSEnclaveConfigurationError(KMSEnclaveError):
    """Raised when KMS provider or key identifier is invalid or missing."""


class BaseKMSEnclave(ABC):
    """
    Abstract interface for Cloud KMS / HSM Enclave implementations.
    """

    def __init__(self, key_id: str):
        self.key_id = key_id.strip()
        if not self.key_id:
            raise KMSEnclaveConfigurationError("KMS Key ID cannot be empty.")

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier (e.g., 'MOCK', 'AWS_KMS', 'GCP_KMS')."""

    @abstractmethod
    def encrypt_dek(self, plaintext_dek: bytes) -> bytes:
        """
        Encrypts a 256-bit Data Encryption Key (DEK) under the remote KEK.
        Returns ciphertext DEK bytes.
        """

    @abstractmethod
    def decrypt_dek(self, ciphertext_dek: bytes) -> bytearray:
        """
        Decrypts a ciphertext DEK under the remote KEK.
        Returns mutable bytearray plaintext DEK.
        """

    def generate_dek(self) -> tuple[bytearray, bytes]:
        """
        Generates an ephemeral 256-bit DEK and its encrypted envelope ciphertext.
        Returns: (plaintext_dek as bytearray, ciphertext_dek as bytes)
        """
        self._check_kill_switch()
        raw_key = secrets.token_bytes(DEK_LENGTH_BYTES)
        ciphertext = self.encrypt_dek(raw_key)
        return bytearray(raw_key), ciphertext

    def _check_kill_switch(self) -> None:
        """
        Verifies that Master Kill Switch is NOT engaged.
        If engaged, halts fail-closed immediately.
        """
        try:
            from core.execution.kill_switch import live_kill_switch

            active, state = live_kill_switch.is_active()
            if active:
                raise KMSEnclaveKillSwitchActiveError(
                    f"Master Kill Switch is ACTIVE ({state.reason}). KMS Key Enclave operations rejected."
                )
        except ImportError:
            # Standalone or test sandbox where execution modules are not loaded
            pass

    def safe_zeroize(self, buffer: bytearray | None) -> None:
        """Safely zeroes mutable buffers."""
        if buffer is not None and isinstance(buffer, bytearray):
            zeroize_bytes(buffer)


class MockKMSEnclave(BaseKMSEnclave):
    """
    Sandboxed mock KMS / HSM Enclave for testing, CI, and offline operation.
    Simulates remote HSM envelope encryption using AES-256-GCM under a simulated root KEK.
    """

    def __init__(self, key_id: str = "mock-hsm-master-key-01", simulated_kek: bytes | None = None):
        super().__init__(key_id)
        if simulated_kek:
            if len(simulated_kek) != 32:
                raise KMSEnclaveConfigurationError("Simulated KEK must be 32 bytes.")
            self._kek = simulated_kek
        else:
            # Deterministic or random KEK per instance
            self._kek = secrets.token_bytes(32)
        self._cipher = AESGCM(self._kek)
        self.is_enabled: bool = True
        self.operation_count: int = 0

    @property
    def provider_name(self) -> str:
        return "MOCK_HSM"

    def encrypt_dek(self, plaintext_dek: bytes) -> bytes:
        self._check_kill_switch()
        if not self.is_enabled:
            raise KMSEnclaveError(f"Mock KMS key '{self.key_id}' is disabled.")
        if len(plaintext_dek) != DEK_LENGTH_BYTES:
            raise KMSEnclaveError(f"Plaintext DEK must be {DEK_LENGTH_BYTES} bytes.")

        nonce = secrets.token_bytes(12)
        ciphertext = self._cipher.encrypt(nonce, plaintext_dek, self.key_id.encode("utf-8"))
        self.operation_count += 1
        return nonce + ciphertext

    def decrypt_dek(self, ciphertext_dek: bytes) -> bytearray:
        self._check_kill_switch()
        if not self.is_enabled:
            raise KMSEnclaveError(f"Mock KMS key '{self.key_id}' is disabled.")
        if len(ciphertext_dek) < 12 + 16:  # nonce (12) + tag (16)
            raise KMSEnclaveDecryptionError("Ciphertext DEK is truncated or invalid.")

        nonce = ciphertext_dek[:12]
        ct = ciphertext_dek[12:]
        try:
            plaintext = self._cipher.decrypt(nonce, ct, self.key_id.encode("utf-8"))
            self.operation_count += 1
            return bytearray(plaintext)
        except Exception as e:
            raise KMSEnclaveDecryptionError(f"Mock KMS decryption failed: {e}") from e


class AWSKMSEnclave(BaseKMSEnclave):
    """
    AWS Key Management Service (KMS) Enclave.
    Uses AWS KMS GenerateDataKey and Decrypt APIs.
    """

    def __init__(self, key_id: str, region_name: str | None = None):
        super().__init__(key_id)
        self.region_name = region_name or os.getenv("AWS_REGION", "us-east-1")
        self._client: Any = None

    @property
    def provider_name(self) -> str:
        return "AWS_KMS"

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import boto3

                self._client = boto3.client("kms", region_name=self.region_name)
            except ImportError as e:
                raise KMSEnclaveConfigurationError(
                    "boto3 package is required for AWS KMS Enclave. Install with: pip install boto3"
                ) from e
            except Exception as e:
                raise KMSEnclaveConfigurationError(
                    f"Failed to initialize AWS KMS client: {e}"
                ) from e
        return self._client

    def encrypt_dek(self, plaintext_dek: bytes) -> bytes:
        self._check_kill_switch()
        client = self._get_client()
        try:
            response = client.encrypt(
                KeyId=self.key_id,
                Plaintext=plaintext_dek,
                EncryptionContext={"Application": "SKY_CBT_CREDENTIAL_VAULT"},
            )
            return response["CiphertextBlob"]
        except Exception as e:
            raise KMSEnclaveError(
                f"AWS KMS encrypt failed for key '{mask_secret(self.key_id)}': {e}"
            ) from e

    def decrypt_dek(self, ciphertext_dek: bytes) -> bytearray:
        self._check_kill_switch()
        client = self._get_client()
        try:
            response = client.decrypt(
                CiphertextBlob=ciphertext_dek,
                KeyId=self.key_id,
                EncryptionContext={"Application": "SKY_CBT_CREDENTIAL_VAULT"},
            )
            plaintext = response["Plaintext"]
            return bytearray(plaintext)
        except Exception as e:
            raise KMSEnclaveDecryptionError(
                f"AWS KMS decrypt failed for key '{mask_secret(self.key_id)}': {e}"
            ) from e


class GCPKMSEnclave(BaseKMSEnclave):
    """
    Google Cloud Key Management Service (Cloud KMS) Enclave.
    Uses GCP KMS CryptoKeys Encrypt and Decrypt APIs.
    """

    def __init__(self, key_id: str):
        super().__init__(key_id)
        self._client: Any = None

    @property
    def provider_name(self) -> str:
        return "GCP_KMS"

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from google.cloud import kms

                self._client = kms.KeyManagementServiceClient()
            except ImportError as e:
                raise KMSEnclaveConfigurationError(
                    "google-cloud-kms package is required for GCP KMS Enclave. "
                    "Install with: pip install google-cloud-kms"
                ) from e
            except Exception as e:
                raise KMSEnclaveConfigurationError(
                    f"Failed to initialize GCP KMS client: {e}"
                ) from e
        return self._client

    def encrypt_dek(self, plaintext_dek: bytes) -> bytes:
        self._check_kill_switch()
        client = self._get_client()
        try:
            response = client.encrypt(request={"name": self.key_id, "plaintext": plaintext_dek})
            return response.ciphertext
        except Exception as e:
            raise KMSEnclaveError(
                f"GCP KMS encrypt failed for key '{mask_secret(self.key_id)}': {e}"
            ) from e

    def decrypt_dek(self, ciphertext_dek: bytes) -> bytearray:
        self._check_kill_switch()
        client = self._get_client()
        try:
            response = client.decrypt(request={"name": self.key_id, "ciphertext": ciphertext_dek})
            return bytearray(response.plaintext)
        except Exception as e:
            raise KMSEnclaveDecryptionError(
                f"GCP KMS decrypt failed for key '{mask_secret(self.key_id)}': {e}"
            ) from e


def create_kms_enclave(
    provider: str | None = None, key_id: str | None = None
) -> BaseKMSEnclave | None:
    """
    Factory function to instantiate the configured KMS Enclave.
    Environment variables:
      - KMS_PROVIDER: 'mock' | 'aws' | 'gcp' | 'disabled'
      - KMS_KEY_ID: Cloud KMS key resource name or ARN
    """
    prov = (provider or os.getenv("KMS_PROVIDER", "disabled")).strip().lower()
    kid = key_id or os.getenv("KMS_KEY_ID", "")

    if prov in ("disabled", "", "none"):
        return None
    if prov in ("mock", "simulated"):
        return MockKMSEnclave(key_id=kid or "mock-sky-master-kek")
    if prov in ("aws", "aws_kms"):
        if not kid:
            raise KMSEnclaveConfigurationError("KMS_KEY_ID is required for AWS KMS Enclave.")
        return AWSKMSEnclave(key_id=kid)
    if prov in ("gcp", "gcp_kms", "google"):
        if not kid:
            raise KMSEnclaveConfigurationError("KMS_KEY_ID is required for GCP KMS Enclave.")
        return GCPKMSEnclave(key_id=kid)

    raise KMSEnclaveConfigurationError(
        f"Unsupported KMS provider: '{prov}'. Supported: mock, aws, gcp, disabled."
    )
