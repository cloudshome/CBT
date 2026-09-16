"""
scripts/generate_release_checksums.py
=====================================
Computes cryptographic SHA-256 checksums for all release binaries and artifacts.
Emits standard GNU-format release/SHA256SUMS.txt.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_DIR = REPO_ROOT / "release"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def generate_checksums() -> dict[str, str]:
    if not RELEASE_DIR.exists():
        RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    checksums: dict[str, str] = {}
    lines: list[str] = []

    # Target executable and archive release files
    targets = sorted(
        [
            p
            for p in RELEASE_DIR.iterdir()
            if p.is_file()
            and p.name != "SHA256SUMS.txt"
            and (p.suffix in (".exe", ".zip", ".msi", ".json", ".txt"))
        ],
        key=lambda x: x.name,
    )

    for p in targets:
        digest = sha256_file(p)
        checksums[p.name] = digest
        lines.append(f"{digest}  {p.name}")

    out_file = RELEASE_DIR / "SHA256SUMS.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))

    print(f"[OK] Generated {len(checksums)} SHA-256 checksums in: {out_file}")
    for fname, digest in checksums.items():
        print(f"  {digest[:16]}...  {fname}")

    return checksums


if __name__ == "__main__":
    generate_checksums()
