#!/usr/bin/env python3
"""
SKY / CBT — CLI Utility for Backup Verification, Atomic Restoration, and Disaster Recovery Drills.

Usage:
    # 1. Non-destructive archive audit & integrity check:
    python scripts/verify_and_restore_backup.py --verify-only path/to/backup.tar.gz

    # 2. Automated Disaster Recovery drill (measures RTO and RPO):
    python scripts/verify_and_restore_backup.py --drill path/to/backup.tar.gz --target data/dr_drill_sandbox

    # 3. Verified restoration to target directory:
    python scripts/verify_and_restore_backup.py --restore path/to/backup.tar.gz --target data/
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database_recovery import DisasterRecoveryEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cbt.dr_cli")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SKY/CBT Database Backup Verification & DR Utility"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--verify-only", metavar="ARCHIVE", help="Non-destructively verify archive integrity"
    )
    group.add_argument(
        "--drill", metavar="ARCHIVE", help="Run automated disaster recovery drill measuring RTO/RPO"
    )
    group.add_argument(
        "--restore", metavar="ARCHIVE", help="Safely restore verified databases to target directory"
    )

    parser.add_argument(
        "--target",
        default="data/dr_drill_sandbox",
        help="Target directory for drill or restoration",
    )
    parser.add_argument(
        "--rto-max",
        type=float,
        default=30.0,
        help="Maximum acceptable RTO in seconds (default: 30.0)",
    )
    parser.add_argument(
        "--rpo-max",
        type=float,
        default=1.0,
        help="Maximum acceptable RPO in seconds (default: 1.0)",
    )

    args = parser.parse_args()
    engine = DisasterRecoveryEngine()

    if args.verify_only:
        archive_path = Path(args.verify_only)
        logger.info(f"Auditing archive integrity: {archive_path}")
        result = engine.restore_from_archive(
            archive_path, target_dir=Path(args.target), dry_run=True
        )
        meta = engine.inspect_archive(archive_path)

        summary = {
            "archive": meta.archive_path,
            "sha256": meta.sha256,
            "size_bytes": meta.size_bytes,
            "success": result.success,
            "databases": [
                {
                    "name": r.db_name,
                    "integrity_passed": r.integrity_check_passed,
                    "foreign_keys_passed": r.foreign_keys_passed,
                    "user_version": r.user_version,
                    "tables": r.tables,
                }
                for r in result.integrity_reports
            ],
            "error": result.error,
        }
        print(json.dumps(summary, indent=2))
        sys.exit(0 if result.success else 1)

    elif args.drill:
        archive_path = Path(args.drill)
        target_path = Path(args.target)
        logger.info(f"Initiating Disaster Recovery Drill on {archive_path} -> {target_path}")
        report = engine.run_disaster_recovery_drill(
            backup_archive=archive_path,
            isolated_recovery_target=target_path,
            rto_target_seconds=args.rto_max,
            rpo_target_seconds=args.rpo_max,
        )
        report_dict = {
            "drill_timestamp": report.drill_timestamp,
            "success": report.success,
            "rto_seconds": report.rto_seconds,
            "rto_target_seconds": report.rto_target_seconds,
            "rto_pass": report.rto_pass,
            "rpo_seconds": report.rpo_seconds,
            "rpo_target_seconds": report.rpo_target_seconds,
            "rpo_pass": report.rpo_pass,
            "databases_verified": report.databases_verified,
            "all_integrity_passed": report.all_integrity_passed,
            "details": report.details,
        }
        print(json.dumps(report_dict, indent=2))
        sys.exit(0 if report.success else 1)

    elif args.restore:
        archive_path = Path(args.restore)
        target_path = Path(args.target)
        logger.warning(f"Restoring verified databases from {archive_path} into {target_path}")
        result = engine.restore_from_archive(archive_path, target_dir=target_path, dry_run=False)
        print(
            json.dumps(
                {
                    "archive": result.archive_path,
                    "target": result.target_dir,
                    "restored_files": result.restored_files,
                    "duration_seconds": round(result.duration_seconds, 4),
                    "success": result.success,
                    "error": result.error,
                },
                indent=2,
            )
        )
        sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
