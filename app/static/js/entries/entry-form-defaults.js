(function () {
  "use strict";

  function hide(el) {
    if (el) el.setAttribute("hidden", "");
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
    if (dateInput) dateInput.value = localDateValue(now);
    if (timeInput) timeInput.value = localTimeValue(now);
  }

  function syncEntryDateTimeForms(scope) {
    (scope || document).querySelectorAll("form[data-default-local-now]").forEach(setEntryFormToLocalNow);
  }

  function resetLogTrigger() {
    var trigger = document.querySelector("[data-log-trigger]");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
  }

  function resetFormFields(form) {
    if (!form) return;
    form.reset();
    if (form.matches("[data-default-local-now]")) setEntryFormToLocalNow(form);
  }

  document.addEventListener("DOMContentLoaded", function () {
    syncEntryDateTimeForms(document);
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    syncEntryDateTimeForms(event.detail.target);
  });

  document.body.addEventListener("log-saved", function () {
    document.querySelectorAll("#log-sheet-dialog form").forEach(resetFormFields);
    resetLogTrigger();
    hide(document.getElementById("log-sheet-dialog"));
  });
})();
