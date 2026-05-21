const CACHE_NAME = 'ks-mobile-v1';
const STATIC = ['/mobile', '/mobile/manifest.json'];

self.addEventListener('install', e => {
    e.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(STATIC)));
    self.skipWaiting();
});

self.addEventListener('activate', e => {
    e.waitUntil(caches.keys().then(keys =>
        Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ));
    self.clients.claim();
});

self.addEventListener('fetch', e => {
    const url = new URL(e.request.url);
    // Network-first for API calls
    if (url.pathname.startsWith('/api/')) {
        e.respondWith(
            fetch(e.request).catch(() => new Response('{"error":"offline"}', {headers: {'Content-Type': 'application/json'}}))
        );
        return;
    }
    // Cache-first for static
    e.respondWith(
        caches.match(e.request).then(cached => cached || fetch(e.request))
    );
});
