#!/usr/bin/env python3
"""
scripts/sync_heavy_data.py
==========================
CLI command for synchronizing heavy CBT research assets (PDFs, datasets, DB snapshots)
with the 5-TB Google Drive storage tier (ypelectronics11@gmail.com).

Usage:
  python scripts/sync_heavy_data.py --status
  python scripts/sync_heavy_data.py --upload
  python scripts/sync_heavy_data.py --download
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    import dotenv
    dotenv.load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

from core.storage.heavy_data_sync import heavy_data_sync_manager


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SKY / CBT Heavy Data & 5-TB Google Drive Synchronization CLI"
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--status", action="store_true", default=True, help="Display Drive sync telemetry and status"
    )
    group.add_argument(
        "--upload", action="store_true", help="Scan local directories and upload new/changed heavy files to Drive"
    )
    group.add_argument(
        "--download", action="store_true", help="Download missing heavy files recorded in manifest from Drive"
    )
    parser.add_argument(
        "--force", action="store_true", help="Force re-upload or re-download even if matching"
    )

    args = parser.parse_args()

    if args.upload:
        print("[*] Starting Heavy Data Upload to 5-TB Google Drive Storage Tier...")
        report = heavy_data_sync_manager.sync_all_heavy_data(force_upload=args.force)
        print("=" * 60)
        print("UPLOAD REPORT:")
        print(f"  Live Google Drive : {report.is_live_drive}")
        print(f"  Files Scanned     : {report.scanned_count}")
        print(f"  Files Uploaded    : {report.synced_count}")
        print(f"  Files Skipped     : {report.skipped_count}")
        print(f"  Errors            : {report.error_count}")
        print(f"  Data Transferred  : {report.bytes_transferred / (1024 * 1024):.2f} MB")
        if report.errors:
            print("\nErrors encountered:")
            for err in report.errors:
                print(f"  - {err}")
        print("=" * 60)
        return 0 if report.error_count == 0 else 1

    elif args.download:
        print("[*] Starting Rehydration: Downloading Missing Heavy Data from 5-TB Google Drive...")
        report = heavy_data_sync_manager.download_missing_heavy_files()
        print("=" * 60)
        print("DOWNLOAD REPORT:")
        print(f"  Live Google Drive : {report.is_live_drive}")
        print(f"  Files Checked     : {report.scanned_count}")
        print(f"  Files Downloaded  : {report.synced_count}")
        print(f"  Files Existing    : {report.skipped_count}")
        print(f"  Errors            : {report.error_count}")
        print(f"  Data Transferred  : {report.bytes_transferred / (1024 * 1024):.2f} MB")
        if report.errors:
            print("\nErrors encountered:")
            for err in report.errors:
                print(f"  - {err}")
        print("=" * 60)
        return 0 if report.error_count == 0 else 1

    else:
        status = heavy_data_sync_manager.get_status()
        print("=" * 60)
        print("SKY 5-TB GOOGLE DRIVE HEAVY DATA STATUS")
        print("=" * 60)
        print(f"  Storage Tier      : {status['storage_tier']}")
        print(f"  Target Account    : {status['target_account']}")
        print(f"  Connected Account : {status['connected_account']}")
        print(f"  Live Drive Active : {'YES' if status['is_live_google_drive'] else 'NO (Simulated Local Mode)'}")
        print(f"  Synced Files      : {status['total_synced_files']}")
        print(f"  Synced Volume     : {status['total_synced_mb']} MB ({status['total_synced_gb']} GB)")
        print(f"  Manifest Path     : {status['manifest_file']}")
        print(f"  Monitored Folders : {', '.join(status['monitored_folders'])}")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())

