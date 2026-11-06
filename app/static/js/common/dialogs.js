// Shared modal lifecycle and page scroll lock.
var dialogPageScroll = {
  saved: null,
  lock: function () {
    if (this.saved) return;
    var body = document.body.style;
    this.saved = { x: window.scrollX, y: window.scrollY,
      htmlOverflow: document.documentElement.style.overflow,
      overflow: body.overflow, position: body.position, top: body.top,
      left: body.left, width: body.width };
    document.documentElement.style.overflow = "hidden";
    body.overflow = "hidden";
    body.position = "fixed";
    body.top = -this.saved.y + "px";
    body.left = -this.saved.x + "px";
    body.width = "100%";
  },
  unlock: function () {
    var saved = this.saved;
    if (!saved) return;
    document.documentElement.style.overflow = saved.htmlOverflow;
    ["overflow", "position", "top", "left", "width"].forEach(function (key) {
      document.body.style[key] = saved[key];
    });
    window.scrollTo({ left: saved.x, top: saved.y, behavior: "instant" });
    this.saved = null;
  },
};

function DialogManager(id) {
  this.id = id;
  this.el = null; // resolved at init time
}

DialogManager.prototype = {
  // ── lifecycle ──────────────────────────────────────────────

  init: function () {
    const el = document.getElementById(this.id);
    if (!el) return;
    this.el = el;

    // Defensive: ensure hidden state is correct.
    el.setAttribute("hidden", "");

    // Window keydown → Escape closes.
    this._keydown = function (e) {
      if (dialogManagerRegistry.top() !== this) return;
      if (el.hasAttribute("data-disable-escape-close")) return;
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopImmediatePropagation();
        this.close();
      }
    };
    window.addEventListener("keydown", this._keydown.bind(this));

    // Backdrop click (outside the dialog panel) → close.
    this._overlayClick = function (e) {
      if (dialogManagerRegistry.top() !== this) return;
      if (el.hasAttribute("data-disable-backdrop-close")) return;
      var panel = el.querySelector('[role="dialog"]');
      if (panel && !panel.contains(e.target)) {
        this.close();
      }
    };
    el.addEventListener("click", this._overlayClick.bind(this));
  },

  // ── actions ────────────────────────────────────────────────

  open: function () {
    if (!this.el) return;
    dialogManagerRegistry.purgeOrphans();
    dialogManagerRegistry.add(this);
    this.el.removeAttribute("hidden");
    dialogPageScroll.lock();
    this.el.dispatchEvent(new CustomEvent("dialog:open", { bubbles: true }));
    this.el.querySelector('[role="dialog"]')?.focus({ preventScroll: true });
  },

  close: function () {
    if (!this.el) return;
    this.el.setAttribute("hidden", "");
    dialogManagerRegistry.purgeOrphans();
    dialogManagerRegistry.remove(this);
    if (dialogManagerRegistry.count() === 0) {
      dialogPageScroll.unlock();
    }
    this.el.dispatchEvent(new CustomEvent("dialog:close", { bubbles: true }));
  },
};

// ── registry ─────────────────────────────────────────────────
// Tracks instances, including reopened dialogs and HTMX replacements.

var dialogManagerRegistry = {
  _list: [],
  add: function (dlg) {
    if (this._list.indexOf(dlg) !== -1) return;
    this._list.push(dlg);
  },
  remove: function (dlg) {
    var idx = this._list.indexOf(dlg);
    if (idx !== -1) this._list.splice(idx, 1);
  },
  count: function () {
    var open = 0;
    for (var i = 0; i < this._list.length; i++) {
      var dlg = this._list[i];
      if (dlg.el && document.body.contains(dlg.el) && !dlg.el.hasAttribute("hidden")) open += 1;
    }
    return open;
  },
  top: function () {
    return this._list.findLast(function (dlg) {
      return dlg.el?.isConnected && !dlg.el.hasAttribute("hidden");
    });
  },
  // Remove entries whose element is no longer in the DOM (orphaned by tab
  // navigation). Prevents stale DialogManagers from blocking overflow restore.
  purgeOrphans: function () {
    var remaining = [];
    for (var i = 0; i < this._list.length; i++) {
      var dlg = this._list[i];
      if (dlg.el && document.body.contains(dlg.el)) {
        remaining.push(dlg);
      }
    }
    this._list = remaining;
    if (this.count() === 0) {
      dialogPageScroll.unlock();
    }
  },
};

document.body.addEventListener("htmx:afterSettle", function () {
  dialogManagerRegistry.purgeOrphans();
});
