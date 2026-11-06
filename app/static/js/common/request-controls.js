window.MushinRequestLoading = (function () {
  "use strict";
  const active = new Map();
  function restore(node, state) {
    node.classList.remove("request-loading");
    node.style.removeProperty("--request-loading-color");
    if (state.color) node.style.setProperty("--request-loading-color", state.color);
    for (const [attribute, value] of Object.entries(state.attributes)) {
      if (value === null) node.removeAttribute(attribute);
      else node.setAttribute(attribute, value);
    }
  }
  function start(control, form) {
    if (!control) return function () {};
    let state = active.get(control);
    if (!state) {
      state = {
        count: 0, form: form,
        color: control.style.getPropertyValue("--request-loading-color"),
        attributes: {
          "aria-busy": control.getAttribute("aria-busy"),
          "aria-disabled": control.getAttribute("aria-disabled"),
        },
      };
      active.set(control, state);
      control.style.setProperty("--request-loading-color", getComputedStyle(control).color);
      control.classList.add("request-loading");
      control.setAttribute("aria-busy", "true");
      control.setAttribute("aria-disabled", "true");
    }
    state.count++;
    let finished = false;
    return function () {
      if (finished) return;
      finished = true;
      if (--state.count || active.get(control) !== state) return;
      restore(control, state);
      active.delete(control);
    };
  }
  function formBusy(form) {
    return form && Array.from(active.values()).some(state => state.form === form);
  }
  document.addEventListener("click", function (event) {
    const control = event.target.closest("button, a");
    if (control && (active.has(control) || (control.type === "submit" && formBusy(control.form)))) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
  document.addEventListener("submit", function (event) {
    if (!formBusy(event.target)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
  }, true);
  window.addEventListener("pageshow", function () {
    active.forEach(function (state, control) { restore(control, state); });
    active.clear();
  });
  return {
    start: start,
    clean: function (original, copy) {
      const state = active.get(original);
      if (state) restore(copy, state);
    },
  };
})();
