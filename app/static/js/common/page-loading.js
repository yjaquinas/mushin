(function () {
  "use strict";

  const root = document.documentElement;
  const pending = new Set();
  root.classList.add("app-booting");

  function reset() {
    pending.clear();
    root.classList.remove("app-booting", "page-loading");
  }

  function start() {
    const token = {};
    const started = performance.now();
    pending.add(token);
    root.classList.add("page-loading");
    let finished = false;
    return function () {
      if (finished) return;
      finished = true;
      // Keep even cached transitions visible, without delaying navigation.
      window.setTimeout(function () {
        pending.delete(token);
        if (!pending.size) root.classList.remove("page-loading");
      }, Math.max(0, 180 - (performance.now() - started)));
    };
  }

  window.MushinPageLoading = { start: start };
  window.MushinAppReady.when(function () {
    root.classList.remove("app-booting");
  });
  window.addEventListener("pageshow", function (event) {
    if (root.hasAttribute("data-bootstrap-pending") || !window.MushinAppReady.ready) return;
    reset();
    if (event.persisted) {
      const finish = start();
      finish();
    }
  });

  document.addEventListener("click", function (event) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest("a[href]");
    if (!link || link.hasAttribute("download") || link.hasAttribute("data-download") || (link.target && link.target !== "_self")) return;
    const url = new URL(link.href, window.location.href);
    if (url.origin !== window.location.origin) return;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return;
    // Wait until every click handler has had a chance to prevent navigation.
    window.setTimeout(function () {
      if (!event.defaultPrevented) start();
    }, 0);
  });
  document.addEventListener("htmx:beforeOnLoad", function (event) {
    const xhr = event.detail.xhr;
    if (xhr.getResponseHeader("HX-Redirect") || xhr.getResponseHeader("HX-Refresh") === "true") start();
  });
})();
