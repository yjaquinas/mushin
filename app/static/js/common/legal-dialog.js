(function () {
  var DIALOG_ID = "legal-dialog";
  var CONTENT_ID = "legal-dialog-content";
  var TITLE_ID = "legal-dialog-title";
  var CLOSE_ID = "legal-dialog-close";

  var dialog = document.getElementById(DIALOG_ID);
  var titleEl = document.getElementById(TITLE_ID);
  var closeBtn = document.getElementById(CLOSE_ID);
  if (!dialog) return;

  var dlg = new DialogManager(DIALOG_ID);
  dlg.init();

  if (closeBtn) {
    closeBtn.addEventListener("click", function () {
      dlg.close();
    });
  }

  document.body.addEventListener("htmx:afterSwap", function (e) {
    if (e.detail.target && e.detail.target.id === CONTENT_ID) {
      dlg.open();
    }
  });

  document.addEventListener("click", function (e) {
    var link = e.target.closest("[data-legal]");
    if (!link) return;
    e.preventDefault();

    var type = link.getAttribute("data-legal");
    titleEl.textContent = link.getAttribute("data-dialog-title") || "";

    htmx.ajax("GET", "/legal/" + type, {
      target: "#" + CONTENT_ID,
      swap: "innerHTML",
    });
  });

  document.querySelectorAll(".bottom-nav-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      dlg.close();
    });
  });
})();
