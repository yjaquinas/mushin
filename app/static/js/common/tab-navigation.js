(function () {
  "use strict";

  var activeTab = null;

  // Per-tab virtual history stacks: [{ url, idx }]
  var tabHistory = {
    profile: [],
    social: [],
    settings: [],
  };

  // Panel innerHTML cache per history index: { tab: { idx: html } }
  var tabCache = { profile: {}, social: {}, settings: {} };

  // Input field values per cache entry: { tab: { idx: { [index]: value } } }
  var inputCache = { profile: {}, social: {}, settings: {} };

  // Masthead innerHTML saved when switching away from a tab
  var tabMasthead = {};

  // ── Helpers ───────────────────────────────────────────────────────────

  function panelFor(name) {
    return document.getElementById("tab-panel-" + name);
  }

  function mastheadEl() {
    return document.getElementById("masthead-area");
  }

  function savePanelInputs(tab, idx) {
    var panel = panelFor(tab);
    if (!panel) return;
    var inputs = panel.querySelectorAll("input, textarea, select");
    var values = {};
    inputs.forEach(function (el, i) {
      values[i] = el.value;
    });
    if (!inputCache[tab]) inputCache[tab] = {};
    inputCache[tab][idx] = values;
  }

  function restorePanelInputs(tab, idx) {
    var values = inputCache[tab] && inputCache[tab][idx];
    if (!values) return;
    var panel = panelFor(tab);
    if (!panel) return;
    var inputs = panel.querySelectorAll("input, textarea, select");
    Object.keys(values).forEach(function (i) {
      if (inputs[i]) inputs[i].value = values[i];
    });
  }

  // ── Masthead ──────────────────────────────────────────────────────────

  function updateMasthead(doc) {
    var local = mastheadEl();
    var remote = doc && doc.querySelector("#masthead-area");
    if (!local) return;
    local.innerHTML = remote ? remote.innerHTML : "";
    var title = local.querySelector("h1");
    if (title && title.textContent.trim()) {
      local.removeAttribute("hidden");
    } else {
      local.setAttribute("hidden", "");
    }
  }

  function saveMasthead(tab) {
    var h = mastheadEl();
    if (h) tabMasthead[tab] = h.innerHTML;
  }

  function restoreMasthead(tab) {
    var h = mastheadEl();
    if (!h) return;
    var html = tabMasthead[tab];
    if (html !== undefined) {
      h.innerHTML = html;
      var title = h.querySelector("h1");
      if (title && title.textContent.trim()) {
        h.removeAttribute("hidden");
      } else {
        h.setAttribute("hidden", "");
      }
    } else {
      h.setAttribute("hidden", "");
    }
  }

  // ── Tab switching ─────────────────────────────────────────────────────

  function switchTab(name) {
    if (name === activeTab) return;

    // Save current tab's masthead before leaving
    if (activeTab) saveMasthead(activeTab);

    document.querySelectorAll(".tab-panel").forEach(function (p) {
      p.classList.remove("tab-panel--active");
    });
    document.querySelectorAll(".bottom-nav-tab").forEach(function (l) {
      l.classList.remove("bottom-nav-tab--active");
    });

    var panel = panelFor(name);
    var link = document.querySelector(
      '[data-tab="' + name + '"].bottom-nav-tab',
    );
    if (panel) panel.classList.add("tab-panel--active");
    if (link) link.classList.add("bottom-nav-tab--active");

    // Restore target tab's masthead
    restoreMasthead(name);

    activeTab = name;
    document.body.setAttribute("data-current-tab", name);
  }

  // ── Central navigator ─────────────────────────────────────────────────

  function navigate(url) {
    fetch(url, { headers: { "X-In-Tab-Nav": "1" } })
      .then(function (r) {
        return r.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        var newTab = doc.body.getAttribute("data-current-tab");

        // Non-tabbed page (e.g. entry/legal for non-logged-in users) —
        // do a full navigation instead of swapping into a tab panel.
        if (!newTab) {
          window.location.href = url;
          return;
        }

        var tab = newTab;

        // Save current tab's masthead before any DOM changes
        if (activeTab) saveMasthead(activeTab);

        updateMasthead(doc);

        // If switching tabs, save the freshly-updated masthead for the
        // target tab before switchTab restores the old cached version
        if (tab !== activeTab) saveMasthead(tab);

        var panel = panelFor(tab);
        var remotePanel = doc.getElementById("tab-panel-" + tab);
        var newHTML = "";
        if (panel && remotePanel) {
          // Save current panel's inputs before replacing
          if (tab === activeTab) savePanelInputs(tab, tabHistory[tab].length - 1);
          newHTML = remotePanel.innerHTML;
          panel.innerHTML = newHTML;
          if (window.htmx) window.htmx.process(panel);
        }

        tabHistory[tab].push({ url: url });
        var idx = tabHistory[tab].length - 1;
        tabCache[tab][idx] = newHTML;

        switchTab(tab);
        window.history.pushState({ tab: tab, idx: idx }, "", url);
      });
  }

  // ── Bottom-nav click ──────────────────────────────────────────────────

  document.addEventListener("click", function (e) {
    var tabLink = e.target.closest(".bottom-nav-tab[data-tab]");
    if (!tabLink) return;
    e.preventDefault();

    var name = tabLink.getAttribute("data-tab");
    var url = tabLink.getAttribute("href");

    // Clicking the already-active tab: flush history, go to root.
    if (name === activeTab) {
      tabHistory[name] = [];
      tabCache[name] = {};
      navigate(url);
      return;
    }

    var panel = panelFor(name);

    if (panel && panel.children.length > 0) {
      // Panel has cached content — just switch tabs.
      switchTab(name);
      var stack = tabHistory[name];
      var lastEntry = stack.length > 0 ? stack[stack.length - 1] : null;
      window.history.pushState(
        { tab: name, idx: lastEntry ? lastEntry.idx : 0 },
        "",
        lastEntry ? lastEntry.url : url,
      );
    } else {
      navigate(url);
    }
  });

  // ── In-tab link interception ──────────────────────────────────────────

  document.addEventListener("click", function (e) {
    var link = e.target.closest(
      "a[href^='/']:not([data-tab]):not([data-tab-back]):not([target])",
    );
    if (!link) return;
    // Only intercept while a tab is active (no interception on login/legal pages)
    if (!activeTab) return;
    // Don't intercept dialog-triggering legal links
    if (link.hasAttribute("data-legal")) return;
    // Don't intercept HTMX-enhanced elements
    if (
      link.hasAttribute("hx-get") ||
      link.hasAttribute("hx-post") ||
      link.hasAttribute("hx-put") ||
      link.hasAttribute("hx-delete") ||
      link.hasAttribute("hx-patch")
    )
      return;
    e.preventDefault();
    navigate(link.getAttribute("href"));
  });

  // ── Masthead back button ──────────────────────────────────────────────

  document.addEventListener("click", function (e) {
    var backBtn = e.target.closest("[data-tab-back]");
    if (!backBtn) return;
    e.preventDefault();
    // Let the popstate handler restore cached panel + masthead — no fetch.
    window.history.back();
  });

  // ── Browser back / forward ────────────────────────────────────────────

  window.addEventListener("popstate", function (e) {
    var state = e.state || {};
    if (!state.tab || !activeTab) return;

    if (state.tab !== activeTab) {
      switchTab(state.tab);
    } else {
      // Same-tab — restore the masthead saved when this state was entered
      restoreMasthead(state.tab);
    }

    // Restore cached panel content for this history index
    var panel = panelFor(state.tab);
    var cache = tabCache[state.tab] && tabCache[state.tab][state.idx];
    if (panel && cache !== undefined) {
      panel.innerHTML = cache;
      if (window.htmx) window.htmx.process(panel);
      restorePanelInputs(state.tab, state.idx);
    }

    // Sync tabHistory to the current index
    if (tabHistory[state.tab] && state.idx !== undefined) {
      tabHistory[state.tab] = tabHistory[state.tab].slice(0, state.idx + 1);
    }
  });

  // ── Tag HTMX-swapped history entries ──────────────────────────────────

  document.body.addEventListener("htmx:afterSettle", function (e) {
    if (!activeTab) return;
    var panel = e.detail.target && e.detail.target.closest(".tab-panel");
    if (!panel) return;

    // Save current panel content to cache before HTMX replaces it?
    // No — htmx:afterSettle fires AFTER the swap, so the content is already
    // in the DOM. We tag the history entry and cache the new content.
    // Use the current history state's idx so HTMX replaces don't collide
    // with navigate() pushes (which compute idx from tabHistory length).
    var state = window.history.state || {};
    var idx = state.idx !== undefined ? state.idx : tabHistory[activeTab].length;
    savePanelInputs(activeTab, idx);
    tabCache[activeTab][idx] = panel.innerHTML;
    window.history.replaceState(
      { tab: activeTab, idx: idx },
      "",
      window.location.href,
    );
  });

  // ── Init ──────────────────────────────────────────────────────────────

  document.addEventListener("DOMContentLoaded", function () {
    var initialTab =
      document.body.getAttribute("data-current-tab") || "";
    if (initialTab) {
      activeTab = initialTab;
      tabHistory[initialTab] = [{ url: window.location.href }];
      var panel = panelFor(initialTab);
      if (panel) {
        tabCache[initialTab][0] = panel.innerHTML;
        savePanelInputs(initialTab, 0);
      }
      window.history.replaceState(
        { tab: initialTab, idx: 0 },
        "",
        window.location.href,
      );
    }

    if (window.htmx && activeTab) {
      var panel = panelFor(activeTab);
      if (panel) window.htmx.process(panel);
    }
  });
})();
