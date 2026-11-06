window.MushinEntryFocus = (function () {
  "use strict";
  function scrollToDeepLinkedEntry(root) {
    var row = (root || document).querySelector("[data-entry-deep-link]");
    if (!row) return;
    window.requestAnimationFrame(function () {
      row.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  function scrollToDeepLinkedComment() {
    var match = window.location.hash.match(/^#comment-(\d+)$/);
    var target = match && document.getElementById("comment-" + match[1]);
    if (!target) {
      match = window.location.hash.match(/^#comment-slot-(\d+)$/);
      target = match && document.getElementById("comment-slot-" + match[1]);
    }
    if (!target) return;
    window.requestAnimationFrame(function () {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  return { scrollEntry: scrollToDeepLinkedEntry, scrollComment: scrollToDeepLinkedComment };
})();
