const VERSION = "{{ version }}";
const STATIC_CACHE = "dj-static-" + VERSION;
const PAGES_CACHE = "dj-pages-v1";
const MAX_PAGES = 20;
const PRECACHE = {{ precache_json|safe }};
const SKIP_PREFIXES = ["/admin/", "/editor/", "/health", "/feed/", "/sw.js"];
// Job pages (not their report form) and the two home pages.
const PAGE_PATH = /^\/(en\/)?(jobs\/\d+\/(?!report\/)[^/]+\/)?$/;

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names.filter((name) => name.startsWith("dj-static-") && name !== STATIC_CACHE).map((name) => caches.delete(name))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin || SKIP_PREFIXES.some((prefix) => url.pathname.startsWith(prefix))) return;
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(cacheFirst(request));
  } else if (request.mode === "navigate") {
    event.respondWith(networkFirst(request, url));
  }
});

async function cacheFirst(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) await cache.put(request, response.clone());
  return response;
}

async function networkFirst(request, url) {
  try {
    const response = await fetch(request);
    if (response.ok && url.search === "" && PAGE_PATH.test(url.pathname)) {
      const cache = await caches.open(PAGES_CACHE);
      // Delete before put so the newest page sits last in key order and is the one kept.
      await cache.delete(request);
      await cache.put(request, response.clone());
      const keys = await cache.keys();
      for (const key of keys.slice(0, Math.max(0, keys.length - MAX_PAGES))) await cache.delete(key);
    }
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) return cached;
    const offline = await caches.match(url.pathname.startsWith("/en/") ? "/en/offline/" : "/offline/");
    return offline || Response.error();
  }
}
