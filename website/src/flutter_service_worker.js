/* The site used to be a Flutter app with an offline worker at this address. Browsers that
   still have it installed fetch this file when they check for updates; it removes the old
   worker and its caches so they load the current page. The old app now lives on its own
   path with its own worker, which this file does not touch. */
self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (event) {
  event.waitUntil((async function () {
    var names = await caches.keys();
    await Promise.all(names.filter(function (n) { return n.indexOf("flutter-") === 0; })
      .map(function (n) { return caches.delete(n); }));
    await self.registration.unregister();
    var windows = await self.clients.matchAll({ type: "window" });
    windows.forEach(function (client) { client.navigate(client.url); });
  })());
});
