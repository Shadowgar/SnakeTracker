"use strict";

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/service-worker.js", {scope: "/"}));
}

document.addEventListener("DOMContentLoaded", () => {
  const logoutForms = document.querySelectorAll('form[action="/logout"]');
  if (!logoutForms.length || !("caches" in window)) return;
  logoutForms.forEach((logout) => logout.addEventListener("submit", async (event) => {
    event.preventDefault();
    const names = await caches.keys();
    await Promise.all(names.filter((name) => name.startsWith("snaketracker-shell-")).map((name) => caches.delete(name)));
    logout.submit();
  }));
});
