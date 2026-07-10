(function () {
  "use strict";

  var TAB_NAMES = ["profile", "social", "settings"];
  var tabState = {
    profile: { index: -1, entries: [] },
    social: { index: -1, entries: [] },
    settings: { index: -1, entries: [] },
  };
  var activeTab = null;

  function panelFor(name) {
    return document.getElementById("tab-" + name);
  }

  function mastheadEl() {
    return document.getElementById("masthead-area");
  }

  function currentEntry(tab) {
    var state = tabState[tab];
    if (!state || state.index < 0) return null;
    return state.entries[state.index] || null;
  }

  function captureInputs(panel) {
    var values = {};
    if (!panel) return values;
    panel.querySelectorAll("input, textarea, select").forEach(function (el, i) {
      if (el.type === "checkbox" || el.type === "radio") {
        values[i] = { checked: el.checked };
      } else {
        values[i] = { value: el.value };
      }
    });
    return values;
  }

  function restoreInputs(panel, values) {
    if (!panel || !values) return;
    var inputs = panel.querySelectorAll("input, textarea, select");
    Object.keys(values).forEach(function (i) {
      if (!inputs[i]) return;
      if (Object.prototype.hasOwnProperty.call(values[i], "checked")) {
        inputs[i].checked = values[i].checked;
      } else {
        inputs[i].value = values[i].value;
      }
    });
  }

  function captureMasthead() {
    var masthead = mastheadEl();
    return masthead ? masthead.innerHTML : "";
  }

  function restoreMasthead(html) {
    var masthead = mastheadEl();
    if (!masthead) return;
    masthead.innerHTML = html || "";
    var title = masthead.querySelector("h1");
    if (title && title.textContent.trim()) {
      masthead.removeAttribute("hidden");
    } else {
      masthead.setAttribute("hidden", "");
    }
  }

  function saveActiveEntry() {
    if (!activeTab) return;
    var entry = currentEntry(activeTab);
    var panel = panelFor(activeTab);
    if (!entry || !panel) return;
    entry.panelHTML = panel.innerHTML;
    entry.mastheadHTML = captureMasthead();
    entry.inputs = captureInputs(panel);
  }

  function setActiveChrome(tab) {
    TAB_NAMES.forEach(function (name) {
      var panel = panelFor(name);
      if (panel) {
        var isActive = name === tab;
        panel.classList.toggle("tab-panel--active", isActive);
        panel.hidden = !isActive;
        panel.setAttribute("aria-hidden", isActive ? "false" : "true");
      }
    });

    document.querySelectorAll(".bottom-nav-tab").forEach(function (link) {
      var isActive = link.getAttribute("data-tab") === tab;
      link.classList.toggle("bottom-nav-tab--active", isActive);
      if (isActive) {
        link.setAttribute("aria-current", "page");
      } else {
        link.removeAttribute("aria-current");
      }
    });

    activeTab = tab;
    document.body.setAttribute("data-current-tab", tab);
  }

  function restoreEntry(tab, idx, options) {
    var state = tabState[tab];
    var entry = state && state.entries[idx];
    var panel = panelFor(tab);
    if (!entry || !panel) return false;

    if (!options || !options.skipSave) saveActiveEntry();
    state.index = idx;
    panel.innerHTML = entry.panelHTML || "";
    if (window.htmx) window.htmx.process(panel);
    restoreInputs(panel, entry.inputs);
    restoreMasthead(entry.mastheadHTML);
    setActiveChrome(tab);
    document.body.dispatchEvent(
      new CustomEvent("tab:panel-rendered", { detail: { tab: tab, panel: panel } }),
    );
    return true;
  }

  function pushBrowserState(tab, idx, url, replace) {
    var state = { tab: tab, idx: idx };
    if (replace) {
      window.history.replaceState(state, "", url);
    } else {
      window.history.pushState(state, "", url);
    }
  }

  function appendEntry(tab, entry, replaceCurrent) {
    var state = tabState[tab];
    if (!state) return -1;

    if (replaceCurrent && state.index >= 0) {
      state.entries[state.index] = entry;
      return state.index;
    }

    if (state.index < state.entries.length - 1) {
      state.entries = state.entries.slice(0, state.index + 1);
    }
    state.entries.push(entry);
    state.index = state.entries.length - 1;
    return state.index;
  }

  function entryFromDocument(doc, tab, url) {
    var remotePanel = doc.getElementById("tab-" + tab);
    var remoteMasthead = doc.getElementById("masthead-area");
    if (!remotePanel) return null;
    return {
      url: url,
      panelHTML: remotePanel.innerHTML,
      mastheadHTML: remoteMasthead ? remoteMasthead.innerHTML : "",
      inputs: captureInputs(remotePanel),
    };
  }

  function navigate(url, options) {
    fetch(url, { headers: { "X-In-Tab-Nav": "1" } })
      .then(function (response) {
        return response.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        var tab = doc.body.getAttribute("data-current-tab");
        if (!tab || !tabState[tab]) {
          window.location.href = url;
          return;
        }

        var entry = entryFromDocument(doc, tab, url);
        if (!entry) {
          window.location.href = url;
          return;
        }

        saveActiveEntry();
        var idx = appendEntry(tab, entry, options && options.replaceCurrent);
        restoreEntry(tab, idx, { skipSave: true });
        pushBrowserState(tab, idx, url, options && options.replaceState);
      })
      .catch(function () {
        window.location.href = url;
      });
  }

  function switchToTab(tab, url) {
    var state = tabState[tab];
    if (!state) return;
    if (state.index >= 0) {
      restoreEntry(tab, state.index);
      pushBrowserState(tab, state.index, currentEntry(tab).url, false);
    } else {
      navigate(url);
    }
  }

  document.addEventListener("click", function (e) {
    var tabLink = e.target.closest(".bottom-nav-tab[data-tab]");
    if (!tabLink) return;
    e.preventDefault();

    var tab = tabLink.getAttribute("data-tab");
    var url = tabLink.getAttribute("href");
    if (tab === activeTab) {
      navigate(url, { replaceCurrent: false });
      return;
    }
    switchToTab(tab, url);
  });

  document.addEventListener("click", function (e) {
    var link = e.target.closest(
      "a[href^='/']:not([data-tab]):not([data-tab-back]):not([target])",
    );
    if (!link || !activeTab) return;
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
    var backBtn = e.target.closest("[data-tab-back]");
    if (!backBtn) return;
    e.preventDefault();
    window.history.back();
  });

  window.addEventListener("popstate", function (e) {
    var state = e.state || {};
    if (!state.tab || state.idx === undefined) return;
    restoreEntry(state.tab, state.idx);
  });

  document.body.addEventListener("htmx:afterSettle", function (e) {
    if (!activeTab) return;
    var panel = e.detail.target && e.detail.target.closest(".tab-panel");
    if (!panel) return;
    saveActiveEntry();
    var state = window.history.state || {};
    if (state.tab === activeTab && state.idx !== undefined) {
      pushBrowserState(activeTab, state.idx, window.location.href, true);
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    var initialTab = document.body.getAttribute("data-current-tab") || "";
    if (!tabState[initialTab]) return;

    var panel = panelFor(initialTab);
    var entry = {
      url: window.location.href,
      panelHTML: panel ? panel.innerHTML : "",
      mastheadHTML: captureMasthead(),
      inputs: captureInputs(panel),
    };
    var idx = appendEntry(initialTab, entry, false);
    setActiveChrome(initialTab);
    pushBrowserState(initialTab, idx, window.location.href, true);

    if (window.htmx && panel) window.htmx.process(panel);
  });
})();
