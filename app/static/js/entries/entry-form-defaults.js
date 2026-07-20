(function () {
  "use strict";

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
    var timeInput = form.querySelector('input[name="time"]');
    if (timeInput) timeInput.value = localTimeValue(now);
  }

  function syncEntryDateTimeForms(scope) {
    (scope || document).querySelectorAll("form[data-default-local-now]").forEach(setEntryFormToLocalNow);
  }

  function syncNoTimeToggle(scope) {
    (scope || document).querySelectorAll('input[type="checkbox"][name="no_time"]').forEach(function (cb) {
      if (cb.hasAttribute("data-no-time-init")) return;
      cb.setAttribute("data-no-time-init", "true");
      var form = cb.closest("form");
      var timeInput = form && form.querySelector('input[type="time"][name="time"]');
      if (!timeInput) return;
      function toggle() {
        if (cb.checked) {
          timeInput.setAttribute("hidden", "");
        } else {
          timeInput.removeAttribute("hidden");
        }
      }
      toggle();
      cb.addEventListener("change", toggle);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    syncEntryDateTimeForms(document);
    syncNoTimeToggle(document);
  });

  document.body.addEventListener("htmx:afterSwap", function () {
    syncEntryDateTimeForms(document);
    syncNoTimeToggle(document);
  });
})();
