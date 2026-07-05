// Create-activity sheet: dialog wrapper for the activity creation form.
//
// Uses DialogManager for focus-trap, Escape key, and overlay-click.
// Auto-opens on load and closes on successful form submission.
// Handles both initial page load and HTMX-swap into #sheet.

(function () {
  "use strict";

  function initSheet() {
    var sheet = document.getElementById("activity-sheet-dialog");
    if (!sheet) return;

    // Prevent duplicate initialization.
    if (sheet.getAttribute("data-activity-sheet-init")) return;
    sheet.setAttribute("data-activity-sheet-init", "true");

    var dlg = new DialogManager("activity-sheet-dialog");
    dlg.init();
    dialogManagerRegistry.add(dlg);
    dlg.open();

    // Close on successful form submission inside the sheet.
    // In HTMX 2.x, POST requests have useUrlParams: false.
    document.body.addEventListener("htmx:afterRequest", function (event) {
      if (!event.detail.successful) return;
      if (!document.body.contains(sheet)) return;
      var cfg = event.detail.requestConfig;
      if (!cfg || cfg.useUrlParams) return;
      dlg.close();
    });
  }

  // Initial page load.
  initSheet();

  // HTMX swap into #sheet (the new-activity entry point).
  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (event.detail.target.id !== "sheet") return;
    initSheet();
  });

  document.addEventListener("click", function (event) {
    var cancel = event.target.closest("#activity-sheet-cancel");
    if (!cancel) return;
    var sheet = document.getElementById("activity-sheet-dialog");
    if (sheet) sheet.setAttribute("hidden", "");
  });
})();
