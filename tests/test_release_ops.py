"""P22.1 release metadata, channels, SBOM and private diagnostics."""

from __future__ import annotations

import json
import stat
import tarfile
from pathlib import Path

import pytest

from ops.hub import diagnostics, dispatch, setup
from ops.release import (
    ReleaseError,
    artifact_record,
    dependency_inventory,
    redact,
    release_manifest,
    signing_readiness,
    spdx_sbom,
    write_checksums,
    write_support_bundle,
)


def test_manifest_is_sorted_versioned_and_no_order_path(tmp_path):
    z = tmp_path / "z.apk"
    a = tmp_path / "a.deb"
    z.write_bytes(b"android")
    a.write_bytes(b"ubuntu")
    payload = release_manifest(
        [z, a], channel="beta", version="9.1.2", commit="abc", created_at=123
    )
    assert [row["name"] for row in payload["artifacts"]] == ["a.deb", "z.apk"]
    assert payload["channel"] == "beta"
    assert payload["api_compatibility"] == {"min": 1, "max": 1}
    assert payload["live_exchange_execution"] is False
    assert all(len(row["sha256"]) == 64 for row in payload["artifacts"])


def test_channels_are_closed_vocabulary(tmp_path):
    artifact = tmp_path / "sky.whl"
    artifact.write_bytes(b"wheel")
    with pytest.raises(ReleaseError):
        release_manifest([artifact], channel="nightly")


def test_cannot_claim_signed_without_verifier_record(tmp_path):
    artifact = tmp_path / "sky.exe"
    artifact.write_bytes(b"exe")
    with pytest.raises(ReleaseError):
        artifact_record(artifact, signed=True)


def test_checksums_are_reproducible_and_sorted(tmp_path):
    b = tmp_path / "b.zip"
    b.write_bytes(b"b")
    a = tmp_path / "a.zip"
    a.write_bytes(b"a")
    first = write_checksums(tmp_path / "one", [b, a]).read_text()
    second = write_checksums(tmp_path / "two", [a, b]).read_text()
    assert first == second
    assert first.splitlines()[0].endswith("  a.zip")


def test_spdx_and_license_inventory(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("flask>=3.0\n# comment\nmade-up-sky-package==1\n")
    inventory = dependency_inventory(requirements)
    assert [row["name"] for row in inventory] == ["flask", "made-up-sky-package"]
    assert inventory[1]["installed"] == "not-installed"
    sbom = spdx_sbom(requirements=requirements, version="1.2.3", created_at=0)
    assert sbom["spdxVersion"] == "SPDX-2.3"
    assert sbom["dataLicense"] == "CC0-1.0"
    assert len(sbom["packages"]) == 2


def test_recursive_redaction():
    payload = redact(
        {
            "api_token": "danger",
            "nested": {"password": "danger2", "safe": "Bearer abc.def"},
            "url": "https://me:password@example.test/path",
        }
    )
    text = json.dumps(payload)
    assert "danger" not in text and "abc.def" not in text and "me:password" not in text
    assert payload["nested"]["safe"] == "Bearer ***REDACTED***"


def test_support_bundle_is_private_and_minimal(tmp_path):
    output = tmp_path / "support.tar.gz"
    write_support_bundle(
        output,
        hub_status={
            "ok": True,
            "device_token": "never",
            "paths": {"db": "/private/db"},
        },
        hub_doctor={"ok": True, "password": "never2"},
    )
    assert not (output.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO))
    with tarfile.open(output, "r:gz") as archive:
        assert archive.getnames() == ["diagnostics.json"]
        body = archive.extractfile("diagnostics.json").read().decode()
    assert "never" not in body
    data = json.loads(body)
    assert data["privacy"] == {
        "database_included": False,
        "market_store_included": False,
        "environment_included": False,
        "raw_logs_included": False,
    }
    assert data["live_exchange_execution"] is False


def test_hub_diagnostics_dispatch(tmp_path, monkeypatch):
    prefix = tmp_path / "hub"
    monkeypatch.setenv("SKY_HUB_PREFIX", str(prefix))
    setup(prefix=prefix)
    output = tmp_path / "bundle.tar.gz"
    result = diagnostics(prefix=prefix, output=output)
    assert result["ok"] and result["archive"] == str(output)
    assert "secrets" in result["excludes"]
    via_dispatch = dispatch(
        "diagnostics", prefix=prefix, archive=str(tmp_path / "second.tar.gz")
    )
    assert via_dispatch["ok"]


def test_signing_readiness_reports_names_not_values(monkeypatch):
    monkeypatch.setenv("SKY_WINDOWS_CERTIFICATE", "TOP-SECRET-CERT")
    monkeypatch.setenv("SKY_WINDOWS_CERT_PASSWORD", "TOP-SECRET-PASSWORD")
    payload = signing_readiness()
    assert payload["windows"]["ready"] is True
    assert "TOP-SECRET" not in json.dumps(payload)
    assert payload["debian"]["ready"] is False


def test_release_workflow_and_runbook_exist():
    root = Path(__file__).resolve().parent.parent
    workflow = (root / "ci" / "release.workflow.yml").read_text()
    assert "copy this file" in workflow
    assert "permissions:" in workflow and "contents: read" in workflow
    assert "pip-audit" in workflow
    assert "build_release.py" in workflow
    assert "secrets." not in workflow, (
        "untrusted PR workflow must never receive signing secrets"
    )
    build_deb = (root / "packaging" / "build_deb.sh").read_text()
    postinst = (root / "packaging" / "debian" / "postinst").read_text()
    postrm = (root / "packaging" / "debian" / "postrm").read_text()
    assert "${misc:Depends}" in build_deb and "pip install" in postinst
    assert "rm -rf /opt/sky" in postrm
    runbook = (root / "docs" / "RELEASE_OPERATIONS.md").read_text()
    for phrase in ("lost phone", "certificate expired", "database locked", "rollback"):
        assert phrase in runbook.lower()
