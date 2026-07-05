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
      tags.apply(document);
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
    tags.apply(document);
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

  window.addEventListener("resize", function () {
    tags.apply(document);
  });
})();
