// Log sheet: quick-add / entry logging modal.

(function () {
  "use strict";

  var dlg = null;

  function initLogSheet() {
    var sheet = document.getElementById("log-sheet-dialog");
    if (!sheet) return null;
    if (!sheet.querySelector('[role="dialog"]')) return null;
    if (sheet.getAttribute("data-log-sheet-init")) return sheet;

    sheet.setAttribute("data-log-sheet-init", "true");
    dlg = new DialogManager("log-sheet-dialog");
    dlg.init();
    dialogManagerRegistry.add(dlg);
    dlg.open();
    return sheet;
  }

  function resetAndCloseDialog(sheet) {
    if (!sheet || !dlg) return;
    var form = sheet.querySelector("form");
    if (form) {
      form.reset();
      form.querySelectorAll("[data-toggle-time]").forEach(function (checkbox) {
        var fieldGroup = checkbox.closest("[data-time-field-group]");
        var timeInput = fieldGroup ? fieldGroup.querySelector('input[type="time"]') : null;
        if (!timeInput) return;
        if (checkbox.checked) {
          timeInput.setAttribute("hidden", "");
          timeInput.disabled = true;
        } else {
          timeInput.removeAttribute("hidden");
          timeInput.disabled = false;
        }
      });
    }
    dlg.close();
  }

  document.addEventListener("click", function (event) {
    var cancel = event.target.closest("#log-sheet-cancel");
    var sheet = document.getElementById("log-sheet-dialog");
    if (!cancel || !sheet || !sheet.contains(cancel)) return;
    resetAndCloseDialog(sheet);
  });

  document.addEventListener("DOMContentLoaded", function () {
    initLogSheet();
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    var target = event.detail && event.detail.target;
    if (!target || target.id !== "log-sheet-slot") return;
    initLogSheet();
  });
})();
