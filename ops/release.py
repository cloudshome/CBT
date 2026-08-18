"""P22.1 release engineering primitives.

The module makes release outputs inspectable without pretending this checkout
can sign native installers.  It contains no signing key support beyond
*verification* metadata: private keys belong in the release environment.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
import tarfile
import tempfile
import time
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable

from config import VERSION

CHANNELS = ("stable", "beta")
SCHEMA_VERSION = 1
SECRET_WORDS = ("token", "secret", "password", "api_key", "apikey", "credential", "private_key")


class ReleaseError(ValueError):
    """A release input violates the public release contract."""


def sha256_file(path: Path | str) -> str:
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_kind(path: Path) -> str:
    name = path.name.lower()
    for suffix, kind in (
        (".deb", "ubuntu-deb"), (".msix", "windows-msix"),
        (".exe", "windows-exe"), (".apk", "android-apk"),
        (".aab", "android-aab"), (".whl", "python-wheel"),
        (".tar.gz", "source-archive"), (".zip", "archive"),
    ):
        if name.endswith(suffix):
            return kind
    return "file"


def artifact_record(path: Path | str, *, signed: bool = False,
                    signature: str | None = None) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if signed and not signature:
        raise ReleaseError("signed artifacts require a detached signature or verifier record")
    record: dict[str, Any] = {
        "name": path.name,
        "kind": _artifact_kind(path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "signed": bool(signed),
    }
    if signature:
        record["signature"] = Path(signature).name
    return record


def release_manifest(artifacts: Iterable[Path | str], *, channel: str,
                     version: str = VERSION, commit: str = "unknown",
                     created_at: int | None = None) -> dict[str, Any]:
    """Return stable, sorted public metadata for a release's artifacts."""
    channel = (channel or "").strip().lower()
    if channel not in CHANNELS:
        raise ReleaseError(f"channel must be one of {CHANNELS}")
    records = sorted((artifact_record(p) for p in artifacts), key=lambda row: row["name"])
    names = [row["name"] for row in records]
    if len(names) != len(set(names)):
        raise ReleaseError("artifact names must be unique")
    return {
        "schema": SCHEMA_VERSION,
        "product": "SKY",
        "version": version,
        "channel": channel,
        "commit": commit,
        "created_at": int(created_at if created_at is not None else time.time()),
        "api_compatibility": {"min": 1, "max": 1},
        "live_exchange_execution": False,
        "artifacts": records,
    }


def write_release_manifest(output: Path | str, artifacts: Iterable[Path | str],
                           *, channel: str, version: str = VERSION,
                           commit: str = "unknown", created_at: int | None = None) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = release_manifest(artifacts, channel=channel, version=version,
                               commit=commit, created_at=created_at)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def write_checksums(output: Path | str, artifacts: Iterable[Path | str]) -> Path:
    output = Path(output)
    rows = sorted((Path(p).name, sha256_file(p)) for p in artifacts)
    output.write_text("".join(f"{digest}  {name}\n" for name, digest in rows), encoding="utf-8")
    return output


