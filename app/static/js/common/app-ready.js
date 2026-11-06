window.MushinAppReady = (function () {
  "use strict";
  const callbacks = [];
  const bootstrap = document.documentElement.hasAttribute("data-bootstrap-pending");
  let ready = false;
  let failed = false;

  window.addEventListener("error", function (event) {
    if (!bootstrap || ready) return;
    if (event.target instanceof HTMLScriptElement || event instanceof ErrorEvent) failed = true;
  }, true);

  function complete() {
    if (ready) return;
    if (bootstrap && failed) throw new Error("Startup dependency failed");
    while (callbacks.length) {
      const callback = callbacks.shift();
      try {
        callback();
      } catch (error) {
        if (bootstrap) {
          failed = true;
          throw error;
        }
        window.setTimeout(function () { throw error; }, 0);
      }
    }
    ready = true;
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!bootstrap) window.setTimeout(complete, 0);
  }, { once: true });

  return {
    when(callback) {
      if (ready) callback();
      else callbacks.push(callback);
    },
    complete: complete,
    get failed() { return failed; },
    get ready() { return ready; },
  };
})();
