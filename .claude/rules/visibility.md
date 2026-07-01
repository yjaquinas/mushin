# Auth, visibility, and data-isolation rules

## Account model

Every user must sign up (username + password) before doing anything. Username
is load-bearing: every activity lives at `/@{username}/{slug}`, so a
username-less account can't participate in the core URL scheme.

## Three-tier visibility

- `public` — whole record including notes is visible to anyone.
- `private` — any visitor sees the **character sheet** at `/@{username}`
  (activity names + counts, cards not clickable) but **cannot open
  `/@{username}/{slug}`** — that 303-redirects to `/@{username}`. A **fellow**
  (accepted mutual connection after sharing-consent) sees the full record
  including entries and free-text notes on either account. A private account
  is still searchable by username/display name; activity _names_ are visible
  to any searcher.

## Capability-checking authority

`app/services/profiles.py::viewer_capability` / `can_view_activity_detail` is
the **single, fail-closed authority** for every visibility decision.

- **Never** inline a `visibility` field comparison in a route handler.
- **Never** cache a capability result — always call the service function.

## Data isolation

Every data query must be scoped by `owner_id`. Multi-user isolation is
non-negotiable; an unscoped query is a bug regardless of context.

## UI strings

All user-facing copy lives in `app/ui_strings.py`. No hardcoded strings in
templates — the integration test `test_no_hardcoded_copy_in_templates`
enforces this. When adding new copy, add it to `ui_strings.py` first.
