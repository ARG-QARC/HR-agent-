const CACHE_NAME = 'recruiter-ai-pwa-v4';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(keys.map((key) => caches.delete(key)));
    })
  );
  self.clients.claim();
});

// Always pass through directly to network (bypasses stale cached JS files)
self.addEventListener('fetch', (event) => {
  event.respondWith(fetch(event.request));
});
