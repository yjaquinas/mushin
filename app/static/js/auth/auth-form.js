// Inline-error handling for the entry screen's login / create-account forms.
//
// Both forms POST to the JSON auth endpoints (/auth/login, /auth/signup) with
// hx-swap="none" so a successful response can redirect without HTMX trying to
// swap a JSON body into the page. On success, the response body carries a
// `redirect_url` (the user's canonical /@{username} profile); we navigate there,
// falling back to /home only if the field is missing. A form-local hidden
// `next` field (set server-side by the entry/login GET route, already validated as a
// same-origin path by profiles.safe_next_path) takes priority over
// `redirect_url` when present, so a visitor who hit "log in to comment" lands
// back on the activity they were reading rather than their own profile. On
// failure (4xx), the endpoint's `{"detail": "..."}` body is shown inline in
// the form's #auth-error element and echoed through the shared error toast
// without losing the entered username (the form itself is never swapped).
window.MushinAuth = {
  showErrorToast(message) {
    if (!message || typeof window.showToast !== "function") return;
    window.showToast(message, "error");
  },

  handle(event) {
    const xhr = event.detail.xhr;
    if (event.detail.successful) {
      let redirectUrl = "/home";
      try {
        const body = JSON.parse(xhr.responseText);
        if (typeof body.redirect_url === "string" && body.redirect_url) {
          redirectUrl = body.redirect_url;
        }
      } catch {
        // Non-JSON success body — fall back to /home.
      }

      const form = event.detail.elt;
      const nextField = form && typeof form.querySelector === "function"
        ? form.querySelector('input[name="next"]')
        : null;
      if (nextField && nextField.value) {
        redirectUrl = nextField.value;
      }

      window.location.href = redirectUrl;
      return;
    }

    const form = event.detail.elt;
    const errorEl = form.querySelector("[data-auth-error]");
    if (!errorEl) return;

    let message = "";
    try {
      const body = JSON.parse(xhr.responseText);
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (body.detail && typeof body.detail.message === "string") {
        message = body.detail.message;
      }
    } catch {
      // Non-JSON error body — leave message empty rather than show raw HTML.
    }

    errorEl.textContent = message;
    errorEl.hidden = !message;
    this.showErrorToast(message);
  },
};

document.addEventListener("submit", function (event) {
  const form = event.target;
  if (!form || !form.hasAttribute("data-auth-form")) return;
});

document.body.addEventListener("htmx:afterRequest", function (event) {
  const elt = event.detail && event.detail.elt;
  if (!elt || !elt.hasAttribute("data-auth-form")) return;
  window.MushinAuth.handle(event);
});
