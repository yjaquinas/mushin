(function () {
  if (document.cookie.indexOf("mushin_theme=") !== -1) return;
  var theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", theme);
  document.cookie = "mushin_theme=" + theme + ";path=/;max-age=31536000;SameSite=Lax";
})();
