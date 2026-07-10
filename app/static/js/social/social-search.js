(function () {
  document.addEventListener("click", function (e) {
    var toggle = e.target.closest("#social-button-search-toggle");
    if (!toggle) return;

    var searchSection = document.getElementById("social-section-search");
    var recentSection = document.getElementById("social-section-feed");
    if (!searchSection || !recentSection) return;

    var searchInput = document.getElementById("social-field-search");
    var iconOpen = document.getElementById("social-icon-search-open");
    var iconClose = document.getElementById("social-icon-search-close");

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
