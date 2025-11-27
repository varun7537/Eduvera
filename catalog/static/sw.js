const CACHE = 'learnhub-v1';
self.addEventListener('install', e => {
    e.waitUntil(caches.open(CACHE).then(cache => cache.addAll(['/'])));
});
self.addEventListener('fetch', e => {
    e.respondWith(caches.match(e.request).then(res => res || fetch(e.request)));
});