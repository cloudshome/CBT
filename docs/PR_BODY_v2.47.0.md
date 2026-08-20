## Summary

This release ships **v2.47.0**, delivering PWA Web Push (VAPID) notifications, high-resolution vector PWA app icons, iOS safe-area/standalone display mode polish, the Risk Center "Why Blocked?" Veto Timeline, and R-Multiple Distribution analytics.

### Key Changes
- **PWA Web Push (VAPID)**:
  - `data/push_notifications.py`: RFC 8292 Web Push manager with SECP256R1 keypair generation, IEEE P1363 ECDSA JWT signature creation, and broadcast dispatch.
  - SQLite `push_subscriptions` table and methods in `data/database.py`.
  - API Endpoints: `GET /api/push/vapid-key` (auth-exempt for PWA worker), `POST /api/push/subscribe`, `POST /api/push/unsubscribe`, `POST /api/push/test`.
  - `web/static/sw.js` and `window.SKY_push` UI integration supporting push events, notification clicks, permissions, and test triggers.
  - Connection probe `_probe_webpush()` in `brain/connections.py` and System tab UI card.
- **PWA Vector Icons & iOS Polish**:
  - `packaging/generate_icons.py` creating high-res 180x180, 192x192, 512x512, and 512x512 maskable PNG icons under `web/static/icons/` with dark navy background (`#070b14`) and glowing cyan/emerald candlestick emblem.
  - iOS safe-area insets (`env(safe-area-inset-top)`) and standalone mode detection (`body.standalone` / `body.ios-standalone`).
- **Risk Center Veto Timeline**:
  - SQLite `risk_vetoes` table and `record_risk_veto` / `get_risk_vetoes` in `data/database.py`.
  - Auto-logging of trade veto events in `brain/decision.py`.
  - Endpoint `GET /api/risk/veto-timeline` and Risk Center card "🛡 VETO TIMELINE — WHY TRADES WERE BLOCKED".
- **R-Multiple Distribution Analytics**:
  - `r_distribution(db)` in `brain/analytics.py` calculating net R histogram bins (`<-2R` to `>=3R`), mean R, median R, and win/loss/scratch counts over `live_book_rows()`.
  - Endpoint `GET /api/analytics/r-distribution` and Risk Center card "📊 R-MULTIPLE DISTRIBUTION".

### Verification
- `pytest -n auto`: **1277 passed, 1 skipped** (11 new unit tests in `tests/test_pwa_push_and_analytics.py`).
- `pytest tests/test_dashboard_js.py -q`: **10 passed**.