def _requirement_rows(requirements: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw in requirements.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name = re.split(r"[<>=!~;\[]", line, maxsplit=1)[0].strip()
        if not name:
            continue
        declared = line[len(name):].strip() or "unconstrained"
        try:
            dist = metadata.distribution(name)
            installed = dist.version
            expression = (dist.metadata.get("License-Expression") or "").strip()
            evidence = (dist.metadata.get("License") or "").strip()
            if expression:
                license_name = expression
            else:
                folded = " ".join(evidence.upper().split())
                if folded.startswith("MIT"):
                    license_name = "MIT"
                elif "BSD 3-CLAUSE" in folded or "BSD 3 CLAUSE" in folded:
                    license_name = "BSD-3-Clause"
                elif "APACHE" in folded and "2.0" in folded:
                    license_name = "Apache-2.0"
                elif (evidence and "\n" not in evidence and len(evidence) < 120
                      and re.fullmatch(r"[A-Za-z0-9.+()-]+", evidence)):
                    license_name = evidence
                else:
                    license_name = "NOASSERTION"
        except metadata.PackageNotFoundError:
            installed, license_name, evidence = "not-installed", "NOASSERTION", ""
        rows.append({"name": name, "declared": declared,
                     "installed": installed, "license": license_name,
                     "license_evidence": " ".join(evidence.split())[:240]})
    return sorted(rows, key=lambda row: row["name"].lower())


def dependency_inventory(requirements: Path | str = "requirements.txt") -> list[dict[str, str]]:
    return _requirement_rows(Path(requirements))


def spdx_sbom(*, requirements: Path | str = "requirements.txt",
              version: str = VERSION, created_at: int | None = None) -> dict[str, Any]:
    """Build a small valid SPDX 2.3 JSON inventory without a new dependency."""
    created = int(created_at if created_at is not None else time.time())
    packages = []
    for row in dependency_inventory(requirements):
        packages.append({
            "SPDXID": "SPDXRef-Package-" + re.sub(r"[^A-Za-z0-9.-]", "-", row["name"]),
            "name": row["name"],
            "versionInfo": row["installed"],
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": row["license"] or "NOASSERTION",
            "downloadLocation": "NOASSERTION",
            "externalRefs": [{
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": f"pkg:pypi/{row['name']}@{row['installed']}",
            }],
            "annotations": [{"annotationType": "OTHER", "annotator": "Tool: SKY-P22",
                             "annotationDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(created)),
                             "comment": f"Declared requirement: {row['declared']}"}],
        })
    namespace_hash = hashlib.sha256(f"SKY:{version}:{created}".encode()).hexdigest()[:24]
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"SKY-{version}",
        "documentNamespace": f"https://github.com/Azimshawon/SKY/sbom/{version}/{namespace_hash}",
        "creationInfo": {
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(created)),
            "creators": ["Tool: SKY-P22"],
        },
        "packages": packages,
    }


def write_sbom(output: Path | str, *, requirements: Path | str = "requirements.txt",
               version: str = VERSION, created_at: int | None = None) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(spdx_sbom(requirements=requirements, version=version,
                                           created_at=created_at),
                                 indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def redact(value: Any, key: str = "") -> Any:
    """Recursively redact likely secrets from diagnostics structures."""
    lower = key.lower()
    if any(word in lower for word in SECRET_WORDS):
        return "***REDACTED***"
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        # Bearer-like values and URL credentials must never survive a bundle.
        value = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer ***REDACTED***", value)
        value = re.sub(r"(https?://)[^/@:\s]+:[^/@\s]+@", r"\1***REDACTED***@", value)
    return value


def support_snapshot(*, hub_status: dict[str, Any], hub_doctor: dict[str, Any]) -> dict[str, Any]:
    return redact({
        "schema": SCHEMA_VERSION,
        "generated_at": int(time.time()),
        "app_version": VERSION,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "hub": hub_status,
        "doctor": hub_doctor,
        "privacy": {
            "database_included": False,
            "market_store_included": False,
            "environment_included": False,
            "raw_logs_included": False,
        },
        "live_exchange_execution": False,
    })


def write_support_bundle(output: Path | str, *, hub_status: dict[str, Any],
                         hub_doctor: dict[str, Any]) -> Path:
    """Write a private tar.gz containing only a redacted JSON snapshot."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    snapshot = support_snapshot(hub_status=hub_status, hub_doctor=hub_doctor)
    with tempfile.TemporaryDirectory(prefix="sky-support-") as tmp:
        report = Path(tmp) / "diagnostics.json"
        report.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with tarfile.open(output, "w:gz") as archive:
            info = archive.gettarinfo(str(report), arcname="diagnostics.json")
            info.mtime = 0
            with report.open("rb") as handle:
                archive.addfile(info, handle)
    output.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return output


def signing_readiness() -> dict[str, Any]:
    """Public readiness only. Never reads or prints a credential value."""
    required = {
        "debian": ("SKY_DEBIAN_SIGNING_KEY_ID",),
        "windows": ("SKY_WINDOWS_CERTIFICATE", "SKY_WINDOWS_CERT_PASSWORD"),
        "android": ("SKY_ANDROID_KEYSTORE", "SKY_ANDROID_KEY_ALIAS",
                    "SKY_ANDROID_KEYSTORE_PASSWORD"),
    }
    return {
        target: {"ready": all(bool(os.getenv(name)) for name in names),
                 "required_secret_names": list(names)}
        for target, names in required.items()
    }
