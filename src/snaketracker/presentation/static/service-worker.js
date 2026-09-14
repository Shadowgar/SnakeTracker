"use strict";

const CACHE_PREFIX = "snaketracker-shell-";
const ASSET_VERSION = "m66-a-owner-fidelity";
const CACHE = `${CACHE_PREFIX}${ASSET_VERSION}`;
const SHELL = [
  `/static/app.css?v=${ASSET_VERSION}`,
  `/static/pwa.js?v=${ASSET_VERSION}`,
  `/static/species-directory.js?v=${ASSET_VERSION}`,
  `/static/quick-log.js?v=${ASSET_VERSION}`,
  "/static/animal-fallbacks/snake.webp",
  "/static/animal-fallbacks/lizard.webp",
  "/static/animal-fallbacks/spider.webp",
  "/static/animal-fallbacks/scorpion.webp",
  "/static/favicon.svg",
  "/static/offline.html",
];
self.addEventListener("install", (event) => event.waitUntil(
  caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
));
self.addEventListener("activate", (event) => event.waitUntil(
  caches.keys()
    .then((names) => Promise.all(names.filter((name) => name.startsWith(CACHE_PREFIX) && name !== CACHE).map((name) => caches.delete(name))))
    .then(() => self.clients.claim())
));
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request)));
    return;
  }
  if (event.request.mode === "navigate") {
    event.respondWith(fetch(event.request).catch(() => caches.match("/static/offline.html")));
  }
});
