// Some browsers and crawlers (Google's renderer, private modes) refuse service workers; the site works without one.
if ("serviceWorker" in navigator) window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
