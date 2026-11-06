window.MushinRegionLoading = (function () {
  "use strict";
  const statuses = new Map();
  const targets = new Map();
  const sources = new Map();
  function statusFor(source, target) {
    const selector = source.getAttribute("data-loading-status");
    if (selector) return document.querySelector(selector);
    return source.querySelector("[data-request-status]") ||
      (target && target.querySelector("[data-request-status]"));
  }
  function startTarget(target) {
    if (!target) return function () {};
    const state = targets.get(target) || { count: 0, busy: target.getAttribute("aria-busy") };
    targets.set(target, state);
    state.count++;
    target.setAttribute("aria-busy", "true");
    return function () {
      if (--state.count) return;
      if (state.busy === null) target.removeAttribute("aria-busy");
      else target.setAttribute("aria-busy", state.busy);
      targets.delete(target);
    };
  }
  document.body.addEventListener("htmx:beforeSend", function (event) {
    const { elt: source, target, xhr } = event.detail;
    const config = event.detail.requestConfig;
    // Read failures can be retried here; writes use their submit control.
    if (config.verb.toLowerCase() !== "get") return;
    const status = statusFor(source, target);
    if (!status) return;
    const finishTarget = startTarget(target);
    const state = statuses.get(status) || { count: 0, version: 0 };
    statuses.set(status, state);
    const version = ++state.version;
    state.source = source;
    state.retry = function () {
      window.htmx.ajax("GET", config.path, {
        source: source, target: target,
        swap: source.closest("[hx-swap]")?.getAttribute("hx-swap") || "outerHTML",
        values: config.parameters,
      });
    };
    state.count++;
    state.failed = false;
    status.hidden = false;
    status.querySelector("[data-request-pending]").hidden = false;
    status.querySelector("[data-request-failure]").hidden = true;
    source.setAttribute("data-request-pending-source", "");
    sources.set(source, (sources.get(source) || 0) + 1);
    let aborted = false;
    xhr.addEventListener("abort", function () { aborted = true; }, { once: true });
    xhr.addEventListener("loadend", function () {
      finishTarget();
      const remaining = sources.get(source) - 1;
      if (remaining) sources.set(source, remaining);
      else {
        sources.delete(source);
        source.removeAttribute("data-request-pending-source");
      }
      if (version === state.version) state.failed = !aborted && (xhr.status < 200 || xhr.status >= 400);
      if (--state.count) return;
      status.hidden = !state.failed;
      status.querySelector("[data-request-pending]").hidden = true;
      status.querySelector("[data-request-failure]").hidden = !state.failed;
      if (!state.failed || !status.isConnected) statuses.delete(status);
    }, { once: true });
  });
  document.addEventListener("click", function (event) {
    const retry = event.target.closest("[data-request-retry]");
    if (!retry) return;
    const state = statuses.get(retry.closest("[data-request-status]"));
    if (!state || state.count || !state.source.isConnected) return;
    state.retry();
  });
  document.body.addEventListener("tab:panel-rendered", function (event) {
    event.detail.panel.querySelectorAll("[data-request-pending-source]").forEach(function (source) {
      source.removeAttribute("data-request-pending-source");
      if (source.hasAttribute("hx-get") && !sources.has(source) &&
          !/(^|,\s*)(load|revealed)(\s|,|$)/.test(source.getAttribute("hx-trigger") || "")) {
        window.htmx.trigger(source, "request-retry");
      }
    });
    for (const status of statuses.keys()) {
      if (!status.isConnected) statuses.delete(status);
    }
  });
  return {
    clean: function (original, copy) {
      const target = targets.get(original);
      if (target) {
        if (target.busy === null) copy.removeAttribute("aria-busy");
        else copy.setAttribute("aria-busy", target.busy);
      }
      if (original.hasAttribute("data-request-status")) copy.hidden = true;
    },
  };
})();
