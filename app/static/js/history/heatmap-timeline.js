(function () {
  "use strict";

  function hide(element) {
    if (element) element.hidden = true;
  }

  function show(element) {
    if (element) element.hidden = false;
  }

  function initTimeline(timeline) {
    if (!timeline || timeline.dataset.heatmapInitialized === "true") return;
    timeline.dataset.heatmapInitialized = "true";

    var scroll = timeline.querySelector("[data-heatmap-scroll]");
    var nowButton = timeline.querySelector("[data-heatmap-now]");
    if (!scroll || !nowButton) return;

    function atNow() {
      return scroll.scrollLeft >= scroll.scrollWidth - scroll.clientWidth - 4;
    }

    function syncNowButton() {
      if (atNow()) hide(nowButton);
      else show(nowButton);
    }

    scroll.addEventListener("scroll", syncNowButton, { passive: true });
    nowButton.addEventListener("click", function () {
      scroll.scrollTo({ left: scroll.scrollWidth, behavior: "smooth" });
    });

    requestAnimationFrame(function () {
      scroll.scrollLeft = scroll.scrollWidth;
      syncNowButton();
    });
  }

  function initTimelines(scope) {
    (scope || document).querySelectorAll("[data-heatmap-timeline]").forEach(initTimeline);
  }

  document.addEventListener("DOMContentLoaded", function () { initTimelines(document); });
  document.body.addEventListener("htmx:afterSwap", function (event) { initTimelines(event.detail.target); });
})();
