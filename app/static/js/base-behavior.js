(function () {
  "use strict";

  function hide(el) {
    if (el) el.setAttribute("hidden", "");
  }

  function show(el) {
    if (el) el.removeAttribute("hidden");
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

  function closeInlineLogSheet() {
    hide(document.getElementById("log-panel"));
    var panel = document.getElementById("log-panel");
    if (panel) panel.innerHTML = "";
    var trigger = document.querySelector("[data-log-trigger]");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
    var icon = document.querySelector('[id^="log-trigger-icon-"]');
    if (icon) icon.classList.remove("rotate-45");
  }

  function resetFormFields(form) {
    if (!form) return;
    form.reset();
    form.querySelectorAll("[data-toggle-time]").forEach(function (checkbox) {
      var timeBlock = checkbox.closest("label");
      timeBlock = timeBlock ? timeBlock.nextElementSibling : null;
      if (timeBlock) {
        if (checkbox.checked) {
          show(timeBlock);
        } else {
          hide(timeBlock);
        }
      }
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
      var panel = document.getElementById("log-panel");
      var iconEl = document.querySelector('[id^="log-trigger-icon-"]');
      if (open) {
        logTrigger.setAttribute("aria-expanded", "false");
        if (panel) {
          hide(panel);
          panel.innerHTML = "";
        }
        if (iconEl) iconEl.classList.remove("rotate-45");
        event.preventDefault();
        return;
      }

      logTrigger.setAttribute("aria-expanded", "true");
      if (panel) show(panel);
      if (iconEl) iconEl.classList.add("rotate-45");
      return;
    }
  });

  document.addEventListener("change", function (event) {
    if (event.target.matches('#visibility-form input[name="visibility"]')) {
      syncVisibilityForm();
      return;
    }

    if (!event.target.matches("[data-toggle-time]")) return;
    var timeBlock = event.target.closest("label");
    timeBlock = timeBlock ? timeBlock.nextElementSibling : null;
    if (!timeBlock) return;
    if (event.target.checked) {
      show(timeBlock);
    } else {
      hide(timeBlock);
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-flash-dismiss]").forEach(function (flash) {
      window.setTimeout(function () {
        flash.remove();
      }, 5000);
    });
    syncVisibilityForm();
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    var target = event.detail.target;
    syncHistoryFocus(target);
    syncHomeCards(target);
    syncVisibilityForm();
  });

  document.body.addEventListener("htmx:afterRequest", function (event) {
    var elt = event.detail.elt;
    if (elt && elt.id === "logout-button" && event.detail.successful) {
      window.location.href = "/";
      return;
    }

    if (elt && elt.id === "theme-toggle" && event.detail.successful) {
      window.setTimeout(function () {
        window.location.reload();
      }, 100);
      return;
    }

    if (elt && elt.matches("[data-log-trigger]")) {
      var panel = document.getElementById("log-panel");
      if (panel) show(panel);
      var icon = document.querySelector('[id^="log-trigger-icon-"]');
      if (icon) icon.classList.remove("rotate-45");
    }
  });

  document.body.addEventListener("log-saved", function () {
    document.querySelectorAll("#log-sheet-inline form, #log-sheet-dialog form").forEach(function (form) {
      resetFormFields(form);
    });
    closeInlineLogSheet();
    hide(document.getElementById("log-sheet-dialog"));
  });
})();
