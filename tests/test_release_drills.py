"""P22.3: drills stay open unless operator evidence is complete."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ops.release_drills import (DRILLS, DrillError, evaluate_evidence,
                                evaluate_file, p22_status)


def _complete(drill_id: str) -> dict:
    spec = DRILLS[drill_id]
    row = {key: "ok" for key in spec["required"]}
    row["operator"] = "owner"
    row["host"] = "release-host-1"
    if "live_exchange_execution" in spec["required"]:
        row["live_exchange_execution"] = False
    if "timestamp_ok" in spec["required"]:
        row["timestamp_ok"] = True
    if "signtool_verify" in spec["required"]:
        row["signtool_verify"] = True
    if "apksigner_verify" in spec["required"]:
        row["apksigner_verify"] = True
    if "verified_on_clean_vm" in spec["required"]:
        row["verified_on_clean_vm"] = True
    if "play_protect_ok" in spec["required"]:
        row["play_protect_ok"] = True
    if "device_model" in spec["required"]:
        row["device_model"] = "Pixel 7"
    if "key_id_last4" in spec["required"]:
        row["key_id_last4"] = "A1B2"
    if "publisher" in spec["required"]:
        row["publisher"] = "SKY"
    if "keystore_alias" in spec["required"]:
        row["keystore_alias"] = "sky"
    for key in spec["required"]:
        if key.endswith("sha256"):
            row[key] = "a" * 64
    return row


def test_catalog_never_claims_p22_complete_without_evidence():
    status = p22_status()
    assert status["p22_complete"] is False
    assert status["live_exchange_execution"] is False
    assert len(status["drills"]) == 6
    assert all(r["status"] == "pending" for r in status["results"])


def test_incomplete_evidence_fails_closed():
    verdict = evaluate_evidence("ubuntu-clean-vm", {"operator": "me"})
    assert verdict["passed"] is False
    assert "backup_sha256" in verdict["missing"]


def test_sandbox_claim_is_rejected():
    evidence = _complete("windows-authenticode")
    evidence["notes"] = "this sandbox signed the exe"
    verdict = evaluate_evidence("windows-authenticode", evidence)
    assert verdict["passed"] is False
    assert verdict["forbidden_claims"]


def test_live_execution_flag_must_stay_false():
    evidence = _complete("windows-clean-target")
    evidence["live_exchange_execution"] = True
    verdict = evaluate_evidence("windows-clean-target", evidence)
    assert verdict["passed"] is False


def test_complete_evidence_passes_and_status_can_go_green(tmp_path):
    for drill_id in DRILLS:
        (tmp_path / f"{drill_id}.json").write_text(
            json.dumps(_complete(drill_id)), encoding="utf-8")
    status = p22_status(tmp_path)
    assert status["p22_complete"] is True
    assert all(r["passed"] for r in status["results"])


def test_evaluate_file_rejects_garbage(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(DrillError):
        evaluate_file("debian-repo-sign", path)


def test_cli_drills_open(capsys):
    from main import main
    assert main(["release", "drills", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["p22_complete"] is False
