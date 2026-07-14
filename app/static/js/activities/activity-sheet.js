// Create-activity sheet: dialog wrapper for the activity creation form.
//
// Uses DialogManager for focus-trap, Escape key, and overlay-click.
// Auto-opens on load and closes on successful form submission.
// Handles both initial page load and HTMX-swap into #profile-target-activity-sheet.

(function () {
  "use strict";

  function initSheet() {
    var sheet = document.getElementById("activity-dialog-create");
    if (!sheet) return;

    // Prevent duplicate initialization.
    if (sheet.getAttribute("data-activity-sheet-init")) return;
    sheet.setAttribute("data-activity-sheet-init", "true");

    var dlg = new DialogManager("activity-dialog-create");
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

  // HTMX swap into #profile-target-activity-sheet (the new-activity entry point).
  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (event.detail.target.id !== "profile-target-activity-sheet") return;
    initSheet();
  });

  document.addEventListener("click", function (event) {
    var cancel = event.target.closest("#activity-button-create-cancel");
    if (!cancel) return;
    var sheet = document.getElementById("activity-dialog-create");
    if (sheet) sheet.setAttribute("hidden", "");
  });

  // Prevent checking the secret checkbox when the user's plan doesn't allow it.
  document.addEventListener("change", function (event) {
    if (event.target.id !== "activity-secret") return;
    if (!event.target.checked) return;
    var form = event.target.closest("form");
    if (!form || form.getAttribute("data-secret-allowed") === "true") return;
    event.target.checked = false;
    window.showToast(form.getAttribute("data-secret-toast"), "warning");
  });
})();
