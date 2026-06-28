// Log sheet: quick-add / entry logging panel.
//
// Uses DialogManager for focus-trap, Escape key, and overlay-click.
// Auto-opens on load. The cancel button closes via hx-on::click inline.

(function () {
  "use strict";

  var sheet = document.getElementById("log-sheet-dialog");
  if (!sheet) return;

  var dlg = new DialogManager("log-sheet-dialog");
  dlg.init();
  dialogManagerRegistry.add(dlg);
  dlg.open();
})();
