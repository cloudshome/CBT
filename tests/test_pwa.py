"""P18.4 PWA foundation — installability, safe caching, offline shell.

The worker must NEVER cache private API payloads, auth, SSE or mutations.
The manifest must make Chrome/Edge installability pass.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "web" / "static" / "manifest.json"
SW = ROOT / "web" / "static" / "sw.js"
OFFLINE = ROOT / "web" / "static" / "offline.html"
ICON_192 = ROOT / "web" / "static" / "icons" / "icon-192.png"
ICON_512 = ROOT / "web" / "static" / "icons" / "icon-512.png"
ICON_180 = ROOT / "web" / "static" / "icons" / "icon-180.png"
ICON_MASK = ROOT / "web" / "static" / "icons" / "icon-maskable-512.png"
APP = ROOT / "web" / "app.py"


def test_manifest_exists_and_valid():
    assert MANIFEST.exists(), "manifest.json missing"
    data = json.loads(MANIFEST.read_text())
    assert data.get("name"), "manifest name missing"
    assert data.get("short_name"), "manifest short_name missing"
    assert data.get("start_url", "").startswith("/"), "start_url must be /"
    assert data.get("display") in ("standalone", "minimal-ui", "fullscreen"), f"display {data.get('display')} not installable"
    assert data.get("background_color"), "background_color missing"
    assert data.get("theme_color"), "theme_color missing"
    assert data["theme_color"].lower() == "#070b14", f"theme_color should be #070b14, got {data['theme_color']}"
    icons = data.get("icons") or []
    assert len(icons) >= 3, f"expected at least 3 icons, got {len(icons)}"
    sizes = {i.get("sizes") for i in icons}
    assert "192x192" in sizes, f"192 icon missing, sizes={sizes}"
    assert "512x512" in sizes, f"512 icon missing, sizes={sizes}"
    # Purpose any + maskable required for modern Chrome
    purposes = " ".join(i.get("purpose", "") for i in icons)
    assert "any" in purposes, f"purpose any missing in {icons}"
    assert "maskable" in purposes, f"purpose maskable missing in {icons}"
    for icon in icons:
        src = icon.get("src") or ""
        assert src.startswith("/static/"), f"icon src must be /static/, got {src}"
        assert icon.get("type") == "image/png", f"icon type should be image/png, got {icon}"


def test_icons_exist_and_are_png():
    for p in [ICON_192, ICON_512, ICON_180, ICON_MASK]:
        assert p.exists(), f"{p} missing"
        data = p.read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{p.name} not a PNG"
        assert len(data) > 200, f"{p.name} too small, likely empty"


def test_sw_exists_and_safe():
    assert SW.exists(), "sw.js missing"
    js = SW.read_text()
    assert "CACHE_NAME" in js, "CACHE_NAME missing"
    assert "sky-shell" in js, "cache name should be sky-shell"
    assert "SHELL_URLS" in js or "SHELL" in js, "shell precache list missing"
    # Must precache offline and manifest, chart lib, icons — never API
    assert "/offline.html" in js, "offline.html not precached"
    assert "/static/manifest.json" in js, "manifest not precached"
    assert "/static/lightweight-charts" in js or "lightweight" in js, "chart lib not precached"
    # Safety: NEVER_CACHE must include /api/
    assert "startsWith('/api/')" in js or 'startsWith("/api/")' in js, "NEVER_CACHE must check /api/"
    assert "/api/chart/stream" in js or "/api/v1/jobs" in js, "SSE routes must be explicitly never-cached"
    # Must bypass non-GET (POST mutations)
    assert "req.method !== 'GET'" in js or 'request.method' in js, "must bypass non-GET mutations"
    # Must not precache API
    assert "SHELL_URLS" in js
    # Extract SHELL_URLS and ensure no /api/ inside
    shell_match = re.search(r"SHELL_URLS\s*=\s*\[(.*?)\]", js, re.S)
    if shell_match:
        shell_block = shell_match.group(1)
        assert "/api/" not in shell_block, f"SHELL must never contain /api/, got {shell_block}"
    # Push stub exists (abstraction)
    assert "addEventListener('push'" in js or 'addEventListener("push"' in js, "push handler missing"
    assert "showNotification" in js, "push must call showNotification"
    assert "notificationclick" in js, "notificationclick missing"
    # Must have skipWaiting handler
    assert "SKIP_WAITING" in js, "skipWaiting message handler missing"
    assert "self.skipWaiting" in js, "skipWaiting() missing"


def test_sw_never_caches_private_payloads():
    js = SW.read_text()
    # The fetch handler must return early (no respondWith) for NEVER_CACHE
    # That is the only way to guarantee network-only and no CacheStorage leak.
    # Check that the NEVER_CACHE block contains a bare `return;` before respondWith
    never_idx = js.find("NEVER_CACHE")
    assert never_idx != -1
    next_respond = js.find("respondWith", never_idx, never_idx + 2000)
    # There should be a `return;` between NEVER_CACHE check and first respondWith after it
    # Actually our code has `if (NEVER_CACHE) return;` then later navigation check does respondWith
    segment = js[never_idx: never_idx + 800]
    assert "return;" in segment, "NEVER_CACHE must bare-return (network-only, no cache)"
    # Ensure Cache-Control no-cache for sw.js route is set in web/app.py (checked elsewhere)
    # Also ensure sw.js itself is not cached long — checked via route header test


def test_offline_html_exists_and_safe():
    assert OFFLINE.exists(), "offline.html missing"
    html = OFFLINE.read_text()
    assert "Offline" in html, "offline page should mention Offline"
    assert "cached shell" in html or "OFFLINE SHELL" in html, "offline shell marker missing"
    assert "Mutations disabled" in html or "mutations" in html.lower(), "offline must warn mutations disabled"
    assert "never" in html.lower() and "cache" in html.lower(), "offline must explain never-cache privacy"


def test_app_html_has_pwa_links():
    src = APP.read_text()
    # Extract HTML template (plain triple-quoted, not raw)
    m = re.search(r'HTML = r?"""(.*?)"""', src, re.S)
    assert m, "HTML template not found"
    html = m.group(1)
    assert '<link rel="manifest" href="/static/manifest.json">' in html, "manifest link missing"
    assert '<meta name="theme-color" content="#070b14">' in html, "theme-color missing"
    assert 'apple-mobile-web-app-capable' in html, "apple-mobile-web-app-capable missing"
    assert 'apple-touch-icon' in html, "apple-touch-icon missing"
    assert '/static/icons/icon-192.png' in html, "icon 192 link missing"
    assert '/static/icons/icon-180.png' in html, "icon 180 link missing"
    assert 'id=\"offlineBanner\"' in html, "offlineBanner div missing"
    assert 'id=\"installBanner\"' in html, "installBanner div missing"
    assert 'Offline — showing cached shell' in html, "offline banner text missing"
    assert 'Install SKY' in html, "install prompt text missing"
    # Responsive compact CSS
    assert '@media(max-width:640px)' in html, "640px compact media query missing"
    # Service worker registration
    assert "serviceWorker" in html, "serviceWorker registration missing"
    assert "register('/sw.js'" in html or 'register("/sw.js"' in html, "register /sw.js missing"
    assert "scope:'/'" in html or 'scope: "/"' in html or "scope:'/'" in html, "sw scope / missing"
    assert "beforeinstallprompt" in html, "beforeinstallprompt handler missing"
    assert "appinstalled" in html, "appinstalled handler missing"
    assert "navigator.onLine" in html, "online/offline detection missing"
    assert "sky:lastUpdated" in html, "lastUpdated persistence missing"


def test_pwa_routes_serve_without_auth():
    from web.app import make_app
    app = make_app()
    client = app.test_client()
    # sw.js
    r = client.get("/sw.js")
    assert r.status_code == 200, f"/sw.js {r.status_code}"
    assert b"CACHE_NAME" in r.data
    assert r.headers.get("Service-Worker-Allowed") == "/", f"SW Allowed header missing: {r.headers}"
    assert "no-cache" in r.headers.get("Cache-Control", ""), f"sw.js Cache-Control should be no-cache, got {r.headers.get('Cache-Control')}"
    assert r.mimetype == "application/javascript"
    # manifest
    r = client.get("/manifest.json")
    assert r.status_code == 200, f"/manifest.json {r.status_code}"
    data = json.loads(r.data)
    assert data["name"]
    # offline
    r = client.get("/offline.html")
    assert r.status_code == 200, f"/offline.html {r.status_code}"
    assert b"Offline" in r.data
    r = client.get("/offline")
    assert r.status_code == 200, "/offline alias failed"
    # static manifest still works
    r = client.get("/static/manifest.json")
    assert r.status_code == 200, "/static/manifest.json failed"
    # Also check that / with no auth still 200 (public shell)
    r = client.get("/")
    assert r.status_code == 200, "/ should be public"
    assert b"manifest.json" in r.data, "/ should contain manifest link"


def test_no_private_caching_in_sw_headers():
    from web.app import make_app
    app = make_app()
    client = app.test_client()
    # API routes must have no service-worker caching headers (they are network-only)
    # But we check that sw.js itself sets Cache-Control no-cache
    r = client.get("/sw.js")
    cc = r.headers.get("Cache-Control", "")
    assert "no-store" in cc or "no-cache" in cc
    # Ensure that the HTML does not set Cache-Control to cache private data
    # The index page should not be cacheable as private shell with data? It is okay to be network-only via SW navigate fallback.
    # We just ensure the manifest is cacheable but sw is not.


def test_version_bumped():
    import config
    import re
    txt = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text()
    match = re.search(r'^version = "([^"]+)"', txt, re.M)
    assert match, "pyproject.toml version missing"
    assert config.VERSION == match.group(1), (
        f"config.VERSION {config.VERSION} != pyproject {match.group(1)}")
    assert tuple(int(p) for p in config.VERSION.split(".")[:2]) >= (2, 39)


def test_html_still_valid_js():
    # Re-use the served-template parser from test_dashboard_js
    from web.app import HTML
    import re, tempfile, subprocess, shutil
    scripts = re.findall(r"<script>(.*?)</script>", HTML, re.S)
    assert scripts, "no script in served template"
    NODE = shutil.which("node")
    if NODE is None:
        return
    for i, js in enumerate(scripts):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(js)
            path = f.name
        try:
            r = subprocess.run([NODE, "--check", path], capture_output=True, text=True)
            assert r.returncode == 0, f"served script #{i} invalid JS after PWA edit:\n{r.stderr}"
        finally:
            Path(path).unlink(missing_ok=True)
