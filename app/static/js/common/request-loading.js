(function () {
  "use strict";

  const active = new Map();
  const submitters = new WeakMap();

  function start(button, form) {
    if (!button || active.has(button)) return;
    const previous = {
      busy: button.getAttribute("aria-busy"),
      disabled: button.getAttribute("aria-disabled"),
      form: form,
    };
    active.set(button, previous);
    button.style.setProperty("--request-loading-color", getComputedStyle(button).color);
    button.classList.add("request-loading");
    button.setAttribute("aria-busy", "true");
    // Keep successful submitter values and existing disabled-state logic intact.
    button.setAttribute("aria-disabled", "true");
  }

  function stop(button) {
    const previous = active.get(button);
    if (!previous) return;
    button.classList.remove("request-loading");
    button.style.removeProperty("--request-loading-color");
    for (const [attribute, value] of [
      ["aria-busy", previous.busy], ["aria-disabled", previous.disabled],
    ]) {
      if (value === null) button.removeAttribute(attribute);
      else button.setAttribute(attribute, value);
    }
    active.delete(button);
  }

  function formBusy(form) {
    return form && Array.from(active.values()).some(state => state.form === form);
  }

  document.addEventListener("click", function (event) {
    const button = event.target.closest("button");
    if (button && (active.has(button) || (button.type === "submit" && formBusy(button.form)))) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);

  document.addEventListener("submit", function (event) {
    const form = event.target;
    if (formBusy(form)) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    const button = event.submitter || form.querySelector("button[type=submit], button:not([type])");
    submitters.set(form, button);
    // HTMX handles its own lifecycle; native forms stay busy until navigation.
    queueMicrotask(function () {
      if (!event.defaultPrevented && form.method !== "dialog") start(button, form);
    });
  }, true);

  document.body.addEventListener("htmx:beforeSend", function (event) {
    const source = event.detail.elt;
    const form = source.matches("form") ? source : null;
    const button = source.closest("button") || (form && (
      submitters.get(form) || form.querySelector("button[type=submit], button:not([type])")
    ));
    if (!button) return;
    start(button, form);
    // loadend also runs for errors, timeouts, aborts, and removed request elements.
    event.detail.xhr.addEventListener("loadend", function () { stop(button); }, { once: true });
  });

  window.addEventListener("pageshow", function () {
    active.forEach(function (_, button) { stop(button); });
  });
})();
