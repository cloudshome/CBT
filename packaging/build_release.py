#!/usr/bin/env python3
"""Assemble unsigned P22 release metadata around already-built artifacts.

Signing is intentionally external: CI signs platform artifacts first, then
passes the resulting files here. This script never accepts private-key values.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import VERSION
from ops.release import (CHANNELS, dependency_inventory, signing_readiness,
                         write_checksums, write_release_manifest, write_sbom)


def _commit() -> str:
    value = os.getenv("GITHUB_SHA", "").strip()
    if value:
        return value
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, timeout=5
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SKY release metadata")
    parser.add_argument("--channel", choices=CHANNELS, default="beta")
    parser.add_argument("--version", default=VERSION)
    parser.add_argument("--output", type=Path, default=Path("dist/release"))
    parser.add_argument("--artifact", action="append", type=Path, default=[])
    parser.add_argument("--requirements", type=Path, default=Path("requirements.txt"))
    args = parser.parse_args(argv)

    missing = [str(path) for path in args.artifact if not path.is_file()]
    if missing:
        parser.error("artifact not found: " + ", ".join(missing))

    args.output.mkdir(parents=True, exist_ok=True)
    checksums = write_checksums(args.output / "SHA256SUMS", args.artifact)
    sbom = write_sbom(args.output / "sky.spdx.json",
                      requirements=args.requirements, version=args.version)
    inventory = args.output / "dependencies.json"
    inventory.write_text(json.dumps(dependency_inventory(args.requirements),
                                    indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = write_release_manifest(
        args.output / "release.json", args.artifact, channel=args.channel,
        version=args.version, commit=_commit())
    readiness = signing_readiness()
    result = {
        "ok": True,
        "version": args.version,
        "channel": args.channel,
        "artifacts": len(args.artifact),
        "metadata": [str(manifest), str(checksums), str(sbom), str(inventory)],
        "signing_readiness": readiness,
        "note": "metadata generated; signed=true is recorded only after platform verification",
        "live_exchange_execution": False,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
