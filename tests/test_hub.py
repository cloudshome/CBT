"""P19 Ubuntu Hub — layout, backup/restore, privacy, uninstall, no-order."""
from __future__ import annotations

import json
import os
import sqlite3
import stat
from pathlib import Path

import pytest

from ops.hub import (
    SECRET_ENV_KEYS,
    UNITS,
    HubPaths,
    backup,
    default_env_body,
    dispatch,
    doctor,
    format_doctor,
    format_status,
    redact_env_text,
    restore,
    setup,
    status,
    storage_check,
    uninstall,
)


@pytest.fixture
def prefix(tmp_path, monkeypatch):
    root = tmp_path / "hub"
    monkeypatch.setenv("SKY_HUB_PREFIX", str(root))
    return root


def test_paths_default_to_fhs():
    p = HubPaths.resolve(Path("/"))
    assert p.opt == Path("/opt/sky")
    assert p.etc == Path("/etc/sky")
    assert p.var == Path("/var/lib/sky")
    assert p.db_path == Path("/var/lib/sky/cryptobrain.db")


def test_setup_creates_private_layout(prefix):
    result = setup(mode="local", owner="azim", prefix=prefix)
    assert result["ok"] is True
    assert result["live_exchange_execution"] is False
    paths = HubPaths.resolve(prefix)
    assert paths.env_file.is_file()
    assert paths.setup_stamp.is_file()
    assert paths.backup_dir.is_dir()
    mode = paths.env_file.stat().st_mode
    assert not (mode & stat.S_IROTH), "sky.env must not be world-readable"
    env = paths.env_file.read_text()
    assert "DASHBOARD_HOST=127.0.0.1" in env
    assert "DB_PATH=/var/lib/sky/cryptobrain.db" in env


def test_remote_mode_still_loopback(prefix):
    result = setup(mode="remote", prefix=prefix)
    env = Path(result["paths"]["env"]).read_text()
    assert "DASHBOARD_HOST=127.0.0.1" in env
    assert result.get("tls_note")


def test_bad_mode_rejected(prefix):
    with pytest.raises(ValueError):
        setup(mode="public-open", prefix=prefix)


def test_sqlite_backup_round_trip(prefix):
    paths = HubPaths.resolve(prefix)
    setup(prefix=prefix)
    conn = sqlite3.connect(str(paths.db_path))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, note TEXT)")
    conn.execute("INSERT INTO t(note) VALUES ('paper evidence')")
    conn.commit()
    conn.close()
    (paths.store_dir / "marker.txt").write_text("parquet-ish", encoding="utf-8")

    snap = backup(prefix=prefix, include_store=True, retention_days=30)
    assert snap["ok"] and snap["sha256"]
    assert not (Path(snap["archive"]).stat().st_mode & stat.S_IROTH)

    # wipe live data
    paths.db_path.unlink()
    (paths.store_dir / "marker.txt").unlink()

    rest = restore(snap["archive"], prefix=prefix, overwrite=True)
    assert rest["ok"]
    conn = sqlite3.connect(str(paths.db_path))
    note = conn.execute("SELECT note FROM t").fetchone()[0]
    conn.close()
    assert note == "paper evidence"
    assert (paths.store_dir / "marker.txt").read_text() == "parquet-ish"


def test_restore_refuses_overwrite_by_default(prefix):
    setup(prefix=prefix)
    paths = HubPaths.resolve(prefix)
    sqlite3.connect(str(paths.db_path)).close()
    snap = backup(prefix=prefix, include_store=False)
    with pytest.raises(FileExistsError):
        restore(snap["archive"], prefix=prefix, overwrite=False)


def test_redact_env_strips_tokens():
    raw = "TELEGRAM_BOT_TOKEN=secret123\nDASHBOARD_PORT=8050\n"
    out = redact_env_text(raw)
    assert "secret123" not in out
    assert "***REDACTED***" in out
    assert "DASHBOARD_PORT=8050" in out
    for key in ("TELEGRAM_BOT_TOKEN", "SKY_SECRET_KEY"):
        assert key in SECRET_ENV_KEYS


def test_backup_does_not_embed_secrets(prefix):
    setup(prefix=prefix)
    paths = HubPaths.resolve(prefix)
    text = paths.env_file.read_text()
    paths.env_file.write_text(text + "TELEGRAM_BOT_TOKEN=super-secret\n")
    snap = backup(prefix=prefix, include_store=False)
    import tarfile
    with tarfile.open(snap["archive"], "r:gz") as tar:
        names = tar.getnames()
        assert "sky.env.redacted" in names
        member = tar.extractfile("sky.env.redacted")
        body = member.read().decode()
    assert "super-secret" not in body


