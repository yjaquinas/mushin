(function () {
  "use strict";

  function autosizeTextarea(textarea) {
    if (!textarea) return;
    if (textarea.getClientRects().length === 0) {
      textarea.style.height = "";
      return;
    }
    textarea.style.height = "auto";
    textarea.style.height = textarea.scrollHeight + "px";
  }

  function formatBoundedCount(value) {
    return Number(value || 0).toLocaleString("en-US");
  }

  function enforceBoundedTextareaLimits(textarea) {
    if (!textarea) return;

    var value = textarea.value;
    var maxChars = parseInt(textarea.dataset.boundedMaxChars || textarea.dataset.commentMaxChars || "0", 10);
    var maxLines = parseInt(textarea.dataset.boundedMaxLines || textarea.dataset.commentMaxLines || "0", 10);
    var lineCount = value.length === 0 ? 1 : value.split("\n").length;
    var lastValidValue = textarea.dataset.lastValidValue || "";

    if (maxChars > 0 && value.length > maxChars) {
      textarea.value = lastValidValue;
      if (window.showToast) {
        window.showToast(textarea.dataset.boundedMaxCharsMessage || textarea.dataset.commentMaxCharsMessage, "warning");
      }
      autosizeTextarea(textarea);
      return;
    }

    if (maxLines > 0 && lineCount > maxLines) {
      textarea.value = lastValidValue;
      if (window.showToast) {
        window.showToast(textarea.dataset.boundedMaxLinesMessage || textarea.dataset.commentMaxLinesMessage, "warning");
      }
      autosizeTextarea(textarea);
      return;
    }

    textarea.dataset.lastValidValue = value;
  }

  function updateBoundedTextareaCharCount(textarea) {
    if (!textarea) return;
    var container = textarea.parentElement;
    if (!container) return;
    var counter = container.querySelector("[data-bounded-char-count]") || container.querySelector("[data-comment-char-count]");
    if (!counter) return;
    var maxChars = textarea.dataset.boundedMaxChars || textarea.dataset.commentMaxChars || textarea.getAttribute("maxlength") || "";
    counter.textContent = formatBoundedCount(textarea.value.length) + "/" + formatBoundedCount(maxChars);
  }

  function syncTextarea(textarea) {
    if (textarea.dataset.lastValidValue === undefined) {
      textarea.dataset.lastValidValue = textarea.value;
    }
    enforceBoundedTextareaLimits(textarea);
    autosizeTextarea(textarea);
    updateBoundedTextareaCharCount(textarea);
  }

  function syncCommentFormState(scope) {
    (scope || document).querySelectorAll("[data-comment-form]").forEach(function (form) {
      var textarea = form.querySelector('textarea[name="body"]');
      if (textarea) syncTextarea(textarea);
    });
  }

  function syncBoundedTextareas(scope) {
    (scope || document).querySelectorAll("[data-bounded-textarea]").forEach(syncTextarea);
  }

  document.addEventListener("input", function (event) {
    if (event.target.matches('[data-comment-form] textarea[name="body"], [data-bounded-textarea]')) {
      syncTextarea(event.target);
    }
  });

  document.addEventListener("submit", function (event) {
    var form = event.target.closest("[data-comment-form]");
    if (!form) return;
    var textarea = form.querySelector('textarea[name="body"]');
    if (!textarea || textarea.value.trim().length > 0) return;
    textarea.value = "";
    textarea.dataset.lastValidValue = "";
    autosizeTextarea(textarea);
    updateBoundedTextareaCharCount(textarea);
  }, true);

  document.addEventListener("DOMContentLoaded", function () {
    syncCommentFormState(document);
    syncBoundedTextareas(document);
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    syncCommentFormState(event.detail.target);
    syncBoundedTextareas(event.detail.target);
  });

  document.body.addEventListener("dialog:open", function (event) {
    syncBoundedTextareas(event.target);
  });
})();
