(function () {
  "use strict";
  const submitters = new WeakMap();
  document.addEventListener("submit", function (event) {
    if (event.defaultPrevented) return;
    const form = event.target;
    const control = event.submitter || form.querySelector("button[type=submit], button:not([type])");
    submitters.set(form, control);
    window.setTimeout(function () {
      if (!event.defaultPrevented && form.method !== "dialog") {
        window.MushinRequestLoading.start(control, form);
      }
    }, 0);
  }, true);
  document.body.addEventListener("htmx:beforeSend", function (event) {
    const source = event.detail.elt;
    const form = source.matches("form") ? source : null;
    const control = source.closest("button, a") || (form && (
      submitters.get(form) || form.querySelector("button[type=submit], button:not([type])")
    ));
    if (!control) return;
    const finish = window.MushinRequestLoading.start(control, form);
    event.detail.xhr.addEventListener("loadend", finish, { once: true });
  });
})();
