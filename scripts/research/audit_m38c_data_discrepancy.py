import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent


def sha256_file(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def audit():
    manifest_path = ROOT / "research/m37_derivatives_manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    manifest_partitions = manifest["partitions"]
    print(f"Total partitions in manifest: {len(manifest_partitions)}")

    total_manifest_rows = 0
    total_disk_rows = 0
    mismatches = []
    by_category_manifest = {}
    by_category_disk = {}

    for p in manifest_partitions:
        rel_path = p["relative_path"]
        disk_path = ROOT / rel_path
        m_rows = p["rows"]
        m_sha = p["sha256"]
        total_manifest_rows += m_rows

        cat_key = f"{p['symbol']}_{p['metric']}"
        by_category_manifest[cat_key] = by_category_manifest.get(cat_key, 0) + m_rows

        if not disk_path.exists():
            mismatches.append(
                {"path": rel_path, "type": "MISSING_FILE", "manifest_rows": m_rows, "disk_rows": 0}
            )
            continue

        disk_sha = sha256_file(disk_path)
        df = pd.read_parquet(disk_path)
        d_rows = len(df)
        total_disk_rows += d_rows
        by_category_disk[cat_key] = by_category_disk.get(cat_key, 0) + d_rows

        if d_rows != m_rows or disk_sha != m_sha:
            mismatches.append(
                {
                    "path": rel_path,
                    "type": "INTEGRITY_MISMATCH",
                    "manifest_rows": m_rows,
                    "disk_rows": d_rows,
                    "manifest_sha": m_sha,
                    "disk_sha": disk_sha,
                }
            )

    print(f"Manifest Total Rows: {total_manifest_rows}")
    print(f"Disk Total Rows:     {total_disk_rows}")
    print(f"Discrepancies found: {len(mismatches)}")

    print("\nBreakdown by Category (Manifest vs Disk):")
    for cat in sorted(by_category_manifest.keys()):
        m_cnt = by_category_manifest[cat]
        d_cnt = by_category_disk.get(cat, 0)
        print(f"  {cat:30s}: Manifest={m_cnt:6d} | Disk={d_cnt:6d} | Diff={d_cnt - m_cnt}")

    # Now let's check what was excluded, or where 345,596 comes from!
    print(f"\nDelta between 348,046 and 345,596: {348046 - 345596}")


if __name__ == "__main__":
    audit()
