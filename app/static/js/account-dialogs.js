// Account-page dialogs: import-data and delete-account.
//
// Uses DialogManager for focus-trap, Escape key, and overlay-click.
// Cancel buttons inside the dialog content also close the dialog (overlay-click
// fires first since the target is inside the dialog element).
// Auto-open on error uses hx-on::load in import_data_dialog.html.jinja2.

(function () {
  "use strict";

  // ── Import dialog ──────────────────────────────────────────
  var importDlg = new DialogManager("import-data-dialog");
  importDlg.init();
  dialogManagerRegistry.add(importDlg);

  var importCancelBtn = document.getElementById("import-cancel-button");
  if (importCancelBtn) {
    importCancelBtn.addEventListener("click", function () {
      importDlg.close();
    });
  }

  // ── Delete-account dialog ──────────────────────────────────
  var deleteDlg = new DialogManager("delete-account-dialog");
  deleteDlg.init();
  dialogManagerRegistry.add(deleteDlg);

  var deleteCancelBtn = document.getElementById("delete-cancel-button");
  if (deleteCancelBtn) {
    deleteCancelBtn.addEventListener("click", function () {
      deleteDlg.close();
    });
  }
})();
