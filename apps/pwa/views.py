from django.http import HttpResponse
from django.views import View


class ManifestView(View):
    def get(self, request):
        return HttpResponse(
            """
{
  "name": "TTPAA 운영 포털",
  "short_name": "TTPAA",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#f6f8fb",
  "theme_color": "#0f766e",
  "lang": "ko-KR",
  "icons": [
    {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
    {"src": "/static/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable any"}
  ]
}
            """.strip(),
            content_type="application/manifest+json",
        )


class ServiceWorkerView(View):
    def get(self, request):
        return HttpResponse(
            """
const CACHE_NAME = "ttpaa-static-v4";
const OFFLINE_URL = "/offline/";
const PRELOAD_URLS = ["/", OFFLINE_URL, "/static/css/app.css", "/static/js/app.js"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(PRELOAD_URLS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        return response;
      })
      .catch(async () => {
        const cached = await caches.match(event.request);
        if (cached) {
          return cached;
        }
        if (event.request.mode === "navigate") {
          return caches.match(OFFLINE_URL);
        }
      })
  );
});
            """.strip(),
            content_type="application/javascript",
        )
