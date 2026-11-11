
const CACHE_NAME = "doomwatch-v1";
const APP_FILES = [
  "./",
  "./index.html",
  "./manifest.json"
];

// Install and cache the core dashboard files
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(APP_FILES);
    })
  );

  self.skipWaiting();
});

// Remove old caches when the version changes
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name.startsWith("doomwatch-") && name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );

  self.clients.claim();
});

// Serve cached files first, then try the network
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;

  const requestUrl = new URL(event.request.url);

  if (requestUrl.origin !== self.location.origin) return;

  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) return cachedResponse;

      return fetch(event.request).then((networkResponse) => {
        if (
          networkResponse &&
          networkResponse.status === 200 &&
          networkResponse.type === "basic"
        ) {
          const responseCopy = networkResponse.clone();

          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseCopy);
          });
        }

        return networkResponse;
      }).catch(() => {
        if (event.request.mode === "navigate") {
          return caches.match("./index.html");
        }

        return new Response("Offline — this resource is not cached.", {
          status: 503,
          headers: { "Content-Type": "text/plain" }
        });
      });
    })
  );
});

