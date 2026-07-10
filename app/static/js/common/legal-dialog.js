(function () {
  var DIALOG_ID = "settings-dialog-legal";
  var CONTENT_ID = "settings-target-legal-content";
  var TITLE_ID = "settings-title-legal-dialog";
  var CLOSE_ID = "settings-button-legal-close";

  function dialog() {
    return document.getElementById(DIALOG_ID);
  }

  function openDialog() {
    var el = dialog();
    if (!el) return;
    el.removeAttribute("hidden");
    document.body.style.overflow = "hidden";
    var panel = el.querySelector('[role="dialog"]');
    if (panel) panel.focus();
  }

  function closeDialog() {
    var el = dialog();
    if (!el) return;
    el.setAttribute("hidden", "");
    document.body.style.overflow = "";
  }

  document.body.addEventListener("htmx:afterSwap", function (e) {
    if (e.detail.target && e.detail.target.id === CONTENT_ID) {
      openDialog();
    }
  });

  document.addEventListener("click", function (e) {
    var link = e.target.closest("[data-legal]");
    if (!link) return;
    e.preventDefault();

    var titleEl = document.getElementById(TITLE_ID);
    if (!titleEl || !dialog()) return;
    titleEl.textContent = link.getAttribute("data-dialog-title") || "";

    htmx.ajax("GET", "/legal/" + link.getAttribute("data-legal"), {
      target: "#" + CONTENT_ID,
      swap: "innerHTML",
    });
  });

  document.addEventListener("click", function (e) {
    if (e.target.closest("#" + CLOSE_ID)) {
      closeDialog();
      return;
    }

    var el = dialog();
    if (!el || el.hidden || e.target !== el) return;
    closeDialog();
  });

  document.addEventListener("click", function (e) {
    if (e.target.closest(".bottom-nav-tab")) closeDialog();
  });

  window.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeDialog();
  });
})();
