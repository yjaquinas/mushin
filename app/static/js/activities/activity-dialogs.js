// Activity-page dialogs: rename activity and delete activity.

(function () {
  "use strict";

  function initDialog(id) {
    var el = document.getElementById(id);
    if (!el || !el.querySelector('[role="dialog"]') || el.getAttribute("data-dialog-init")) return null;
    el.setAttribute("data-dialog-init", "true");
    var dlg = new DialogManager(id);
    dlg.init();
    dialogManagerRegistry.add(dlg);
    return dlg;
  }

  var renameDlg = initDialog("activity-dialog-rename");
  var deleteDlg = initDialog("activity-dialog-delete");
  var dynamicDialogs = {};

  function autoOpenDialog(id, dlg) {
    var el = document.getElementById(id);
    if (el && el.hasAttribute("data-auto-open") && dlg) {
      el.removeAttribute("data-auto-open");
      dlg.open();
    }
  }

  document.addEventListener("click", function (event) {
    var renameCancel = event.target.closest("#rename-activity-cancel-button");
    if (renameCancel && renameDlg) {
      renameDlg.close();
      return;
    }

    var deleteCancel = event.target.closest("#activity-button-delete-cancel");
    if (deleteCancel && deleteDlg) {
      deleteDlg.close();
      return;
    }

    var genericCancel = event.target.closest("[data-dialog-close]");
    if (genericCancel) {
      var host = genericCancel.closest("[id]");
      if (!host) return;
      var dlg = dynamicDialogs[host.id];
      if (dlg) dlg.close();
    }
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    renameDlg = initDialog("activity-dialog-rename") || renameDlg;
    deleteDlg = initDialog("activity-dialog-delete") || deleteDlg;

    var target = event.detail && event.detail.target;
    if (!target || !target.id) return;

    if (target.id === "activity-dialog-rename") {
      autoOpenDialog("activity-dialog-rename", renameDlg);
      return;
    }

    if (target.id === "activity-dialog-delete") {
      autoOpenDialog("activity-dialog-delete", deleteDlg);
      return;
    }

    if (
      target.id.startsWith("entry-delete-dialog-") ||
      target.id.startsWith("comment-delete-dialog-") ||
      target.id.startsWith("entry-edit-dialog-") ||
      target.id.startsWith("connect-remove-dialog") ||
      target.id.startsWith("connect-cancel-dialog")
    ) {
      dynamicDialogs[target.id] = initDialog(target.id) || dynamicDialogs[target.id];
      autoOpenDialog(target.id, dynamicDialogs[target.id]);
    }
  });
})();
