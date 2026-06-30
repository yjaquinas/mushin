// Log sheet: quick-add / entry logging panel.
//
// Uses DialogManager for focus-trap, Escape key, and overlay-click when
// rendered as a modal dialog. Skips DialogManager when rendered inline
// (data-inline="true") — the form is already visible in the page flow.

(function () {
  "use strict";

  var sheet = document.getElementById("log-sheet-dialog");
  if (!sheet) return;

  // Inline mode — no dialog wrapper, form is already visible.
  if (sheet.getAttribute("data-inline") === "true") return;

  var dlg = new DialogManager("log-sheet-dialog");
  dlg.init();
  dialogManagerRegistry.add(dlg);
  dlg.open();
})();
