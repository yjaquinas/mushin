(function () {
  "use strict";

  function syncViewport() {
    var viewport = window.visualViewport;
    var style = document.documentElement.style;
    style.setProperty("--entry-viewport", (viewport?.height || window.innerHeight) + "px");
    style.setProperty("--entry-viewport-top", (viewport?.offsetTop || 0) + "px");
  }

  window.visualViewport?.addEventListener("resize", syncViewport);
  window.visualViewport?.addEventListener("scroll", syncViewport);
  window.addEventListener("resize", syncViewport);
  document.body.addEventListener("dialog:open", function (event) {
    if (event.target.querySelector("[data-entry-dialog]")) syncViewport();
  });
  syncViewport();
})();
