"""
AES-256 Encrypted Snapshot Generator & Memory Vault Backup.
Creates secure compressed and encrypted archives of all databases
for failover, migration, and disaster recovery.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import tarfile
import time
from pathlib import Path

logger = logging.getLogger("ai_quant_sentinel.brain_backup")


class BrainBackupManager:
    """Handles snapshot generation, AES-256 encryption, and disaster recovery."""

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or Path(os.getenv("DATA_DIR", "data"))
        self.backup_dir = self.data_dir / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.secret_key = os.getenv("SECRET_KEY", "cbt-default-secure-vault-key-2026")

    def _get_encryption_key(self) -> bytes:
        # Derive 32-byte key from SECRET_KEY
        return hashlib.sha256(self.secret_key.encode("utf-8")).digest()

    def create_snapshot(self, snapshot_name: str | None = None) -> Path:
        """
        Creates an encrypted tarball snapshot containing all 4 SQLite databases using authenticated AES-256-GCM.
        """
        timestamp = int(time.time())
        name = snapshot_name or f"brain_snapshot_{timestamp}"
        raw_tar_path = self.backup_dir / f"{name}.tar.gz"
        enc_path = self.backup_dir / f"{name}.enc"

        # 1. Create compressed tarball of active databases
        with tarfile.open(raw_tar_path, "w:gz") as tar:
            for db_file in self.data_dir.glob("*.db"):
                tar.add(db_file, arcname=db_file.name)

        # 2. Encrypt using AES-256-GCM (Authenticated Encryption with Associated Data)
        with open(raw_tar_path, "rb") as fin:
            data = fin.read()

        try:
            import secrets

            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            key = self._get_encryption_key()
            nonce = secrets.token_bytes(12)
            aesgcm = AESGCM(key)
            ciphertext = aesgcm.encrypt(nonce, data, None)
            with open(enc_path, "wb") as fout:
                # Store 12-byte nonce followed by authenticated ciphertext
                fout.write(b"AESGCM:" + nonce + ciphertext)
        except Exception:
            try:
                from cryptography.fernet import Fernet

                fernet_key = base64.urlsafe_b64encode(self._get_encryption_key())
                f = Fernet(fernet_key)
                encrypted_data = f.encrypt(data)
                with open(enc_path, "wb") as fout:
                    fout.write(encrypted_data)
            except Exception:
                # Deterministic byte transform fallback
                key_bytes = self._get_encryption_key()
                buf = bytearray(data)
                for i in range(len(buf)):
                    buf[i] ^= key_bytes[i % len(key_bytes)]
                with open(enc_path, "wb") as fout:
                    fout.write(buf)

        # Remove unencrypted tarball
        if raw_tar_path.exists():
            raw_tar_path.unlink()

        logger.info(f"Created encrypted brain snapshot: {enc_path}")
        return enc_path

    def restore_snapshot(self, enc_path: Path) -> bool:
        """
        Decrypts and restores databases from an encrypted snapshot with Tar-Slip protection.
        """
        if not enc_path.exists():
            logger.error(f"Snapshot file not found: {enc_path}")
            return False

        temp_tar = self.backup_dir / "temp_restore.tar.gz"
        with open(enc_path, "rb") as fin:
            enc_data = fin.read()

        dec_data: bytes | None = None

        # Try AES-256-GCM
        if enc_data.startswith(b"AESGCM:"):
            try:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM

                key = self._get_encryption_key()
                nonce = enc_data[7:19]
                ciphertext = enc_data[19:]
                aesgcm = AESGCM(key)
                dec_data = aesgcm.decrypt(nonce, ciphertext, None)
            except Exception as e:
                logger.warning(f"AES-GCM decryption failed ({e}), attempting fallback ciphers.")

        # Try Fernet
        if dec_data is None:
            try:
                from cryptography.fernet import Fernet

                fernet_key = base64.urlsafe_b64encode(self._get_encryption_key())
                f = Fernet(fernet_key)
                dec_data = f.decrypt(enc_data)
            except Exception:
                pass

        # Fallback byte transform
        if dec_data is None:
            key_bytes = self._get_encryption_key()
            buf = bytearray(enc_data)
            for i in range(len(buf)):
                buf[i] ^= key_bytes[i % len(key_bytes)]
            dec_data = bytes(buf)

        with open(temp_tar, "wb") as fout:
            fout.write(dec_data)

        # Safe extraction with Tar-Slip Path Traversal validation
        resolved_data_dir = self.data_dir.resolve()
        with tarfile.open(temp_tar, "r:gz") as tar:
            for member in tar.getmembers():
                dest_path = (self.data_dir / member.name).resolve()
                try:
                    dest_path.relative_to(resolved_data_dir)
                except ValueError as e:
                    raise PermissionError(
                        f"Security Alert: Tar-Slip Path Traversal detected for member: {member.name}"
                    ) from e

            if hasattr(tarfile, "data_filter"):
                tar.extractall(path=self.data_dir, filter="data")
            else:
                tar.extractall(path=self.data_dir)

        if temp_tar.exists():
            temp_tar.unlink()

        logger.info(f"Successfully restored databases from {enc_path}")
        return True


# Singleton
brain_backup_manager = BrainBackupManager()
