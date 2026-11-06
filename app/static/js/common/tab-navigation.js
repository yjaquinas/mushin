(function () {
  "use strict";
  var tabs = window.MushinTabs;
  var {
    tabState, panelFor, currentEntry, captureInputs, captureMasthead,
    saveActiveEntry, setActiveChrome, restoreEntry, pushBrowserState,
    appendEntry, entryFromDocument,
  } = tabs;
  var pending = null;
  function navigate(url, options) {
    if (pending) pending.abort();
    var controller = new AbortController();
    pending = controller;
    var finish = window.MushinPageLoading.start();
    var fullNavigation = false;
    function fallback() {
      fullNavigation = true;
      window.location.href = url;
    }
    fetch(url, { headers: { "X-In-Tab-Nav": "1" }, signal: controller.signal })
      .then(function (response) {
        return response.text();
      })
      .then(function (html) {
        if (controller.signal.aborted) return;
        var doc = new DOMParser().parseFromString(html, "text/html");
        var tab = doc.body.getAttribute("data-current-tab");
        if (!tab || !tabState[tab]) {
          fallback();
          return;
        }
        var entry = entryFromDocument(doc, tab, url);
        if (!entry) {
          fallback();
          return;
        }
        saveActiveEntry();
        var idx = appendEntry(tab, entry, options && options.replaceCurrent);
        restoreEntry(tab, idx, { skipSave: true });
        pushBrowserState(tab, idx, url, options && options.replaceState);
        if (options && options.scrollToTop) window.scrollTo(0, 0);
      })
      .catch(function () {
        if (!controller.signal.aborted) fallback();
      })
      .finally(function () { if (!fullNavigation) finish(); });
  }
  function switchToTab(tab, url) {
    var state = tabState[tab];
    if (!state) return;
    if (state.index >= 0) {
      if (pending) pending.abort();
      restoreEntry(tab, state.index);
      pushBrowserState(tab, state.index, currentEntry(tab).url, false);
    } else {
      navigate(url);
    }
  }
  function isSocialFeed() {
    return window.location.pathname === "/social";
  }
  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var tabLink = e.target.closest(".bottom-nav-tab[data-tab]");
    if (!tabLink) return;
    e.preventDefault();
    var tab = tabLink.getAttribute("data-tab");
    var url = tabLink.getAttribute("href");
    if (tab === tabs.activeTab) {
      if (tab === "social" && isSocialFeed()) {
        navigate(url, { replaceCurrent: true, replaceState: true, scrollToTop: true });
        return;
      }
      navigate(url, { replaceCurrent: false });
      return;
    }
    switchToTab(tab, url);
  });
  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var link = e.target.closest(
      "a[href^='/']:not([data-tab]):not([data-tab-back]):not([target])",
    );
    if (!link || !tabs.activeTab) return;
    if (link.hasAttribute("download") || link.hasAttribute("data-download")) return;
    if (link.hasAttribute("data-legal")) return;
    if (
      link.hasAttribute("hx-get") ||
      link.hasAttribute("hx-post") ||
      link.hasAttribute("hx-put") ||
      link.hasAttribute("hx-delete") ||
      link.hasAttribute("hx-patch")
    ) {
      return;
    }
    e.preventDefault();
    navigate(link.getAttribute("href"));
  });
  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var backBtn = e.target.closest("[data-tab-back]");
    if (!backBtn) return;
    e.preventDefault();
    window.history.back();
  });
  window.addEventListener("popstate", function (e) {
    var state = e.state || {};
    if (!state.tab || state.idx === undefined) return;
    if (pending) pending.abort();
    restoreEntry(state.tab, state.idx);
  });
  document.body.addEventListener("htmx:afterSettle", function (e) {
    if (!tabs.activeTab) return;
    var panel = e.detail.target && e.detail.target.closest(".tab-panel");
    if (!panel) return;
    saveActiveEntry();
    var state = window.history.state || {};
    if (state.tab === tabs.activeTab && state.idx !== undefined) {
      pushBrowserState(tabs.activeTab, state.idx, window.location.href, true);
    }
  });
  document.addEventListener("DOMContentLoaded", function () {
    var initialTab = document.body.getAttribute("data-current-tab") || "";
    if (!tabState[initialTab]) return;
    if ("scrollRestoration" in window.history) {
      window.history.scrollRestoration = "manual";
    }
    var panel = panelFor(initialTab);
    var entry = {
      url: window.location.href,
      panelHTML: panel ? window.MushinLoadingSnapshot.html(panel) : "",
      mastheadHTML: captureMasthead(),
      inputs: captureInputs(panel),
      scrollY: window.scrollY,
    };
    var idx = appendEntry(initialTab, entry, false);
    setActiveChrome(initialTab);
    pushBrowserState(initialTab, idx, window.location.href, true);
    if (window.htmx && panel) window.htmx.process(panel);
  });
})();