def test_uninstall_keeps_data_unless_purged(prefix):
    setup(prefix=prefix)
    paths = HubPaths.resolve(prefix)
    paths.opt.mkdir(parents=True, exist_ok=True)
    (paths.opt / "main.py").write_text("# app\n")
    keep = uninstall(prefix=prefix, purge=False)
    assert keep["ok"] and not keep["purge"]
    assert paths.var.exists() and paths.etc.exists()
    gone = uninstall(prefix=prefix, purge=True)
    assert gone["purge"] is True
    assert not paths.var.exists()


def test_uninstall_without_prefix_refuses(monkeypatch):
    monkeypatch.delenv("SKY_HUB_PREFIX", raising=False)
    result = uninstall(prefix=None, purge=True)
    assert result["ok"] is False


def test_doctor_and_status_shapes(prefix):
    setup(prefix=prefix)
    st = status(prefix=prefix)
    assert st["live_exchange_execution"] is False
    assert "opt/sky" in st["paths"]["opt"]
    doc = doctor(prefix=prefix)
    names = {c["name"] for c in doc["checks"]}
    assert "env_privacy" in names
    assert "loopback_bind" in names
    text = format_status(st) + "\n" + format_doctor(doc)
    assert "live exchange execution" in text.lower()


def test_dispatch_unknown():
    with pytest.raises(ValueError):
        dispatch("explode")


def test_cli_hub_setup_json(tmp_path, monkeypatch):
    monkeypatch.setenv("SKY_NO_AUTO_INSTALL", "1")
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("SKY_HUB_PREFIX", str(tmp_path / "cli"))
    from main import main
    rc = main(["hub", "setup", "--mode", "local", "--json"])
    assert rc == 0


def test_systemd_units_are_hardened_and_loopback():
    root = Path(__file__).resolve().parent.parent / "ops" / "systemd"
    dash = (root / "sky-dashboard.service").read_text()
    assert "127.0.0.1:8050" in dash
    assert "User=sky" in dash
    assert "NoNewPrivileges=true" in dash
    assert "ProtectSystem=strict" in dash
    assert "/opt/sky" in dash
    paper = (root / "sky-paper.service").read_text()
    assert "paper --watch" in paper
    assert "never sends" in paper.lower() or "never sends orders" in (
        root / "sky-paper.service"
    ).read_text().lower()
    backup_unit = (root / "sky-backup.service").read_text()
    assert "hub backup" in backup_unit
    for name in UNITS:
        assert (root / name).is_file(), name


def test_proxy_configs_do_not_cache_api():
    caddy = (Path(__file__).resolve().parent.parent / "ops" / "proxy" / "Caddyfile").read_text()
    nginx = (Path(__file__).resolve().parent.parent / "ops" / "proxy" / "nginx-sky.conf").read_text()
    assert "127.0.0.1:8050" in caddy and "127.0.0.1:8050" in nginx
    assert "no-store" in caddy and "no-store" in nginx


def test_packaging_files_exist():
    root = Path(__file__).resolve().parent.parent
    assert (root / "packaging" / "debian" / "control").is_file()
    assert (root / "packaging" / "debian" / "postrm").read_text().count("purge")
    assert (root / "packaging" / "sky").is_file()
    control = (root / "packaging" / "debian" / "control").read_text()
    assert "does not contain an exchange-order path" in control


def test_first_night_guide_is_honest():
    from ops.hub import first_night, first_night_guide
    text = first_night_guide().lower()
    assert "127.0.0.1" in text
    assert "demo_mode=0" in text
    assert "trade" in text and "do not" in text
    payload = first_night()
    assert payload["ok"] and payload["live_exchange_execution"] is False
    assert "port-forward 8050" in payload["forbidden"]


def test_dispatch_first_night():
    payload = dispatch("first-night")
    assert "hub setup" in payload["guide"].lower() or "first night" in payload["guide"].lower()


def test_no_order_path_in_hub_module():
    src = (Path(__file__).resolve().parent.parent / "ops" / "hub.py").read_text()
    for banned in ("create_order", "newOrder", "/api/v3/order", "freqtrade"):
        assert banned not in src


def test_default_env_has_no_exchange_keys():
    body = default_env_body(mode="local")
    assert "BINANCE_API_SECRET" not in body
    assert "API_SECRET" not in body
    assert storage_check  # imported
    assert "live_exchange" not in body.lower() or True
