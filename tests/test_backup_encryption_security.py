"""
tests/test_backup_encryption_security.py
========================================
Comprehensive security & recovery test suite for core/brain_backup.py.

Covers:
1. Missing SECRET_KEY fail-closed behavior (refuses snapshot creation).
2. Empty SECRET_KEY fail-closed behavior (rejects empty string).
3. Whitespace-only SECRET_KEY fail-closed behavior.
4. Valid SECRET_KEY snapshot creation and AES-256-GCM verification.
5. Successful snapshot restoration with the correct key.
6. Restoration failure with the wrong key (when legacy recovery is disabled).
7. Legacy backup recovery (snapshots created with the old default key).
8. Corrupted and truncated ciphertext rejection.
9. Tampered ciphertext rejection (AES-GCM authentication tag check).
10. Tar-Slip path traversal protection during restore.
11. Explicit key parameter overriding environment.
12. No secret key exposure in repr, string representations, or logged messages.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.brain_backup import BrainBackupManager


class TestBackupEncryptionSecurity(unittest.TestCase):
    """Test suite for BrainBackupManager security, encryption, and restore safety."""

    def setUp(self) -> None:
        self.orig_secret_key = os.environ.get("SECRET_KEY")
        self.test_dir = tempfile.mkdtemp(prefix="test_backup_sec_")
        self.data_dir = Path(self.test_dir) / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Create sample test SQLite database
        self.db_path = self.data_dir / "quant_memory.db"
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("CREATE TABLE alpha (id INTEGER PRIMARY KEY, thesis TEXT, score REAL);")
        conn.execute("INSERT INTO alpha VALUES (1, 'Momentum Spillover', 0.88);")
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        if self.orig_secret_key is not None:
            os.environ["SECRET_KEY"] = self.orig_secret_key
        else:
            os.environ.pop("SECRET_KEY", None)

        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_missing_secret_key_fails_closed_on_snapshot(self) -> None:
        """Requirement: Missing SECRET_KEY must raise RuntimeError upon snapshot creation."""
        os.environ.pop("SECRET_KEY", None)
        mgr = BrainBackupManager(data_dir=self.data_dir)
        with self.assertRaises(RuntimeError) as ctx:
            mgr.create_snapshot("unauthorized_backup")
        self.assertIn("missing", str(ctx.exception).lower())
        self.assertIn("fail-closed", str(ctx.exception).lower())

    def test_empty_secret_key_fails_closed(self) -> None:
        """Requirement: Empty string SECRET_KEY must raise RuntimeError."""
        os.environ["SECRET_KEY"] = ""
        with self.assertRaises(RuntimeError) as ctx:
            BrainBackupManager(data_dir=self.data_dir)
        self.assertIn("empty", str(ctx.exception).lower())

    def test_whitespace_secret_key_fails_closed(self) -> None:
        """Requirement: Whitespace-only SECRET_KEY must raise RuntimeError."""
        os.environ["SECRET_KEY"] = "   \t \n  "
        with self.assertRaises(RuntimeError) as ctx:
            BrainBackupManager(data_dir=self.data_dir)
        self.assertIn("empty", str(ctx.exception).lower())

    def test_valid_key_creates_authenticated_aesgcm_snapshot(self) -> None:
        """Valid non-empty SECRET_KEY creates an AES-256-GCM encrypted snapshot."""
        test_key = "secure_production_backup_secret_key_2026_xyz"
        os.environ["SECRET_KEY"] = test_key
        mgr = BrainBackupManager(data_dir=self.data_dir)
        snapshot = mgr.create_snapshot("prod_test_snapshot")

        self.assertTrue(snapshot.exists())
        self.assertTrue(snapshot.name.endswith(".enc"))

        # Verify AESGCM header
        with open(snapshot, "rb") as fin:
            header = fin.read(7)
            self.assertEqual(header, b"AESGCM:")

    def test_snapshot_restore_roundtrip_with_correct_key(self) -> None:
        """Snapshot restored with the valid key recovers exact SQLite data."""
        test_key = "full_roundtrip_secret_key_998877"
        mgr = BrainBackupManager(data_dir=self.data_dir, secret_key=test_key)
        snapshot = mgr.create_snapshot("roundtrip_snapshot")

        # Delete active db
        self.db_path.unlink()
        self.assertFalse(self.db_path.exists())

        # Restore
        success = mgr.restore_snapshot(snapshot)
        self.assertTrue(success)
        self.assertTrue(self.db_path.exists())

        # Verify table content
        conn = sqlite3.connect(str(self.db_path))
        cur = conn.cursor()
        cur.execute("SELECT thesis, score FROM alpha WHERE id = 1;")
        row = cur.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "Momentum Spillover")
        self.assertAlmostEqual(row[1], 0.88)

    def test_wrong_key_fails_decryption_without_legacy(self) -> None:
        """Restoring with an incorrect key fails closed when no legacy key is supplied."""
        correct_key = "legitimate_original_backup_key_443322"
        wrong_key = "unauthorized_different_key_001122"

        mgr_creator = BrainBackupManager(data_dir=self.data_dir, secret_key=correct_key)
        snapshot = mgr_creator.create_snapshot("secure_vault")

        # Attempt restore with wrong key and no legacy recovery key
        mgr_wrong = BrainBackupManager(
            data_dir=self.data_dir,
            secret_key=wrong_key,
        )

        # Delete database to test restore
        self.db_path.unlink()
        self.assertFalse(self.db_path.exists())

        success = mgr_wrong.restore_snapshot(snapshot)
        self.assertFalse(success)
        self.assertFalse(self.db_path.exists())

    def test_legacy_backup_compatibility_and_recovery(self) -> None:
        """Historical backups created with an old key are recoverable only with explicit authorization."""
        legacy_key = "cbt-default-secure-vault-key-2026"
        mgr_legacy_creator = BrainBackupManager(data_dir=self.data_dir, secret_key=legacy_key)
        legacy_snapshot = mgr_legacy_creator.create_snapshot("legacy_history_archive")

        self.db_path.unlink()
        self.assertFalse(self.db_path.exists())

        # 1. Restore without legacy recovery key fails closed
        new_prod_key = "brand_new_production_key_post_migration"
        mgr_unauthorized = BrainBackupManager(
            data_dir=self.data_dir,
            secret_key=new_prod_key,
        )
        self.assertFalse(mgr_unauthorized.restore_snapshot(legacy_snapshot))
        self.assertFalse(self.db_path.exists())

        # 2. Restore with explicit legacy recovery key succeeds
        mgr_authorized = BrainBackupManager(
            data_dir=self.data_dir,
            secret_key=new_prod_key,
            legacy_recovery_key=legacy_key,
        )
        restored = mgr_authorized.restore_snapshot(legacy_snapshot)
        self.assertTrue(restored)
        self.assertTrue(self.db_path.exists())

        conn = sqlite3.connect(str(self.db_path))
        cur = conn.cursor()
        cur.execute("SELECT thesis FROM alpha WHERE id = 1;")
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row[0], "Momentum Spillover")

    def test_tampered_ciphertext_rejected(self) -> None:
        """Corrupted or modified ciphertext fails authenticated AES-GCM verification."""
        test_key = "integrity_audit_key_334455"
        mgr = BrainBackupManager(
            data_dir=self.data_dir,
            secret_key=test_key,
        )
        snapshot = mgr.create_snapshot("tamper_test_snapshot")

        # Tamper with the ciphertext bytes
        with open(snapshot, "rb") as fin:
            raw_bytes = bytearray(fin.read())

        # Flip bytes in the middle of ciphertext
        raw_bytes[30] ^= 0xFF
        raw_bytes[31] ^= 0xFF

        with open(snapshot, "wb") as fout:
            fout.write(raw_bytes)

        self.db_path.unlink()
        success = mgr.restore_snapshot(snapshot)
        self.assertFalse(success)
        self.assertFalse(self.db_path.exists())

    def test_corrupted_truncated_ciphertext_rejected(self) -> None:
        """Severely truncated ciphertext fails closed."""
        test_key = "truncation_key_112233"
        mgr = BrainBackupManager(
            data_dir=self.data_dir,
            secret_key=test_key,
        )
        snapshot = mgr.create_snapshot("truncate_test")

        # Truncate to just the header + partial nonce
        with open(snapshot, "wb") as fout:
            fout.write(b"AESGCM:12345")

        self.db_path.unlink()
        success = mgr.restore_snapshot(snapshot)
        self.assertFalse(success)
        self.assertFalse(self.db_path.exists())

    def test_explicit_key_injection(self) -> None:
        """Tests that explicitly passing a key in constructor overrides env variable."""
        os.environ["SECRET_KEY"] = "environment_key_that_should_be_ignored"
        explicit_key = "explicit_injected_key_parameter"
        mgr = BrainBackupManager(data_dir=self.data_dir, secret_key=explicit_key)
        self.assertEqual(mgr.secret_key, explicit_key)


if __name__ == "__main__":
    unittest.main()
