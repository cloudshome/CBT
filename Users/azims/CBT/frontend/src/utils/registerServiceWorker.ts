/**
 * Registers the Service Worker for offline PWA capabilities and Push Notifications in production.
 * In development, unregisters any active service workers to prevent Vite ESM module interception.
 */
export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (typeof window === 'undefined' || !('serviceWorker' in navigator)) {
    return null;
  }

  // In development mode, unregister any existing service worker to prevent caching Vite dynamic modules
  const isDev = Boolean((import.meta as unknown as { env?: { DEV?: boolean } })?.env?.DEV) ||
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1';

  if (isDev) {
    try {
      const registrations = await navigator.serviceWorker.getRegistrations();
      for (const registration of registrations) {
        await registration.unregister();
        console.info('[PWA DEV] Unregistered stale service worker for development.');
      }
      if ('caches' in window) {
        const keys = await caches.keys();
        for (const key of keys) {
          await caches.delete(key);
        }
      }
    } catch (e) {
      console.warn('[PWA DEV] Error cleaning up dev service worker:', e);
    }
    return null;
  }

  try {
    const registration = await navigator.serviceWorker.register('/sw.js', {
      scope: '/',
    });

    console.info('[PWA] Service Worker registered successfully with scope:', registration.scope);

    registration.addEventListener('updatefound', () => {
      const installingWorker = registration.installing;
      if (installingWorker) {
        installingWorker.addEventListener('statechange', () => {
          if (installingWorker.state === 'installed' && navigator.serviceWorker.controller) {
            console.info('[PWA] New version of Crypto Brain Terminal is available. Reload to update.');
          }
        });
      }
    });

    return registration;
  } catch (error) {
    console.error('[PWA] Service Worker registration failed:', error);
    return null;
  }
}

