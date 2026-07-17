/* Service worker do StormWatch: recebe Web Push e exibe a notificação. */

const CACHE = "stormwatch-v1";
const APP_SHELL = ["/", "/index.html"];

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(APP_SHELL)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Cache-first para o app shell; rede para o resto.
self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request).catch(() => cached))
  );
});

// Recebe o push do backend e mostra a notificação — funciona com o app fechado.
self.addEventListener("push", (event) => {
  let data = { title: "StormWatch", body: "Chuva se aproximando." };
  try {
    if (event.data) data = event.data.json();
  } catch (_) {
    if (event.data) data.body = event.data.text();
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "StormWatch", {
      body: data.body,
      tag: data.tag || "stormwatch",
      renotify: true,
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      vibrate: [120, 60, 120],
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window" }).then((list) => {
      for (const client of list) if ("focus" in client) return client.focus();
      return self.clients.openWindow("/");
    })
  );
});
