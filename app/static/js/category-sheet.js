// Create-activity sheet: dialog wrapper for the activity creation form.
//
// Uses DialogManager for focus-trap, Escape key, and overlay-click.
// Auto-opens on load and closes on successful form submission.

(function () {
  "use strict";

  var sheet = document.getElementById("category-sheet-dialog");
  if (!sheet) return;

  var dlg = new DialogManager("category-sheet-dialog");
  dlg.init();
  dialogManagerRegistry.add(dlg);
  dlg.open();

  // Close on successful form submission inside the sheet.
  document.body.addEventListener("htmx:afterRequest", function (event) {
    if (!event.detail.successful) return;
    if (event.detail.target.closest("#category-sheet-dialog") !== sheet) return;
    var method = event.detail.requestConfig && event.detail.requestConfig.method;
    if (method !== "post") return;
    dlg.close();
  });
})();
