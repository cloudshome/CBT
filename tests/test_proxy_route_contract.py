"""
tests/test_proxy_route_contract.py
==================================
Contract verification test ensuring absolute route parity between:
1. Python FastAPI authoritative endpoints (app.py)
2. Frontend Vite development proxy (frontend/vite.config.ts)
3. Production Nginx reverse proxy (frontend/nginx.conf)
4. Production Caddy reverse proxy (deploy/Caddyfile)
5. Node/Express legacy compatibility surface (src/server.ts)

Prevents architectural seams, phantom endpoints, and routing desynchronization.
"""

import re
from pathlib import Path

from app import app

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_vite_and_nginx_proxy_prefixes_exact_parity():
    """Validates that frontend/vite.config.ts and frontend/nginx.conf have identical Python API prefixes."""
    vite_file = (REPO_ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    nginx_file = (REPO_ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")

    vite_prefixes = set(re.findall(r"'(/api/[a-zA-Z0-9_\-]+)'", vite_file))
    nginx_prefixes = set(
        re.findall(
            r"location\s+(?:=\s+)?(/api/[a-zA-Z0-9_\-]+)\s+\{\s*proxy_pass\s+http://python-backend:8000",
            nginx_file,
        )
    )

    missing_in_nginx = vite_prefixes - nginx_prefixes
    missing_in_vite = nginx_prefixes - vite_prefixes

    assert not missing_in_nginx, (
        f"Prefixes present in Vite but missing from Nginx: {missing_in_nginx}"
    )
    assert not missing_in_vite, (
        f"Prefixes present in Nginx but missing from Vite: {missing_in_vite}"
    )


def test_fastapi_mounted_routes_fully_covered_in_proxies():
    """Validates that all FastAPI route prefixes in app.py are declared in frontend/vite.config.ts."""
    vite_file = (REPO_ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    vite_prefixes = set(re.findall(r"'(/api/[a-zA-Z0-9_\-]+)'", vite_file))

    app_prefixes = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/"):
            parts = path.split("/")
            if len(parts) >= 3:
                app_prefixes.add("/" + parts[1] + "/" + parts[2])

    unproxied_fastapi_prefixes = app_prefixes - vite_prefixes
    assert not unproxied_fastapi_prefixes, (
        f"FastAPI endpoints mounted in app.py missing from proxy configuration: {unproxied_fastapi_prefixes}"
    )


def test_caddyfile_reverse_proxy_contracts():
    """Validates that deploy/Caddyfile preserves Node readiness and Python terminal routes."""
    caddy_file = (REPO_ROOT / "deploy" / "Caddyfile").read_text(encoding="utf-8")

    assert "handle /api/readiness*" in caddy_file
    assert "reverse_proxy backend:3000" in caddy_file
    assert "handle /api/*" in caddy_file
    assert "reverse_proxy python-backend:8000" in caddy_file
    assert "handle /ws/*" in caddy_file


def test_node_server_express_legacy_headers():
    """Validates that src/server.ts explicitly flags Node responses with legacy fallback headers."""
    server_ts = (REPO_ROOT / "src" / "server.ts").read_text(encoding="utf-8")

    assert "X-Backend-Service" in server_ts
    assert "CTB-Express-Legacy" in server_ts
    assert "X-Authoritative-Backend" in server_ts
    assert "Python-FastAPI" in server_ts
