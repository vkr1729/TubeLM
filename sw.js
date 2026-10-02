/* TubeLM offline service worker (generated, no framework). */
const TUBELM_CACHE = 'tubelm-v1';
const PRECACHE = ['index.html', 'manifest.json', 'icon.svg', 'favicon-32x32.png', 'feed.xml'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(TUBELM_CACHE)
      .then((cache) => cache.addAll(PRECACHE).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== TUBELM_CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function isAudioRequest(url) {
  return url.pathname.includes('/audio/') || url.pathname.endsWith('.mp3');
}

function isDocumentRequest(request, url) {
  return request.mode === 'navigate'
    || url.pathname.endsWith('.html')
    || url.pathname.endsWith('.xml')
    || url.pathname.endsWith('.json');
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  let url;
  try {
    url = new URL(request.url);
  } catch (_) {
    return;
  }
  if (isAudioRequest(url)) {
    // Cache-first: audio files are immutable week-partitioned assets.
    event.respondWith(
      caches.match(request).then((hit) => {
        if (hit) return hit;
        return fetch(request).then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(TUBELM_CACHE).then((cache) => cache.put(request, copy));
          }
          return res;
        });
      })
    );
    return;
  }
  if (isDocumentRequest(request, url)) {
    // Stale-while-revalidate: render instantly, refresh in background.
    event.respondWith(
      caches.open(TUBELM_CACHE).then(async (cache) => {
        const cached = await cache.match(request);
        const network = fetch(request)
          .then((res) => {
            if (res && res.ok) cache.put(request, res.clone());
            return res;
          })
          .catch(() => cached);
        return cached || network;
      })
    );
  }
});
