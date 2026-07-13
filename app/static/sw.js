const CACHE = "mushin-v1";
const PRECACHE_URLS = [
  "/static/manifest.json",
  "/static/style.css",
  "/static/logo.png",
  "/static/favicon/favicon-192x192.png",
  "/static/favicon/favicon-512x512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE_URLS)),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request)),
    );
  } else {
    event.respondWith(
      fetch(request).catch(() => caches.match(request)),
    );
  }
});
