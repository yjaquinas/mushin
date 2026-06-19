document.body.addEventListener("htmx:afterSwap", (event) => {
  const target = event.detail.target;
  if (!target || target.id !== "theme-toggle") return;

  const theme = target.dataset.theme;
  if (theme) {
    document.documentElement.dataset.theme = theme;
  } else {
    delete document.documentElement.dataset.theme;
  }
});
