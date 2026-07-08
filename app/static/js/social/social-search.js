(function () {
  document.addEventListener("click", function (e) {
    var toggle = e.target.closest("#search-toggle");
    if (!toggle) return;

    var searchSection = document.getElementById("search-section");
    var recentSection = document.getElementById("recent-entries-section");
    if (!searchSection || !recentSection) return;

    var searchInput = document.getElementById("search-input");
    var iconOpen = document.getElementById("search-icon-open");
    var iconClose = document.getElementById("search-icon-close");

    var wasHidden = searchSection.hidden;
    searchSection.hidden = !wasHidden;
    recentSection.hidden = wasHidden;

    if (iconOpen) iconOpen.hidden = wasHidden;
    if (iconClose) iconClose.hidden = !wasHidden;

    if (wasHidden) {
      if (searchInput) searchInput.focus();
    } else {
      if (searchInput) searchInput.value = "";
    }
  });
})();
