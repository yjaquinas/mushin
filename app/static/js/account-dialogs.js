// Account-page dialogs: import-data and delete-account.

(function () {
  "use strict";

  function initDialog(id) {
    var el = document.getElementById(id);
    if (!el || el.getAttribute("data-dialog-init")) return null;
    el.setAttribute("data-dialog-init", "true");
    var dlg = new DialogManager(id);
    dlg.init();
    dialogManagerRegistry.add(dlg);
    return dlg;
  }

  var importDlg = initDialog("import-data-dialog");
  var deleteDlg = initDialog("delete-account-dialog");

  document.addEventListener("click", function (event) {
    var importOpen = event.target.closest("#import-open-button");
    if (importOpen && importDlg) {
      importDlg.open();
      return;
    }

    var importCancel = event.target.closest("#import-cancel-button");
    if (importCancel && importDlg) {
      importDlg.close();
      return;
    }

    var deleteOpen = event.target.closest("#delete-open-button");
    if (deleteOpen && deleteDlg) {
      deleteDlg.open();
      return;
    }

    var deleteCancel = event.target.closest("#delete-cancel-button");
    if (deleteCancel && deleteDlg) {
      deleteDlg.close();
    }
  });

  function autoOpenImportDialog() {
    var el = document.getElementById("import-data-dialog");
    if (el && el.hasAttribute("data-auto-open") && importDlg) {
      importDlg.open();
    }
  }

  autoOpenImportDialog();

  document.body.addEventListener("htmx:afterSwap", function () {
    importDlg = initDialog("import-data-dialog") || importDlg;
    deleteDlg = initDialog("delete-account-dialog") || deleteDlg;
    autoOpenImportDialog();
  });
})();
