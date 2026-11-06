(function () {
  "use strict";
  document.addEventListener("click", async function (event) {
    const link = event.target.closest("[data-download]");
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    const finish = window.MushinRequestLoading.start(link);
    const error = document.getElementById(link.getAttribute("aria-describedby"));
    if (error) error.hidden = true;
    const controller = new AbortController();
    const timer = window.setTimeout(function () { controller.abort(); }, 30000);
    try {
      const response = await fetch(link.href, { signal: controller.signal });
      const disposition = response.headers.get("Content-Disposition") || "";
      if (response.redirected && !disposition.startsWith("attachment")) {
        window.MushinPageLoading.start();
        window.location.href = response.url;
        return;
      }
      if (!response.ok || !disposition.startsWith("attachment")) throw new Error("download failed");
      const filename = /filename="([^"]+)"/.exec(disposition)?.[1];
      if (!filename) throw new Error("missing filename");
      const url = URL.createObjectURL(await response.blob());
      const download = document.createElement("a");
      download.href = url;
      download.download = filename;
      document.body.append(download);
      download.click();
      download.remove();
      window.setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
    } catch (_) {
      if (error) error.hidden = false;
    } finally {
      window.clearTimeout(timer);
      finish();
    }
  });
})();
