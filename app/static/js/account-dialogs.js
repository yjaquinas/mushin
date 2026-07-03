// Account-page dialogs plus profile sharing.

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
    var template = document.getElementById("entry-import-data-dialog-template");
    var dialog = document.getElementById("entry-import-data-dialog");
    if (!template || !dialog) return;
    var replacement = template.content.firstElementChild;
    if (!replacement) return;
    dialog.replaceWith(replacement.cloneNode(true));
    importDlg = initDialog("entry-import-data-dialog") || importDlg;
  }

  var importDlg = initDialog("entry-import-data-dialog");
  var deleteDlg = initDialog("delete-account-dialog");

  async function copyShareLink(url) {
    if (!url || !navigator.clipboard || !navigator.clipboard.writeText) return false;
    try {
      await navigator.clipboard.writeText(url);
      return true;
    } catch (_error) {
      return false;
    }
  }

  async function shareProfile(button) {
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
    var shareButton = event.target.closest("[data-share-profile]");
    if (shareButton) {
      shareProfile(shareButton);
      return;
    }

    var importOpen = event.target.closest("#entry-import-open-button");
    if (importOpen && importDlg) {
      importDlg.open();
      return;
    }

    var importCancel = event.target.closest("#entry-import-cancel-button");
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
    var el = document.getElementById("entry-import-data-dialog");
    if (el && el.hasAttribute("data-auto-open") && importDlg) {
      importDlg.open();
    }
  }

  autoOpenImportDialog();

  document.body.addEventListener("dialog:close", function (event) {
    if (event.target && event.target.id === "entry-import-data-dialog") {
      resetImportDialog();
    }
  });

  document.body.addEventListener("htmx:afterSwap", function () {
    importDlg = initDialog("entry-import-data-dialog") || importDlg;
    deleteDlg = initDialog("delete-account-dialog") || deleteDlg;
    autoOpenImportDialog();
  });
})();
