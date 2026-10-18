"""P22.2 native Windows/Android project inventory and static lint."""

from __future__ import annotations

from ops.native_projects import (
    ANDROID_ROOT,
    WINDOWS_ROOT,
    drill_checklist,
    inspect_android,
    inspect_windows,
    native_status,
)


def test_windows_project_tree_is_present():
    report = inspect_windows()
    assert report["present"] is True
    assert report["missing"] == []
    assert report["issues"] == []
    assert report["signed"] is False
    assert report["live_exchange_execution"] is False
    assert (WINDOWS_ROOT / "HubClient.cs").is_file()


def test_android_project_tree_is_present():
    report = inspect_android()
    assert report["present"] is True
    assert report["missing"] == []
    assert report["issues"] == []
    assert report["signed"] is False
    assert (ANDROID_ROOT / "app/src/main/java/app/sky/companion/HubClient.kt").is_file()


def test_sources_refuse_order_path_and_live_flag():
    win = (WINDOWS_ROOT / "HubClient.cs").read_text()
    droid = (ANDROID_ROOT / "app/src/main/java/app/sky/companion/HubClient.kt").read_text()
    for text in (win, droid):
        assert "placeOrder" not in text
        assert "/api/v3/order" not in text
        assert "live_exchange_execution" in text.lower() or "LiveExchangeExecution" in text
        assert (
            "true" not in text.lower().split("live_exchange_execution")[-1][:40] or "false" in text
        )


def test_no_signing_material_committed():
    for root in (WINDOWS_ROOT, ANDROID_ROOT):
        for path in root.rglob("*"):
            if path.is_file():
                assert path.suffix.lower() not in {
                    ".jks",
                    ".keystore",
                    ".p12",
                    ".pfx",
                    ".pem",
                }


def test_lint_fails_closed_when_file_missing(tmp_path):
    report = inspect_windows(tmp_path)
    assert report["present"] is False
    assert "SkyCompanion.csproj" in report["missing"]


def test_lint_catches_order_endpoint(tmp_path):
    (tmp_path / "SkyCompanion.csproj").write_text("<Project/>")
    (tmp_path / "Program.cs").write_text("class P {}")
    (tmp_path / "HubClient.cs").write_text('var url = "https://api.binance.com/api/v3/order";')
    (tmp_path / "AppConfig.cs").write_text("class C {}")
    (tmp_path / "README.md").write_text("x")
    report = inspect_windows(tmp_path)
    assert report["present"] is False
    assert any("exchange order" in i for i in report["issues"])


def test_drills_are_pending_not_claimed():
    drills = drill_checklist()
    assert drills["claimed_complete"] is False
    assert all(step["status"] == "pending" for step in drills["steps"])
    payload = native_status()
    assert payload["signed"] is False
    assert payload["ok"] is True


def test_companion_lint_cli():
    from main import main

    assert main(["companion", "lint", "--json"]) == 0
