// Account-page dialogs plus header share actions.

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

  function resetImportDialog() {
    var template = document.getElementById("settings-template-entry-import-dialog");
    var dialog = document.getElementById("settings-dialog-entry-import");
    if (!template || !dialog) return;
    var replacement = template.content.firstElementChild;
    if (!replacement) return;
    dialog.replaceWith(replacement.cloneNode(true));
    importDlg = initDialog("settings-dialog-entry-import") || importDlg;
  }

  var importDlg = initDialog("settings-dialog-entry-import");
  var deleteDlg = initDialog("settings-dialog-delete-account");

  async function copyShareLink(url) {
    if (!url || !navigator.clipboard || !navigator.clipboard.writeText) return false;
    try {
      await navigator.clipboard.writeText(url);
      return true;
    } catch (_error) {
      return false;
    }
  }

  async function shareLink(button) {
    if (!button) return;
    var rawUrl = button.getAttribute("data-share-url");
    var label = button.getAttribute("data-share-label");
    var copied = button.getAttribute("data-share-copied");
    var failed = button.getAttribute("data-share-failed");
    var url = rawUrl ? new URL(rawUrl, window.location.origin).toString() : "";
    if (!url) return;

    try {
      if (navigator.share && (!navigator.canShare || navigator.canShare({ url: url }))) {
        await navigator.share({ title: label, url: url });
        return;
      }
      if (await copyShareLink(url)) {
        if (window.showToast) window.showToast(copied);
        return;
      }
      throw new Error("share unavailable");
    } catch (error) {
      if (error && error.name === "AbortError") return;
      if (await copyShareLink(url)) {
        if (window.showToast) window.showToast(copied);
        return;
      }
      if (window.showToast) window.showToast(failed, "warning");
    }
  }

  document.addEventListener("click", function (event) {
    var shareButton = event.target.closest("[data-share-link]");
    if (shareButton) {
      shareLink(shareButton);
      return;
    }

    var importOpen = event.target.closest("#settings-button-entry-import-open");
    if (importOpen) importDlg = initDialog("settings-dialog-entry-import") || importDlg;
    if (importOpen && importDlg) {
      importDlg.open();
      return;
    }

    var importCancel = event.target.closest("#settings-button-entry-import-cancel");
    if (importCancel && importDlg) {
      importDlg.close();
      return;
    }

    var deleteOpen = event.target.closest("#settings-button-delete-open");
    if (deleteOpen) deleteDlg = initDialog("settings-dialog-delete-account") || deleteDlg;
    if (deleteOpen && deleteDlg) {
      deleteDlg.open();
      return;
    }

    var deleteCancel = event.target.closest("#settings-button-delete-cancel");
    if (deleteCancel && deleteDlg) {
      deleteDlg.close();
    }
  });

  function autoOpenImportDialog() {
    var el = document.getElementById("settings-dialog-entry-import");
    if (el && el.hasAttribute("data-auto-open") && importDlg) {
      importDlg.open();
    }
  }

  autoOpenImportDialog();

  document.body.addEventListener("dialog:close", function (event) {
    if (event.target && event.target.id === "settings-dialog-entry-import") {
      resetImportDialog();
    }
  });

  document.body.addEventListener("htmx:afterSwap", function () {
    importDlg = initDialog("settings-dialog-entry-import") || importDlg;
    deleteDlg = initDialog("settings-dialog-delete-account") || deleteDlg;
    autoOpenImportDialog();
  });
})();
