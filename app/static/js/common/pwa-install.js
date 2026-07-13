(function () {
  "use strict";

  var deferredPrompt = null;
  var STORAGE_KEY = "pwa-install-dismissed";
  var FALLBACK_TIMEOUT_MS = 3000;
  var fallbackTimer = null;
  var promptFired = false;

  function isInstalled() {
    return (
      window.matchMedia("(display-mode: standalone)").matches ||
      window.matchMedia("(display-mode: fullscreen)").matches ||
      window.matchMedia("(display-mode: minimal-ui)").matches
    );
  }

  function isDismissed() {
    try { return sessionStorage.getItem(STORAGE_KEY) === "1"; } catch (_) { return false; }
  }

  function isSafari() {
    var ua = navigator.userAgent;
    return (
      (ua.includes("Safari") || ua.includes("AppleWebKit")) &&
      !ua.includes("Chrome") &&
      !ua.includes("Chromium") &&
      !ua.includes("FxiOS") &&
      !ua.includes("EdgiOS")
    );
  }

  function isSafariMobile() {
    return isSafari() && /iPhone|iPad|iPod/.test(navigator.userAgent);
  }

  function isSafariDesktop() {
    return isSafari() && !isSafariMobile();
  }

  function showBanner() {
    var banner = document.getElementById("pwa-install-banner");
    if (banner) banner.removeAttribute("hidden");
  }

  function hideBanner() {
    var banner = document.getElementById("pwa-install-banner");
    if (banner) banner.setAttribute("hidden", "");
  }

  function dismiss() {
    hideBanner();
    try { sessionStorage.setItem(STORAGE_KEY, "1"); } catch (_) {}
  }

  function showChromiumBanner() {
    var textEl = document.getElementById("pwa-install-text");
    var installBtn = document.getElementById("pwa-install-btn");
    if (textEl) textEl.textContent = textEl.dataset.default;
    if (installBtn) installBtn.removeAttribute("hidden");
    showBanner();
  }

  function showSafariFallback() {
    var textEl = document.getElementById("pwa-install-text");
    var installBtn = document.getElementById("pwa-install-btn");
    if (installBtn) installBtn.setAttribute("hidden", "");
    if (textEl) {
      textEl.textContent = isSafariMobile()
        ? textEl.dataset.safariIos
        : textEl.dataset.safariMac;
    }
    showBanner();
  }

  function onInstallClick() {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then(function (result) {
      if (result.outcome === "accepted") {
        hideBanner();
      }
      deferredPrompt = null;
    });
  }

  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault();
    deferredPrompt = e;
    promptFired = true;
    if (fallbackTimer) { clearTimeout(fallbackTimer); fallbackTimer = null; }
    if (isInstalled() || isDismissed()) return;
    showChromiumBanner();
  });

  fallbackTimer = setTimeout(function () {
    fallbackTimer = null;
    if (promptFired) return;
    if (isInstalled() || isDismissed()) return;
    if (!isSafari()) return;
    showSafariFallback();
  }, FALLBACK_TIMEOUT_MS);

  document.addEventListener("DOMContentLoaded", function () {
    var installBtn = document.getElementById("pwa-install-btn");
    var closeBtn = document.getElementById("pwa-install-close");

    if (installBtn) installBtn.addEventListener("click", onInstallClick);
    if (closeBtn) closeBtn.addEventListener("click", dismiss);
  });
})();
