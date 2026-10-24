/* Camper Repository, Service Worker. Version 0.2 */
const CACHE = "camper-repository-v0.2";
const SHELL = ["./", "index.html", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   /* Dropbox und andere Fremdadressen nie anfassen */
  e.respondWith(
    fetch(req).then(res => {
      if (res.ok && res.type === "basic") {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(req.mode === "navigate" ? "index.html" : req, copy)).catch(() => {});
      }
      return res;
    }).catch(() =>
      caches.match(req, { ignoreSearch: true }).then(hit => hit || (req.mode === "navigate" ? caches.match("index.html") : undefined))
    )
  );
});
