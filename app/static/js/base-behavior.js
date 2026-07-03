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

  window.showToast = showToast;

  function setEntryExpandedState(entryId, open, root) {
    if (!entryId) return;
    (root || document).querySelectorAll('[data-entry-toggle][data-entry-id="' + entryId + '"]').forEach(function (button) {
      button.setAttribute("aria-expanded", open ? "true" : "false");

      var summary = button.querySelector("[data-entry-summary]");
      var time = button.querySelector("[data-entry-time]");
      if (summary) {
        if (open) hide(summary);
        else show(summary);
      }
      if (time) {
        if (open) show(time);
        else hide(time);
      }

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

    (root || document).querySelectorAll("#entry-expanded-" + entryId).forEach(function (panel) {
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
      setEntryExpandedState(entryId, open, root || document);
      if (open) maybeLoadEntryComments(entryId);
    });
  }

  function collapseExpandedEntries(root) {
    (root || document).querySelectorAll("[data-entry-toggle]").forEach(function (button) {
      var entryId = button.getAttribute("data-entry-id");
      setEntryExpandedState(entryId, false, root || document);
    });
  }

  function isHistoryPeriodSwitch(trigger) {
    return !!(trigger && trigger.matches('[role="tab"][id^="history-tab-"]'));
  }

  function isHistoryTarget(target) {
    return !!(target && target.id && target.id.startsWith("history-"));
  }

  function htmxTrigger(event) {
    return event.detail && event.detail.requestConfig ? event.detail.requestConfig.elt : event.detail.elt;
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

  function syncAccountEmailForm() {
    var form = document.getElementById("account-email-form");
    if (!form) return;
    var input = form.querySelector('input[name="email"]');
    var saveButton = form.querySelector('button[type="submit"]');
    if (!input || !saveButton) return;
    var currentValue = (form.dataset.currentEmail || "").trim();
    var enteredValue = input.value.trim();
    saveButton.disabled = enteredValue === currentValue;
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
    syncEntryDateTimeForm(form, form.matches("[data-default-local-now]"));
  }

  function padDatePart(value) {
    return String(value).padStart(2, "0");
  }

  function localDateValue(date) {
    return [
      date.getFullYear(),
      padDatePart(date.getMonth() + 1),
      padDatePart(date.getDate())
    ].join("-");
  }

  function localTimeValue(date) {
    return [padDatePart(date.getHours()), padDatePart(date.getMinutes())].join(":");
  }

  function setEntryFormToLocalNow(form) {
    var now = new Date();
    var dateInput = form.querySelector('input[name="date"]');
    var timeInput = form.querySelector('input[name="time"]');
    var noTime = form.querySelector("[data-toggle-time]");
    if (dateInput) dateInput.value = localDateValue(now);
    if (timeInput) {
      timeInput.value = localTimeValue(now);
      show(timeInput);
      timeInput.disabled = false;
    }
    if (noTime) noTime.checked = false;
  }

  function setEntryFormToLocalDate(form, date) {
    var dateInput = form.querySelector('input[name="date"]');
    var timeInput = form.querySelector('input[name="time"]');
    if (dateInput) dateInput.value = localDateValue(date);
    if (timeInput && !timeInput.disabled) timeInput.value = localTimeValue(date);
  }

  function localizeExistingEntryDateTime(form, hidden) {
    if (!hidden || !hidden.dataset.existingOccurredAt || form.dataset.entryDateTimeLocalized) return;

    var date = new Date(hidden.dataset.existingOccurredAt);
    if (Number.isNaN(date.getTime())) return;

    setEntryFormToLocalDate(form, date);
    form.dataset.entryDateTimeLocalized = "true";
  }

  function entryDateFromForm(form) {
    var dateInput = form.querySelector('input[name="date"]');
    if (!dateInput || !dateInput.value) return null;

    var parts = dateInput.value.split("-");
    if (parts.length !== 3) return null;

    var year = parseInt(parts[0], 10);
    var month = parseInt(parts[1], 10);
    var day = parseInt(parts[2], 10);
    if (!year || !month || !day) return null;

    var timeInput = form.querySelector('input[name="time"]');
    var timeValue = timeInput && !timeInput.disabled ? timeInput.value : "";
    var hour = 0;
    var minute = 0;

    if (timeValue) {
      var timeParts = timeValue.split(":");
      hour = parseInt(timeParts[0], 10);
      minute = parseInt(timeParts[1], 10);
      if (Number.isNaN(hour) || Number.isNaN(minute)) return null;
    }

    return new Date(year, month - 1, day, hour, minute, 0, 0);
  }

  function syncEntryDateTimeForm(form, defaultToLocalNow) {
    if (!form) return;
    var hidden = form.querySelector("[data-occurred-at-utc]");
    if (!hidden) return;

    if (defaultToLocalNow) {
      setEntryFormToLocalNow(form);
    } else {
      localizeExistingEntryDateTime(form, hidden);
    }

    var localDate = entryDateFromForm(form);
    hidden.value = localDate && !Number.isNaN(localDate.getTime()) ? localDate.toISOString() : "";
  }

  function syncEntryDateTimeForms(scope) {
    (scope || document).querySelectorAll("form").forEach(function (form) {
      if (!form.querySelector("[data-occurred-at-utc]")) return;
      syncEntryDateTimeForm(form, form.matches("[data-default-local-now]"));
    });
  }

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

  function formatLocalTimestamp(timestamp) {
    if (!timestamp) return "";

    var date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) return "";

    var parts = new Intl.DateTimeFormat("en-US", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23"
    }).formatToParts(date);

    var values = {};
    parts.forEach(function (part) {
      values[part.type] = part.value;
    });

    if (!values.year || !values.month || !values.day || !values.hour || !values.minute) return "";
    var hour = parseInt(values.hour, 10);
    var hour12 = hour % 12 || 12;
    var ampm = hour < 12 ? "AM" : "PM";
    return values.year + "-" + values.month + "-" + values.day + " " + hour12 + ":" + values.minute + " " + ampm;
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

  function syncLocalTimestamps(scope) {
    (scope || document).querySelectorAll("[data-local-timestamp]").forEach(function (node) {
      var localTimestamp = formatLocalTimestamp(node.dataset.localTimestamp);
      if (localTimestamp) {
        node.textContent = localTimestamp;
      }
    });
  }

  document.addEventListener("click", function (event) {
    var addOpen = event.target.closest("[data-add-activity-open]");
    if (addOpen) {
      hide(addOpen);
      show(document.getElementById("add-activity-form"));
      var nameInput = document.getElementById("activity-name");
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
    syncEntryDateTimeForm(event.target.closest("form"), false);
  });

  document.addEventListener("input", function (event) {
    if (event.target.matches('#account-email-form input[name="email"]')) {
      syncAccountEmailForm();
      return;
    }

    if (event.target.matches('[data-comment-form] textarea[name="body"]')) {
      enforceBoundedTextareaLimits(event.target);
      autosizeTextarea(event.target);
      updateBoundedTextareaCharCount(event.target);
      return;
    }

    if (event.target.matches('input[name="date"], input[name="time"]')) {
      syncEntryDateTimeForm(event.target.closest("form"), false);
      return;
    }

    if (!event.target.matches("[data-bounded-textarea]")) return;
    enforceBoundedTextareaLimits(event.target);
    autosizeTextarea(event.target);
    updateBoundedTextareaCharCount(event.target);
  });

  document.addEventListener("submit", function (event) {
    syncEntryDateTimeForm(event.target.closest("form"), false);

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
    syncVisibilityForm();
    syncAccountEmailForm();
    syncExpandedEntries(document);
    syncCommentFormState(document);
    syncBoundedTextareas(document);
    syncLocalTimestamps(document);
    syncEntryDateTimeForms(document);
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    var target = event.detail.target;
    syncHistoryFocus(target);
    syncHomeCards(target);
    syncAccountEmailForm();
    syncVisibilityForm();
    if (isHistoryTarget(target) && isHistoryPeriodSwitch(htmxTrigger(event))) {
      collapseExpandedEntries(target);
    } else {
      syncExpandedEntries(target);
    }
    syncCommentFormState(target);
    syncBoundedTextareas(target);
    syncLocalTimestamps(target);
    syncEntryDateTimeForms(target);
  });

  document.body.addEventListener("dialog:open", function (event) {
    syncBoundedTextareas(event.target);
  });

  document.body.addEventListener("htmx:configRequest", function (event) {
    var form = event.detail.elt ? event.detail.elt.closest("form") : null;
    syncEntryDateTimeForm(form, false);
    var hidden = form ? form.querySelector("[data-occurred-at-utc]") : null;
    if (hidden && event.detail.parameters) {
      event.detail.parameters.occurred_at_utc = hidden.value;
    }
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

  document.body.addEventListener("htmx:beforeRequest", function (event) {
    var trigger = htmxTrigger(event);
    if (!isHistoryPeriodSwitch(trigger)) return;
    var historyRoot = trigger.closest('[id^="history-"]');
    if (!historyRoot) return;
    collapseExpandedEntries(historyRoot);
  });

  document.body.addEventListener("log-saved", function () {
    document.querySelectorAll("#log-sheet-dialog form").forEach(function (form) {
      resetFormFields(form);
    });
    resetLogTrigger();
    hide(document.getElementById("log-sheet-dialog"));
  });
})();
