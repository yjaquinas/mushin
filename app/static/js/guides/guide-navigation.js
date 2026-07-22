(function () {
  "use strict";

  function hasSameOriginReferrer() {
    if (!document.referrer) return false;
    try {
      return new URL(document.referrer).origin === window.location.origin;
    } catch (_error) {
      return false;
    }
  }

  document.addEventListener("click", function (event) {
    var backLink = event.target.closest("[data-guide-back]");
    if (!backLink || !hasSameOriginReferrer()) return;
    event.preventDefault();
    window.history.back();
  });
})();
