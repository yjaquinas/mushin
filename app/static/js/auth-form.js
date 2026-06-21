// Inline-error handling for the entry screen's login / create-account forms.
//
// Both forms POST to the JSON auth endpoints (/auth/login, /auth/signup) with
// hx-swap="none" so a successful response can redirect without HTMX trying to
// swap a JSON body into the page. On success, the response body carries a
// `redirect_url` (the user's canonical /@{username} profile); we navigate there,
// falling back to /home only if the field is missing. A form-local hidden
// `next` field (set server-side only by GET /login, already validated as a
// same-origin path by profiles.safe_next_path) takes priority over
// `redirect_url` when present, so a visitor who hit "log in to comment" lands
// back on the activity they were reading rather than their own profile. On
// failure (4xx), the endpoint's `{"detail": "..."}` body is shown inline in
// the form's #auth-error element without losing the entered username (the
// form itself is never swapped).
//
// Timezone: on submit we stamp the browser's IANA timezone into a hidden
// `timezone` field so signup / guest-creation / login POSTs carry it. The
// server persists it on the user row at creation only and tolerates a missing
// or garbage value (falls back to 'UTC'), so this is best-effort — if the
// detection throws or the field is absent, auth still works.
window.MushinAuth = {
  // Resolve the browser's IANA timezone name (e.g. "America/New_York").
  // Returns "" if the platform doesn't expose it, letting the server fall
  // back to 'UTC' rather than sending a bogus value.
  detectTimezone() {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch {
      return "";
    }
  },

  // hx-on:submit hook: stamp the detected timezone into the form's hidden
  // `timezone` input (creating it if a template didn't include one) just
  // before the request is configured.
  stampTimezone(event) {
    const form = event.target;
    if (!form || typeof form.querySelector !== "function") return;
    let field = form.querySelector('input[name="timezone"]');
    if (!field) {
      field = document.createElement("input");
      field.type = "hidden";
      field.name = "timezone";
      form.appendChild(field);
    }
    field.value = this.detectTimezone();
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
  },
};
