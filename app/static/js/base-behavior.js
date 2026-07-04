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

  function syncEntryDateTimeForm(form, defaultToLocalNow) {
    if (!form) return;
    if (defaultToLocalNow) {
      setEntryFormToLocalNow(form);
    }
  }

  function syncEntryDateTimeForms(scope) {
    (scope || document).querySelectorAll("form").forEach(function (form) {
      if (!form.matches("[data-default-local-now]")) return;
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

  function browserTimeZone() {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch (error) {
      return "";
    }
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
    var root = scope || document;
    var nodes = [];
    if (root.matches && root.matches("[data-local-timestamp]")) {
      nodes.push(root);
    }
    root.querySelectorAll("[data-local-timestamp]").forEach(function (node) {
      nodes.push(node);
    });
    nodes.forEach(function (node) {
      var localTimestamp = formatLocalTimestamp(node.dataset.localTimestamp);
      if (localTimestamp) {
        node.textContent = localTimestamp;
      }
      node.hidden = false;
    });
  }

  function syncTagSection(section) {
    if (!section) return;
    var list = section.querySelector("[data-tag-list]");
    var expandButton = section.querySelector("[data-tags-expand]");
    var clearButton = section.querySelector("[data-tag-clear]");
    if (!list || !expandButton) return;

    var items = Array.prototype.slice.call(list.children || []);
    items.forEach(function (item) {
      item.hidden = false;
    });

    var rowTops = [];
    var overflowTop = null;
    items.forEach(function (item) {
      var top = item.offsetTop;
      if (rowTops.indexOf(top) === -1) rowTops.push(top);
      if (rowTops.length > 2 && overflowTop === null) overflowTop = top;
    });

    var hasOverflow = overflowTop !== null;
    var selectedOverflow = hasOverflow && items.some(function (item) {
      return item.offsetTop >= overflowTop && item.querySelector(".chip--tag-active");
    });

    if (selectedOverflow) {
      section.dataset.tagsExpanded = "true";
    }

    var expanded = section.dataset.tagsExpanded === "true";
    expandButton.textContent = expanded
      ? (expandButton.dataset.collapseLabel || "Show less")
      : (expandButton.dataset.expandLabel || "Show all");

    if (!hasOverflow) {
      hide(expandButton);
    } else if (expanded) {
      show(expandButton);
    } else {
      items.forEach(function (item) {
        item.hidden = item.offsetTop >= overflowTop;
      });
      show(expandButton);
    }

    if (clearButton) {
      if (selectedTagValues().length > 0) show(clearButton);
      else hide(clearButton);
    }
  }

  function syncTagSections(scope) {
    (scope || document).querySelectorAll("[data-tags-section]").forEach(function (section) {
      syncTagSection(section);
    });
  }

  function selectedTagValues() {
    var raw = document.body.dataset.selectedTags || "";
    return raw ? raw.split(",").filter(Boolean) : [];
  }

  function setSelectedTagValues(tags) {
    var unique = Array.from(new Set((tags || []).filter(Boolean))).sort();
    document.body.dataset.selectedTags = unique.join(",");
    var section = document.querySelector("[data-tags-section]");
    if (section) section.dataset.selectedTags = unique.join(",");
  }

  function applyTagChipState(section) {
    if (!section) return;
    section.dataset.selectedTags = document.body.dataset.selectedTags || "";
    var selectedTags = selectedTagValues();
    section.querySelectorAll("[data-tag-chip]").forEach(function (chip) {
      var active = selectedTags.indexOf(chip.dataset.tagName || "") !== -1;
      chip.setAttribute("aria-pressed", active ? "true" : "false");
      chip.classList.toggle("chip--tag-active", !!active);
    });
  }

  function syncFilteredEntryLists(scope) {
    var selectedTags = selectedTagValues();
    (scope || document).querySelectorAll("[data-history-entry-list]").forEach(function (list) {
      var visibleCount = 0;
      list.querySelectorAll("[data-entry-row]").forEach(function (row) {
        var tags = row.dataset.entryTags ? row.dataset.entryTags.split(",").filter(Boolean) : [];
        var matches = selectedTags.length === 0 || selectedTags.some(function (tag) {
          return tags.indexOf(tag) !== -1;
        });
        row.hidden = !matches;
        if (matches) visibleCount += 1;
      });
      var empty = list.parentElement ? list.parentElement.querySelector("[data-history-empty]") : null;
      if (empty) {
        if (visibleCount === 0) show(empty);
        else hide(empty);
      }
    });
  }

  function prefilterHistoryMarkup(markup) {
    if (selectedTagValues().length === 0 || !markup) return markup;

    var wrapper = document.createElement("div");
    wrapper.innerHTML = markup;
    syncFilteredEntryLists(wrapper);
    return wrapper.innerHTML;
  }

  function applyTagFilter(scope) {
    var section = document.querySelector("[data-tags-section]");
    if (section) applyTagChipState(section);
    syncFilteredEntryLists(scope || document);
    syncTagSections(document);
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

    var tagsExpand = event.target.closest("[data-tags-expand]");
    if (tagsExpand) {
      var tagsSection = tagsExpand.closest("[data-tags-section]");
      if (!tagsSection) return;
      tagsSection.dataset.tagsExpanded = tagsSection.dataset.tagsExpanded === "true" ? "false" : "true";
      syncTagSection(tagsSection);
      return;
    }

    var tagClear = event.target.closest("[data-tag-clear]");
    if (tagClear) {
      var clearSection = tagClear.closest("[data-tags-section]");
      if (!clearSection) return;
      setSelectedTagValues([]);
      applyTagFilter(document);
      return;
    }

    var tagChip = event.target.closest("[data-tag-chip]");
    if (tagChip) {
      var chipSection = tagChip.closest("[data-tags-section]");
      if (!chipSection) return;
      var nextTag = tagChip.dataset.tagName || "";
      var nextSelected = selectedTagValues();
      var existingIndex = nextSelected.indexOf(nextTag);
      if (existingIndex === -1) nextSelected.push(nextTag);
      else nextSelected.splice(existingIndex, 1);
      setSelectedTagValues(nextSelected);
      applyTagFilter(document);
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
    applyTagFilter(document);
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
    if (isHistoryTarget(target)) {
      applyTagFilter(target);
    } else {
      applyTagFilter(document);
    }
  });

  document.body.addEventListener("htmx:afterSettle", function (event) {
    var target = event.detail.target;
    syncLocalTimestamps(target);
    if (isHistoryTarget(target)) {
      applyTagFilter(document);
    }
  });

  document.body.addEventListener("htmx:load", function (event) {
    syncLocalTimestamps(event.detail.elt || document);
  });

  window.addEventListener("resize", function () {
    applyTagFilter(document);
  });

  document.body.addEventListener("dialog:open", function (event) {
    syncBoundedTextareas(event.target);
  });

  document.body.addEventListener("htmx:configRequest", function (event) {
    var form = event.detail.elt ? event.detail.elt.closest("form") : null;
    syncEntryDateTimeForm(form, false);
    if (form && form.matches("[data-comment-form]") && event.detail.parameters) {
      event.detail.parameters.comment_timezone = browserTimeZone();
    } else if (form && form.querySelector('input[name="date"]') && event.detail.parameters) {
      event.detail.parameters.entry_timezone = browserTimeZone();
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

  document.body.addEventListener("htmx:beforeSwap", function (event) {
    var target = event.detail.target;
    if (!isHistoryTarget(target)) return;
    event.detail.serverResponse = prefilterHistoryMarkup(event.detail.serverResponse);
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
