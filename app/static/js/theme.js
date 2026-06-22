document.body.addEventListener("htmx:afterSwap", (event) => {
  const swappedTarget = event.detail.target;
  if (!swappedTarget || swappedTarget.id !== "theme-toggle") return;

  // hx-swap="outerHTML" on the button itself replaces the DOM node; by the
  // time this listener runs, `event.detail.target` is the stale, detached
  // pre-swap node (still carrying the old data-theme). Re-query the live
  // element instead of trusting that reference.
  const target = document.getElementById("theme-toggle");
  const theme = target && target.dataset.theme;
  if (theme) {
    document.documentElement.dataset.theme = theme;
  }
});
