# Read-only PWA

The service worker is served at `/service-worker.js` with root scope and no-cache semantics. It
handles GET only, caches only the public shell, excludes authenticated HTML and mutation requests,
and uses no IndexedDB or browser draft persistence. The service-worker registration was verified
in Chromium with zero console errors.
