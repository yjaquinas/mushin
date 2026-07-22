(function () {
  var DIALOG_ID = "settings-dialog-legal";
  var CONTENT_ID = "settings-target-legal-content";
  var TITLE_ID = "settings-title-legal-dialog";
  var CLOSE_ID = "settings-button-legal-close";
  var scrollPosition = null;
  var originalScrollStyles = null;

  function dialog() {
    return document.getElementById(DIALOG_ID);
  }

  function lockPageScroll() {
    if (scrollPosition !== null) return;

    scrollPosition = window.scrollY;
    originalScrollStyles = {
      htmlOverflow: document.documentElement.style.overflow,
      bodyOverflow: document.body.style.overflow,
      bodyPosition: document.body.style.position,
      bodyTop: document.body.style.top,
      bodyWidth: document.body.style.width,
    };
    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";
    document.body.style.position = "fixed";
    document.body.style.top = "-" + scrollPosition + "px";
    document.body.style.width = "100%";
  }

  function unlockPageScroll() {
    if (scrollPosition === null || !originalScrollStyles) return;

    document.documentElement.style.overflow = originalScrollStyles.htmlOverflow;
    document.body.style.overflow = originalScrollStyles.bodyOverflow;
    document.body.style.position = originalScrollStyles.bodyPosition;
    document.body.style.top = originalScrollStyles.bodyTop;
    document.body.style.width = originalScrollStyles.bodyWidth;
    window.scrollTo(0, scrollPosition);
    scrollPosition = null;
    originalScrollStyles = null;
  }

  function openDialog() {
    var el = dialog();
    if (!el) return;
    el.removeAttribute("hidden");
    lockPageScroll();
    var panel = el.querySelector('[role="dialog"]');
    if (panel) panel.focus();
  }

  function closeDialog() {
    var el = dialog();
    if (!el) return;
    el.setAttribute("hidden", "");
    unlockPageScroll();
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
