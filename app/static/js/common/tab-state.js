window.MushinTabs = (function () {
  "use strict";
  var TAB_NAMES = ["profile", "social", "notifications", "settings"];
  var tabState = {
    profile: { index: -1, entries: [] },
    social: { index: -1, entries: [] },
    notifications: { index: -1, entries: [] },
    settings: { index: -1, entries: [] },
  };
  var activeTab = null;
  function panelFor(name) { return document.getElementById("tab-" + name); }
  function mastheadEl() {
    return document.getElementById("masthead-area");
  }
  function currentEntry(tab) {
    var state = tabState[tab];
    return state && state.index >= 0 ? state.entries[state.index] || null : null;
  }
  function captureInputs(panel) {
    var values = {};
    if (!panel) return values;
    panel.querySelectorAll("input, textarea, select").forEach(function (el, i) {
      values[i] = el.type === "checkbox" || el.type === "radio"
        ? { checked: el.checked }
        : { value: el.value };
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
    return masthead ? window.MushinLoadingSnapshot.html(masthead) : "";
  }
  function restoreMasthead(html) {
    var masthead = mastheadEl();
    if (!masthead) return;
    masthead.innerHTML = html || "";
    var title = masthead.querySelector("h1");
    masthead.hidden = !(title && title.textContent.trim());
  }
  function saveActiveEntry() {
    if (!activeTab) return;
    var entry = currentEntry(activeTab);
    var panel = panelFor(activeTab);
    if (!entry || !panel) return;
    entry.panelHTML = window.MushinLoadingSnapshot.html(panel);
    entry.mastheadHTML = captureMasthead();
    entry.inputs = captureInputs(panel);
    entry.scrollY = window.scrollY;
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
    if (tab === "notifications") {
      document.querySelectorAll('.bottom-nav-tab[data-tab="notifications"] .bottom-nav-badge').forEach(function (badge) {
        badge.remove();
      });
    }
  }
  function restoreEntry(tab, idx, options) {
    var state = tabState[tab];
    var entry = state && state.entries[idx];
    var panel = panelFor(tab);
    if (!entry || !panel) return false;
    var finish = window.MushinPageLoading.start();
    if (!options || !options.skipSave) saveActiveEntry();
    state.index = idx;
    panel.innerHTML = entry.panelHTML || "";
    if (window.htmx) window.htmx.process(panel);
    restoreInputs(panel, entry.inputs);
    restoreMasthead(entry.mastheadHTML);
    setActiveChrome(tab);
    window.scrollTo(0, entry.scrollY || 0);
    document.body.dispatchEvent(
      new CustomEvent("tab:panel-rendered", { detail: { tab: tab, panel: panel } }),
    );
    finish();
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
      scrollY: 0,
    };
  }
  return {
    tabState, panelFor, currentEntry, captureInputs, captureMasthead,
    saveActiveEntry, setActiveChrome, restoreEntry, pushBrowserState,
    appendEntry, entryFromDocument,
    get activeTab() { return activeTab; },
  };
})();
