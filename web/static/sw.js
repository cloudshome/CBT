/* SKY PWA service worker — P18.4
 * Safe-by-default: NEVER caches private/API/SSE/mutation payloads.
 * Shell-only precache (HTML shell, JS, icons, chart lib, offline page).
 * Version it so an update invalidates the old shell.
 */
const CACHE_NAME = 'sky-shell-v2.56.0';
const OFFLINE_URL = '/offline.html';
const SHELL_URLS = [
  '/',
  OFFLINE_URL,
  '/static/manifest.json',
  '/static/lightweight-charts.standalone.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon-180.png'
];

// Install: cache shell. No API is added here.
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(SHELL_URLS))
      .then(() => self.skipWaiting())
  );
});

// Activate: delete old caches.
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Fetch router — the safety boundary.
self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Only handle same-origin GET. POST/PUT/PATCH/DELETE are always network-only
  // and must never be intercepted (mutations, auth, approvals, journal).
  if (req.method !== 'GET') return;

  const path = url.pathname;

  // NEVER intercept private / dynamic routes. These must be network-only and
  // must never appear in CacheStorage (shared browser cache leak).
  // Includes: all /api/*, SSE streams, auth, and the service worker itself.
  const NEVER_CACHE = (
    path.startsWith('/api/') ||
    path === '/sw.js' ||
    path === '/manifest.json' ||
    path === '/offline.html' ||
    // explicit SSE endpoints (even though they are under /api/, list them for clarity)
    path === '/api/chart/stream' ||
    path.startsWith('/api/v1/jobs/') // SSE: /api/v1/jobs/<id>/events
  );
  if (NEVER_CACHE) return;

  // Navigation (browser address bar / link / manifest start_url)
  // Network-first, fallback to offline page or cached shell.
  const isNavigate = req.mode === 'navigate' ||
    (req.headers.get('accept') || '').includes('text/html');
  if (isNavigate) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          // Optionally warm the shell cache with fresh navigation response?
          // Do NOT cache HTML that may contain private state rendered server-side.
          // Keep it network-only; only fallback to cache on failure.
          return res;
        })
        .catch(() => caches.match(OFFLINE_URL).then((cached) => cached || caches.match('/')))
    );
    return;
  }

  // Shell static assets: stale-while-revalidate (fast render, fresh in background)
  // Scope: /static/* only, and only safe immutable assets.
  if (path.startsWith('/static/')) {
    event.respondWith(
      caches.match(req).then((cached) => {
        const fetchPromise = fetch(req).then((networkRes) => {
          // Only cache successful, same-origin, GET, opaque-safe responses
          if (networkRes && networkRes.ok && networkRes.type === 'basic') {
            const clone = networkRes.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
          }
          return networkRes;
        }).catch(() => cached);
        // Return cached immediately if present, otherwise wait for network
        return cached || fetchPromise;
      })
    );
    return;
  }

  // Default for everything else: network-first, no cache fallback beyond shell
  // (do not pollute cache with unknown private payloads).
  event.respondWith(
    fetch(req).catch(() => caches.match(req))
  );
});

// Push notification stub — abstraction only (Telegram/Discord remain primary).
// A real push subscription requires VAPID keys and a push server; the PWA
// foundation only wires the event handler so a future P19 push module can
// drop in without changing the worker.
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { body: event.data ? event.data.text() : '' }; }
  const title = data.title || 'SKY';
  const body = data.body || data.message || 'Update from SKY';
  const url = data.url || '/';
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: '/static/icons/icon-192.png',
      badge: '/static/icons/icon-192.png',
      data: { url },
      tag: data.tag || 'sky-default'
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
      for (const w of wins) { if (w.url === url && 'focus' in w) return w.focus(); }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});

// Allow page to trigger skipWaiting()
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});
