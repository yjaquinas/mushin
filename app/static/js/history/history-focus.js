(function () {
  "use strict";

  function syncHistoryFocus(target) {
    if (!target || !target.id || !target.id.startsWith("activity-section-history-")) return;
    var focusTarget = target.querySelector("[data-history-focus]");
    if (focusTarget) focusTarget.focus();

    var activityId = target.id.slice("activity-section-history-".length);
    var fieldStats = document.getElementById("activity-section-field-stats-" + activityId);
    if (!fieldStats || !focusTarget || !focusTarget.dataset.period) return;
    fieldStats.dataset.period = focusTarget.dataset.period;
  }

  document.body.addEventListener("htmx:afterSwap", function (event) {
    syncHistoryFocus(event.detail.target);
  });
})();
