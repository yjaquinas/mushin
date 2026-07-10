(function () {
  "use strict";

  function hide(el) {
    if (el) el.setAttribute("hidden", "");
  }

  function show(el) {
    if (el) el.removeAttribute("hidden");
  }

  function htmxTrigger(event) {
    return event.detail && event.detail.requestConfig ? event.detail.requestConfig.elt : event.detail.elt;
  }

  function isHistoryPeriodSwitch(trigger) {
    return !!(trigger && trigger.matches('[role="tab"][id^="activity-tab-history-"]'));
  }

  function isHistoryTarget(target) {
    return !!(target && target.id && target.id.startsWith("activity-section-history-"));
  }

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

  document.addEventListener("click", function (event) {
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
      setEntryExpandedState(entryCollapse.getAttribute("data-entry-id"), false);
      return;
    }

    var entryToggle = event.target.closest("[data-entry-toggle]");
    if (!entryToggle) return;
    var entryId = entryToggle.getAttribute("data-entry-id");
    var expanded = entryToggle.getAttribute("aria-expanded") === "true";
    setEntryExpandedState(entryId, !expanded);
    if (!expanded) maybeLoadEntryComments(entryId);
    event.preventDefault();
  }, true);

  function scrollToExpandedEntry() {
    var toggle = document.querySelector("[data-entry-toggle][aria-expanded='true']");
    if (toggle) {
      var entryId = toggle.getAttribute("data-entry-id");
      var row = document.getElementById("entry-row-" + entryId);
      if (row) row.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    syncExpandedEntries(document);
    scrollToExpandedEntry();
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    var target = event.detail.target;
    if (isHistoryTarget(target) && isHistoryPeriodSwitch(htmxTrigger(event))) {
      collapseExpandedEntries(target);
    } else {
      syncExpandedEntries(target);
    }
  });

  document.body.addEventListener("htmx:beforeRequest", function (event) {
    var trigger = htmxTrigger(event);
    if (!isHistoryPeriodSwitch(trigger)) return;
    var historyRoot = trigger.closest('[id^="activity-section-history-"]');
    if (historyRoot) collapseExpandedEntries(historyRoot);
  });
})();
