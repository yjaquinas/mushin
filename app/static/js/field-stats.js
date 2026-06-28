// Field-stats section: inject current data-period into HTMX request params.
//
// The period value is kept in sync by hx-on::after-swap in history.html.jinja2.
// hx-vals on the field-stats div reads data-period at request time.
// This listener is a backup to ensure the period is always present.

(function () {
  "use strict";

  var el = document.getElementById("field-stats");
  if (!el) return;

  // Inject current period into every request from this element.
  document.body.addEventListener("htmx:configRequest", function (event) {
    if (event.detail.target !== el) return;
    event.detail.parameters["period"] = el.dataset.period;
  });
})();
