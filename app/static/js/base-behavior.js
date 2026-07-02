(function () {
  "use strict";

  function hide(el) {
    if (el) el.setAttribute("hidden", "");
  }

  function show(el) {
    if (el) el.removeAttribute("hidden");
  }

  var toastTimer = null;
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
    if (!toast) return;
    applyToastVariant(toast, variant || "informative");
    toast.textContent = message;
    show(toast);
    if (toastTimer) window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () {
      hide(toast);
      toast.textContent = "";
    }, 2500);
  }

  function syncCommentToggle(target) {
    if (!target || !target.id || !target.id.startsWith("comment-slot-")) return;
  }

  function setEntryExpandedState(entryId, open) {
    if (!entryId) return;
    document.querySelectorAll('[data-entry-toggle][data-entry-id="' + entryId + '"]').forEach(function (button) {
      button.setAttribute("aria-expanded", open ? "true" : "false");

      var indicator = button.querySelector("[data-entry-comment-indicator]");
      if (!indicator) return;

      var collapsedIcon = indicator.querySelector("[data-entry-comment-icon-collapsed]");
      var expandedIcon = indicator.querySelector("[data-entry-comment-icon-expanded]");

      if (collapsedIcon) {
        if (open) hide(collapsedIcon);
        else show(collapsedIcon);
      }

      if (expandedIcon) {
        if (open) show(expandedIcon);
        else hide(expandedIcon);
      }
    });

    document.querySelectorAll("#entry-expanded-" + entryId).forEach(function (panel) {
      if (open) show(panel);
      else hide(panel);
    });
  }

  function maybeLoadEntryComments(entryId) {
    var slot = document.getElementById("comment-slot-" + entryId);
    var loader = document.getElementById("comment-loader-" + entryId);
    if (!slot || !loader || slot.childElementCount > 0) return;
    if (window.htmx) window.htmx.trigger(loader, "load-comments");
  }

  function syncExpandedEntries(root) {
    (root || document).querySelectorAll("[data-entry-toggle]").forEach(function (button) {
      var entryId = button.getAttribute("data-entry-id");
      var open = button.getAttribute("aria-expanded") === "true";
      setEntryExpandedState(entryId, open);
      if (open) maybeLoadEntryComments(entryId);
    });
  }

  function syncHistoryFocus(target) {
    if (!target || !target.id || !target.id.startsWith("history-")) return;
    var focusTarget = target.querySelector("[data-history-focus]");
    if (focusTarget) focusTarget.focus();

    var activityId = target.id.slice("history-".length);
    var fieldStats = document.getElementById("field-stats-" + activityId);
    if (!fieldStats || !focusTarget || !focusTarget.dataset.period) return;
    fieldStats.dataset.period = focusTarget.dataset.period;
  }

  function syncHomeCards(target) {
    if (!target || target.id !== "cards") return;
    var emptyState = document.getElementById("home-empty-state");
    if (emptyState && target.querySelector('[id^="card-"]')) {
      emptyState.remove();
    }

    var form = document.getElementById("add-activity-form");
    var opener = document.querySelector("[data-add-activity-open][hidden]");
    if (form) hide(form);
    if (opener) show(opener);
  }

  function syncVisibilityForm() {
    var form = document.getElementById("visibility-form");
    if (!form) return;
    var saveButton = form.querySelector('button[type="submit"]');
    if (!saveButton) return;
    var current = form.querySelector('input[name="visibility"]:checked');
    var selected = form.querySelector('input[name="visibility"]:checked');
    var currentValue = form.dataset.currentVisibility;
    if (!currentValue && current) currentValue = current.value;
    saveButton.disabled = !selected || selected.value === currentValue;
  }

  function resetLogTrigger() {
    var trigger = document.querySelector("[data-log-trigger]");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
  }

  function resetFormFields(form) {
    if (!form) return;
    form.reset();
    form.querySelectorAll("[data-toggle-time]").forEach(function (checkbox) {
      var fieldGroup = checkbox.closest("[data-time-field-group]");
      var timeInput = fieldGroup ? fieldGroup.querySelector('input[type="time"]') : null;
      if (!timeInput) return;
      if (checkbox.checked) {
        hide(timeInput);
        timeInput.disabled = true;
      } else {
        show(timeInput);
        timeInput.disabled = false;
      }
    });
  }

  function autosizeTextarea(textarea) {
    if (!textarea) return;
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
      showToast(textarea.dataset.boundedMaxCharsMessage || textarea.dataset.commentMaxCharsMessage, "warning");
      autosizeTextarea(textarea);
      return;
    }

    if (maxLines > 0 && lineCount > maxLines) {
      textarea.value = lastValidValue;
      showToast(textarea.dataset.boundedMaxLinesMessage || textarea.dataset.commentMaxLinesMessage, "warning");
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

  function syncCommentFormState(scope) {
    (scope || document).querySelectorAll("[data-comment-form]").forEach(function (form) {
      var textarea = form.querySelector('textarea[name="body"]');
      if (!textarea) return;
      if (textarea.dataset.lastValidValue === undefined) {
        textarea.dataset.lastValidValue = textarea.value;
      }
      enforceBoundedTextareaLimits(textarea);
      autosizeTextarea(textarea);
      updateBoundedTextareaCharCount(textarea);
    });
  }

  function syncBoundedTextareas(scope) {
    (scope || document).querySelectorAll("[data-bounded-textarea]").forEach(function (textarea) {
      if (textarea.dataset.lastValidValue === undefined) {
        textarea.dataset.lastValidValue = textarea.value;
      }
      enforceBoundedTextareaLimits(textarea);
      autosizeTextarea(textarea);
      updateBoundedTextareaCharCount(textarea);
    });
  }

  document.addEventListener("click", function (event) {
    var addOpen = event.target.closest("[data-add-activity-open]");
    if (addOpen) {
      hide(addOpen);
      show(document.getElementById("add-activity-form"));
      var nameInput = document.getElementById("category-name");
      if (nameInput) nameInput.focus();
      return;
    }

    var addCancel = event.target.closest("[data-add-activity-cancel]");
    if (addCancel) {
      hide(document.getElementById("add-activity-form"));
      var opener = addCancel.closest("#add-activity-inline");
      opener = opener ? opener.querySelector("[data-add-activity-open]") : null;
      if (opener) show(opener);
      return;
    }

    var requestsToggle = event.target.closest("#requests-cluster-toggle");
    if (requestsToggle) {
      var expanded = requestsToggle.getAttribute("aria-expanded") === "true";
      requestsToggle.setAttribute("aria-expanded", expanded ? "false" : "true");
      var body = document.getElementById("requests-cluster-body");
      if (body) body.toggleAttribute("hidden");
      var icon = document.getElementById("requests-cluster-icon");
      if (icon) icon.textContent = expanded ? "+" : "−";
      return;
    }

    var logTrigger = event.target.closest("[data-log-trigger]");
    if (logTrigger) {
      var open = logTrigger.getAttribute("aria-expanded") === "true";
      if (open) {
        logTrigger.setAttribute("aria-expanded", "false");
        event.preventDefault();
        return;
      }

      logTrigger.setAttribute("aria-expanded", "true");
      return;
    }

    var entryCollapse = event.target.closest("[data-entry-collapse]");
    if (entryCollapse) {
      var collapseId = entryCollapse.getAttribute("data-entry-id");
      setEntryExpandedState(collapseId, false);
      return;
    }

    var entryToggle = event.target.closest("[data-entry-toggle]");
    if (entryToggle) {
      var entryId = entryToggle.getAttribute("data-entry-id");
      var expanded = entryToggle.getAttribute("aria-expanded") === "true";
      setEntryExpandedState(entryId, !expanded);
      if (!expanded) maybeLoadEntryComments(entryId);
      event.preventDefault();
      return;
    }
  }, true);

  document.addEventListener("change", function (event) {
    if (event.target.matches('#visibility-form input[name="visibility"]')) {
      syncVisibilityForm();
      return;
    }

    if (!event.target.matches("[data-toggle-time]")) return;
    var fieldGroup = event.target.closest("[data-time-field-group]");
    var timeInput = fieldGroup ? fieldGroup.querySelector('input[type="time"]') : null;
    if (!timeInput) return;
    if (event.target.checked) {
      hide(timeInput);
      timeInput.disabled = true;
    } else {
      show(timeInput);
      timeInput.disabled = false;
    }
  });

  document.addEventListener("input", function (event) {
    if (event.target.matches('[data-comment-form] textarea[name="body"]')) {
      enforceBoundedTextareaLimits(event.target);
      autosizeTextarea(event.target);
      updateBoundedTextareaCharCount(event.target);
      return;
    }

    if (!event.target.matches("[data-bounded-textarea]")) return;
    enforceBoundedTextareaLimits(event.target);
    autosizeTextarea(event.target);
    updateBoundedTextareaCharCount(event.target);
  });

  document.addEventListener("submit", function (event) {
    var form = event.target.closest("[data-comment-form]");
    if (!form) return;
    var textarea = form.querySelector('textarea[name="body"]');
    if (!textarea) return;
    if (textarea.value.trim().length === 0) {
      textarea.value = "";
      textarea.dataset.lastValidValue = "";
      autosizeTextarea(textarea);
      updateBoundedTextareaCharCount(textarea);
    }
  }, true);

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-toast-message]").forEach(function (messageNode) {
      showToast(messageNode.dataset.toastMessage, messageNode.dataset.toastVariant || "informative");
      messageNode.remove();
    });
    document.querySelectorAll("[data-flash-dismiss]").forEach(function (flash) {
      window.setTimeout(function () {
        flash.remove();
      }, 5000);
    });
    syncVisibilityForm();
    syncExpandedEntries(document);
    syncCommentFormState(document);
    syncBoundedTextareas(document);
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    var target = event.detail.target;
    syncHistoryFocus(target);
    syncHomeCards(target);
    syncVisibilityForm();
    syncCommentToggle(target);
    syncExpandedEntries(target);
    syncCommentFormState(target);
    syncBoundedTextareas(target);
  });

  document.body.addEventListener("htmx:afterRequest", function (event) {
    var elt = event.detail.elt;
    if (elt && elt.id === "logout-button" && event.detail.successful) {
      window.location.href = "/";
      return;
    }

    if (elt && elt.matches("[data-log-trigger]")) {
      return;
    }
  });

  document.body.addEventListener("log-saved", function () {
    document.querySelectorAll("#log-sheet-inline form, #log-sheet-dialog form").forEach(function (form) {
      resetFormFields(form);
    });
    resetLogTrigger();
    hide(document.getElementById("log-sheet-dialog"));
  });
})();
