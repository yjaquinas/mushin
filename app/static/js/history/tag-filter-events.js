(function () {
  "use strict";

  var tags = window.MushinTagFilter;
  if (!tags) return;

  document.addEventListener("click", function (event) {
    var tagsExpand = event.target.closest("[data-tags-expand]");
    if (tagsExpand) {
      var tagsSection = tagsExpand.closest("[data-tags-section]");
      if (!tagsSection) return;
      tagsSection.dataset.tagsExpanded = tagsSection.dataset.tagsExpanded === "true" ? "false" : "true";
      tags.syncSection(tagsSection);
      return;
    }

    if (event.target.closest("[data-tag-clear]")) {
      tags.setSelected([]);
      if (!tags.reloadAllHistory()) tags.apply(document);
      return;
    }

    var tagChip = event.target.closest("[data-tag-chip]");
    if (!tagChip) return;
    var nextSelected = tags.selected();
    var tagName = tagChip.dataset.tagName || "";
    var existingIndex = nextSelected.indexOf(tagName);
    if (existingIndex === -1) nextSelected.push(tagName);
    else nextSelected.splice(existingIndex, 1);
    tags.setSelected(nextSelected);
    if (!tags.reloadAllHistory()) tags.apply(document);
  }, true);

  document.addEventListener("DOMContentLoaded", function () {
    tags.apply(document);
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    tags.apply(tags.isHistoryTarget(event.detail.target) ? event.detail.target : document);
  });

  document.body.addEventListener("htmx:afterSettle", function (event) {
    if (tags.isHistoryTarget(event.detail.target)) tags.apply(document);
  });

  document.body.addEventListener("htmx:beforeSwap", function (event) {
    if (tags.isHistoryTarget(event.detail.target)) {
      event.detail.serverResponse = tags.prefilterHistoryMarkup(event.detail.serverResponse);
    }
  });

  document.body.addEventListener("htmx:configRequest", function (event) {
    var parameters = event.detail.parameters || {};
    var period = parameters.period;
    if (!period && event.detail.path) {
      period = new URL(event.detail.path, window.location.origin).searchParams.get("period");
    }
    if (period === "all") parameters.tags = tags.selected().join(",");
  });

  window.addEventListener("resize", function () {
    tags.apply(document);
  });
})();
