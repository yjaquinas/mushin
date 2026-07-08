(function () {
  "use strict";

  function hide(el) {
    if (el) el.setAttribute("hidden", "");
  }

  function show(el) {
    if (el) el.removeAttribute("hidden");
  }

  var toastTimer = null;
  var TOAST_DISMISS_MS = 5000;
  var TOAST_VARIANT_CLASSES = {
    informative: ["border-border", "bg-surface-2", "text-text-primary"],
    warning: ["border-accent", "bg-accent-subtle", "text-accent-text"],
    error: ["border-danger", "bg-danger-subtle", "text-danger"]
  };

  function applyToastVariant(toast, variant) {
    if (!toast) return;
    Object.keys(TOAST_VARIANT_CLASSES).forEach(function (key) {
      TOAST_VARIANT_CLASSES[key].forEach(function (className) {
        toast.classList.remove(className);
      });
    });
    (TOAST_VARIANT_CLASSES[variant] || TOAST_VARIANT_CLASSES.informative).forEach(function (className) {
      toast.classList.add(className);
    });
    toast.dataset.toastVariant = variant;
  }

  function showToast(message, variant) {
    if (!message) return;
    var toast = document.getElementById("toast");
    var textEl = document.getElementById("toast-text");
    if (!toast || !textEl) return;
    applyToastVariant(toast, variant || "informative");
    textEl.textContent = message;
    show(toast);
    if (toastTimer) window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () {
      hide(toast);
      textEl.textContent = "";
    }, TOAST_DISMISS_MS);
  }

  function dismissToast() {
    var toast = document.getElementById("toast");
    var textEl = document.getElementById("toast-text");
    if (toastTimer) window.clearTimeout(toastTimer);
    hide(toast);
    if (textEl) textEl.textContent = "";
  }

  window.showToast = showToast;

  document.body.addEventListener("show-toast", function (e) {
    showToast(e.detail.message, e.detail.variant || "informative");
  });

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-toast-message]").forEach(function (messageNode) {
      showToast(messageNode.dataset.toastMessage, messageNode.dataset.toastVariant || "informative");
      messageNode.remove();
    });

    var closeBtn = document.getElementById("toast-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", dismissToast);
    }
  });
})();
