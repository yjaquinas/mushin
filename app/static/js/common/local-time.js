(function () {
  "use strict";

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

  function syncLocalTimestamps(scope) {
    var root = scope || document;
    var nodes = [];
    if (root.matches && root.matches("[data-local-timestamp]")) nodes.push(root);
    root.querySelectorAll("[data-local-timestamp]").forEach(function (node) {
      nodes.push(node);
    });
    nodes.forEach(function (node) {
      var localTimestamp = formatLocalTimestamp(node.dataset.localTimestamp);
      if (localTimestamp) node.textContent = localTimestamp;
      node.hidden = false;
    });
  }

  syncLocalTimestamps(document);

  document.addEventListener("DOMContentLoaded", function () {
    syncLocalTimestamps(document);
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    syncLocalTimestamps(event.detail.target);
  });

  document.body.addEventListener("htmx:afterSettle", function (event) {
    syncLocalTimestamps(event.detail.target);
  });

  document.body.addEventListener("htmx:load", function (event) {
    syncLocalTimestamps(event.detail.elt || document);
  });

  document.body.addEventListener("tab:panel-rendered", function (event) {
    syncLocalTimestamps(event.detail.panel || document);
  });

  document.body.addEventListener("htmx:configRequest", function (event) {
    var form = event.detail.elt ? event.detail.elt.closest("form") : null;
    if (form && form.matches("[data-comment-form]") && event.detail.parameters) {
      event.detail.parameters.comment_timezone = browserTimeZone();
    } else if (form && form.querySelector('input[name="date"]') && event.detail.parameters) {
      event.detail.parameters.entry_timezone = browserTimeZone();
    }
  });
})();
