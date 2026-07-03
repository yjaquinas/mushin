// Admin-page dialogs (delete user confirmation).

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

  var deleteDlg = initDialog("delete-user-dialog");

  document.addEventListener("click", function (event) {
    var deleteOpen = event.target.closest("#delete-user-dialog-trigger");
    if (deleteOpen && deleteDlg) {
      deleteDlg.open();
      return;
    }

    var deleteCancel = event.target.closest("#delete-user-cancel");
    if (deleteCancel && deleteDlg) {
      deleteDlg.close();
    }
  });
})();
