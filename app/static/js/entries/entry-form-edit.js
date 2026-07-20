(function () {
  "use strict";

  function initEditForm(form) {
    if (form.hasAttribute("data-edit-init")) return;
    form.setAttribute("data-edit-init", "true");

    var origDate = form.getAttribute("data-original-date");
    var origTime = form.getAttribute("data-original-time");
    var origMemo = form.getAttribute("data-original-memo");
    var origNoTime = form.getAttribute("data-original-no-time");
    if (origDate === null && origTime === null && origMemo === null && origNoTime === null) return;

    var submitBtn = form.querySelector('button[type="submit"]');
    if (!submitBtn) return;

    function checkChanged() {
      var changed = false;
      var dateInput = form.querySelector('input[name="date"]');
      var timeInput = form.querySelector('input[name="time"]');
      var noTimeCb = form.querySelector('input[name="no_time"]');
      var memoInput = form.querySelector('textarea[name="memo"]');

      if (dateInput && dateInput.value !== origDate) changed = true;
      if (timeInput && timeInput.value !== origTime) changed = true;
      if (memoInput && memoInput.value !== origMemo) changed = true;
      if (noTimeCb && String(noTimeCb.checked) !== origNoTime) changed = true;

      submitBtn.disabled = !changed;
    }

    form.addEventListener("input", checkChanged);
    form.addEventListener("change", checkChanged);

    checkChanged();
  }

  function initEditForms(scope) {
    (scope || document).querySelectorAll("form[data-original-date]").forEach(initEditForm);
  }

  document.addEventListener("DOMContentLoaded", function () {
    initEditForms(document);
  });

  function initOnHtmxEvent() {
    initEditForms(document);
  }

  document.body.addEventListener("htmx:afterSwap", initOnHtmxEvent);
  document.body.addEventListener("htmx:afterSettle", initOnHtmxEvent);
})();
