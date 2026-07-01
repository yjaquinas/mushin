// Field-stats section: inject current data-period into HTMX request params.

(function () {
  "use strict";

  document.body.addEventListener("htmx:configRequest", function (event) {
    var elt = event.detail.elt;
    if (!elt || !elt.id || !elt.id.startsWith("field-stats-")) return;
    event.detail.parameters.period = elt.dataset.period || "month";
  });
})();
