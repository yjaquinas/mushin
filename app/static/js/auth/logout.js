(function () {
  "use strict";

  document.body.addEventListener("htmx:afterRequest", function (event) {
    var elt = event.detail.elt;
    if (elt && elt.id === "settings-button-logout" && event.detail.successful &&
        !event.detail.xhr.getResponseHeader("HX-Redirect")) {
      window.MushinPageLoading.start();
      window.location.href = "/";
    }
  });
})();
