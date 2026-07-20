// Generic dialog manager — handles dialog open/close, focus-trap, Escape-to-close,
// and overlay-click-to-close via vanilla JS.
//
// Usage (in templates):
//   const dlg = new DialogManager("dialog-id");
//   dlg.init();
//   // Wire open buttons:
//   document.getElementById("open-btn-id")?.addEventListener("click", () => dlg.open());
//   // Wire cancel button (closes the dialog):
//   document.getElementById("cancel-btn-id")?.addEventListener("click", () => dlg.close());
//
// Each instance wires:
//   - window "keydown Escape" → close
//   - overlay clicks (not inner content) → close
//   - focus-trap on open (moves focus to the dialog root)

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
      if (el.hasAttribute("data-disable-escape-close")) return;
      if (e.key === "Escape") {
        dialogManagerRegistry.remove(this);
        this.close();
      }
    };
    window.addEventListener("keydown", this._keydown.bind(this));

    // Backdrop click (outside the dialog panel) → close.
    this._overlayClick = function (e) {
      if (el.hasAttribute("data-disable-backdrop-close")) return;
      var panel = el.querySelector('[role="dialog"]');
      if (panel && !panel.contains(e.target)) {
        dialogManagerRegistry.remove(this);
        this.close();
      }
    };
    el.addEventListener("click", this._overlayClick.bind(this));
  },

  // ── actions ────────────────────────────────────────────────

  open: function () {
    if (!this.el) return;
    dialogManagerRegistry.purgeOrphans();
    this.el.removeAttribute("hidden");
    document.body.style.overflow = "hidden";
    this.el.dispatchEvent(new CustomEvent("dialog:open", { bubbles: true }));
    this.el.querySelector('[role="dialog"]')?.focus();
  },

  close: function () {
    if (!this.el) return;
    this.el.setAttribute("hidden", "");
    dialogManagerRegistry.purgeOrphans();
    dialogManagerRegistry.remove(this);
    if (dialogManagerRegistry.count() === 0) {
      document.body.style.overflow = "";
    }
    this.el.dispatchEvent(new CustomEvent("dialog:close", { bubbles: true }));
  },
};

// ── registry ─────────────────────────────────────────────────
// Tracks active DialogManager instances so Escape can reach them.
// Removing an instance on close also cleans up its event listeners.

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
      document.body.style.overflow = "";
    }
  },
};

document.body.addEventListener("htmx:afterSettle", function () {
  dialogManagerRegistry.purgeOrphans();
});
