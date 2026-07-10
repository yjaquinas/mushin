(function () {
  "use strict";

  function hide(el) {
    if (el) el.setAttribute("hidden", "");
  }

  function show(el) {
    if (el) el.removeAttribute("hidden");
  }

  function isHistoryTarget(target) {
    return !!(target && target.id && target.id.startsWith("activity-section-history-"));
  }

  function selectedTagValues() {
    var raw = document.body.dataset.selectedTags || "";
    return raw ? raw.split(",").filter(Boolean) : [];
  }

  function setSelectedTagValues(tags) {
    var unique = Array.from(new Set((tags || []).filter(Boolean))).sort();
    document.body.dataset.selectedTags = unique.join(",");
    var section = document.querySelector("[data-tags-section]");
    if (section) section.dataset.selectedTags = unique.join(",");
  }

  function syncTagSection(section) {
    if (!section) return;
    var list = section.querySelector("[data-tag-list]");
    var expandButton = section.querySelector("[data-tags-expand]");
    var clearButton = section.querySelector("[data-tag-clear]");
    if (!list || !expandButton) return;

    var items = Array.prototype.slice.call(list.children || []);
    items.forEach(function (item) {
      item.hidden = false;
    });

    var rowTops = [];
    var overflowTop = null;
    items.forEach(function (item) {
      var top = item.offsetTop;
      if (rowTops.indexOf(top) === -1) rowTops.push(top);
      if (rowTops.length > 2 && overflowTop === null) overflowTop = top;
    });

    var hasOverflow = overflowTop !== null;
    var selectedOverflow = hasOverflow && items.some(function (item) {
      return item.offsetTop >= overflowTop && item.querySelector(".chip--tag-active");
    });
    if (selectedOverflow) section.dataset.tagsExpanded = "true";

    var expanded = section.dataset.tagsExpanded === "true";
    expandButton.textContent = expanded
      ? (expandButton.dataset.collapseLabel || "Show less")
      : (expandButton.dataset.expandLabel || "Show all");

    if (!hasOverflow) {
      hide(expandButton);
    } else if (expanded) {
      show(expandButton);
    } else {
      items.forEach(function (item) {
        item.hidden = item.offsetTop >= overflowTop;
      });
      show(expandButton);
    }

    if (clearButton) {
      if (selectedTagValues().length > 0) show(clearButton);
      else hide(clearButton);
    }
  }

  function syncTagSections(scope) {
    (scope || document).querySelectorAll("[data-tags-section]").forEach(syncTagSection);
  }

  function applyTagChipState(section) {
    if (!section) return;
    section.dataset.selectedTags = document.body.dataset.selectedTags || "";
    var selectedTags = selectedTagValues();
    section.querySelectorAll("[data-tag-chip]").forEach(function (chip) {
      var active = selectedTags.indexOf(chip.dataset.tagName || "") !== -1;
      chip.setAttribute("aria-pressed", active ? "true" : "false");
      chip.classList.toggle("chip--tag-active", !!active);
    });
  }

  function syncFilteredEntryLists(scope) {
    var selectedTags = selectedTagValues();
    (scope || document).querySelectorAll("[data-history-entry-list]").forEach(function (list) {
      var visibleCount = 0;
      list.querySelectorAll("[data-entry-row]").forEach(function (row) {
        var tags = row.dataset.entryTags ? row.dataset.entryTags.split(",").filter(Boolean) : [];
        var matches = selectedTags.length === 0 || selectedTags.some(function (tag) {
          return tags.indexOf(tag) !== -1;
        });
        row.hidden = !matches;
        if (matches) visibleCount += 1;
      });
      var empty = list.parentElement ? list.parentElement.querySelector("[data-history-empty]") : null;
      if (empty) {
        if (visibleCount === 0) show(empty);
        else hide(empty);
      }
    });
  }

  function prefilterHistoryMarkup(markup) {
    if (selectedTagValues().length === 0 || !markup) return markup;
    var wrapper = document.createElement("div");
    wrapper.innerHTML = markup;
    syncFilteredEntryLists(wrapper);
    return wrapper.innerHTML;
  }

  function applyTagFilter(scope) {
    var section = document.querySelector("[data-tags-section]");
    if (section) applyTagChipState(section);
    syncFilteredEntryLists(scope || document);
    syncTagSections(document);
  }

  window.MushinTagFilter = {
    apply: applyTagFilter,
    isHistoryTarget: isHistoryTarget,
    prefilterHistoryMarkup: prefilterHistoryMarkup,
    selected: selectedTagValues,
    setSelected: setSelectedTagValues,
    syncSection: syncTagSection
  };
})();
