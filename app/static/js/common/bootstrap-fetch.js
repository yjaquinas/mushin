(function () {
  "use strict";
  const root = document.documentElement;
  const original = new URL(window.location.href);
  let domReady = false;
  let running = false;
  let reloadOnRetry = false;
  const parsed = new Promise(resolve => {
    document.addEventListener("DOMContentLoaded", function () {
      window.setTimeout(function () { domReady = true; resolve(); }, 0);
    }, { once: true });
  });

  function showRecovery() {
    root.classList.add("app-booting");
    const cover = document.getElementById("bootstrap-splash");
    if (cover) cover.setAttribute("data-bootstrap-error", "");
    else document.addEventListener("DOMContentLoaded", showRecovery, { once: true });
  }

  async function run() {
    if (running) return;
    running = true;
    document.getElementById("bootstrap-splash")?.removeAttribute("data-bootstrap-error");
    const controller = new AbortController();
    const expired = new Promise((_, reject) => {
      controller.signal.addEventListener("abort", () => reject(new Error("Startup expired")), { once: true });
    });
    const timer = window.setTimeout(() => controller.abort(), 30000);
    try {
      const content = fetch(original.href, {
        headers: { "X-Mushin-Bootstrap": "content", Accept: "text/html" },
        credentials: "same-origin", cache: "no-store", signal: controller.signal,
      }).then(async response => {
        if (!(response.headers.get("Content-Type") || "").includes("text/html")) throw new Error("Expected a page");
        const url = new URL(response.url);
        if (url.origin !== original.origin) throw new Error("Unexpected page origin");
        // Fetch omits redirect fragments from response.url; recover a validated next target's fragment.
        const next = original.searchParams.get("next");
        const target = next?.startsWith("/") && !next.startsWith("//") ? new URL(next, original) : null;
        const nextHash = response.redirected && original.pathname !== "/home" && target?.origin === original.origin ? target.hash : "";
        if (!url.hash) url.hash = nextHash || original.hash;
        return { html: await response.text(), url: url.href };
      });
      const [, page] = await Promise.race([Promise.all([parsed, content]), expired]);
      if (!window.htmx || !window.MushinAppReady || window.MushinAppReady.failed) throw new Error("Startup asset failed");
      for (const link of document.querySelectorAll("link[rel=stylesheet]")) {
        if (new URL(link.href).origin === original.origin && !link.sheet) {
          reloadOnRetry = true;
          throw new Error("Startup style failed");
        }
      }
      reloadOnRetry = true;
      await Promise.race([window.MushinBootstrapInstall(page.html, page.url, controller.signal), expired]);
    } catch (_) {
      showRecovery();
    } finally {
      window.clearTimeout(timer);
      running = false;
    }
  }

  document.addEventListener("click", function (event) {
    if (!event.target.closest("[data-bootstrap-retry]")) return;
    event.preventDefault();
    if (running) return;
    if (reloadOnRetry || !domReady || !window.MushinAppReady || window.MushinAppReady.failed || !window.htmx) {
      window.location.replace(original.href);
    } else run();
  });
  run();
})();
