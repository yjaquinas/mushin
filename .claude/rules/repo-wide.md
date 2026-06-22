# Repo-wide conventions

Always-loaded rule (no `paths:` frontmatter). Applies to any work in this project regardless of file location.

## Secret hygiene

- `.env` is **never** committed. If you find yourself about to `git add .env`, stop and use `.env.example` with placeholder values.
- API keys, tokens, and passwords are never hardcoded in source. Always `os.getenv(...)` with a documented env var.
- The production host's IP address is never in any repo. It lives in `~/.ssh/config` on dev machines and in GitHub Actions secrets for CI.
- `gitleaks` runs as a pre-commit hook and explicitly inside `/commit-git`. If gitleaks flags something, **stop and investigate** — do not bypass with `--no-verify`.

## Git hygiene

- Commits use conventional format: `type(scope): subject` — see `/commit-git` for the full convention.
- Commit subjects use imperative mood ("add feature", not "added feature").
- Direct commits to `main` are allowed for solo work, but a branch + PR pattern is preferred once a project has real users or contributors.
- **Never force-push** without confirming it won't overwrite someone else's work.
- **Never rewrite shared history** (rebase/amend of pushed commits) without explicit confirmation.

## Destructive actions

Before any of the following, ask before proceeding:

- `rm -rf` of anything outside a scratch directory
- `git reset --hard` when there are uncommitted changes
- `git clean -fd` anywhere
- `DROP TABLE`, `TRUNCATE`, or any DDL that deletes data
- Deleting branches with unmerged commits
- Any `sudo` command on the production host beyond read-only inspection

## CI and deploy

- `main` is the deploy branch. Pushes to `main` trigger the GitHub Actions deploy workflow.
- Don't push broken code to `main` expecting to "just hotfix it" — the deploy will run, the health check will fail, the service will be in a restart loop.
- The deploy workflow does not auto-rollback. A failing deploy needs a deliberate rollback via `git revert` + push (see `deploy-procedure`).

## Meeting outputs

- `meetings/` in this project is tracked in git — it's the project's decision history.
- New meetings land as `meetings/MEETING-YYYY-MM-DD-{slug}/` via `/run-meeting`.
- Don't edit a committed meeting's output retroactively; write a follow-up meeting instead.

## Project-specific additions

### Personal data

- Every `owner_id`-scoped row is personal data — **including free-text memos**, which can contain anything (health, names, locations).
- **Account deletion must cascade** to all of a user's data (`category`, `activity`, `field_def`, `tag`, `entry`, `entry_tag`, `entry_value`, `match`, `connection`, `block`, `comment`, memos) — a deletion that leaves orphaned data is a privacy failure. Enforce via `ON DELETE CASCADE` from `user`.
- **No memo content (or any `owner_id`-scoped data) may be sent to a third-party API** — no LLM "summarize your progress", no analytics capturing memo text, no error-tracker that might log a memo. Adding any such feature requires a privacy-policy update + fresh explicit consent, never a quiet add.
- Data export/deletion tooling must include memos to make the access/deletion rights honest.
- **Guest mode is retired (2026-06-16) — drain window in effect.** Guest account creation is no longer reachable from the UI; new signups require a username. Existing guest rows (`auth_provider='guest'`) drain via the guest-reaper timer (zero-entry guests ~7d, inactive guests ~30d). During the drain window: the reaper service/timer stays running; the upgrade-in-place flow stays functional; the privacy policy language covering guests remains accurate. Once the backlog clears, a separate cleanup build will remove the `auth_provider='guest'` CHECK, the reaper service/timer, and the guest branches in `app/auth/` and `app/routes/web.py`. Do not remove any of this code before that cleanup build.
- **Public profiles are opt-in and user-controlled.** A user may set their account to `public` (default is `private`), making their entire record — including free-text memos — visible to anyone who has their profile URL (`/@{username}`). The owner sees the same URL as visitors — `/@{username}` — with write affordances shown only when logged in as the owner. This choice is made via a one-time consent screen that states plainly what `public` exposes. Guests (no `username`) cannot have a public profile and are unaffected.
- **This does not change the third-party rule.** "No owner_id-scoped data (including memos) may be sent to a third-party API" still applies unchanged — public profiles are visible to *other users/visitors of Mushin*, never sent to an external service. Don't conflate the two when reviewing future features.

### Social graph (fellows) + three-tier visibility

- **Visibility is three-tier; the capability helper is the only authority.** All visibility decisions go through `app/services/profiles.py::viewer_capability` / `can_view_activity_detail` — a single, unit-tested, **fail-closed** boundary. Never inline a `visibility` check in a route handler; never cache a capability (a stale capability is a bypass). Default-deny on any ambiguity (no session, pending/declined connection, block).
- **`private` no longer means hidden.** A private account's `/@{username}` character sheet (activity names + counts) is visible to any visitor and surfaces in search; only entries + free-text notes stay gated. Any change that *widens* what a non-fellow sees on a private account requires fresh consent + a privacy-policy update.
- **A fellow connection exposes private notes — gate it on explicit, separate consent.** Reaching `connected` requires `status='accepted' AND sharing_consent_at` (set via a deliberate consequence-screen confirm), not merely "a connection row exists." Disconnect/block revokes access in both directions immediately. Deletion cascades `connection` + `block` both directions; data export includes the connection list + pending requests.
- **Search must not leak.** People search may return any account's handle + display name + relationship state, never activity/entry/note data. **Tag search is public-only** and structurally incapable of returning private/limited accounts or matching note/entry text. Blocks hide both directions from search.
- **Third-party rule unchanged for the social graph.** Connections/visibility expose data to *other Mushin users* only — never to any third-party API. Do not conflate "visible to a fellow" with "sent externally" (notifications are in-app, content-free).
- **Comments are co-owned, cross-user personal data.** A comment is free text written by one user (`author_id`) about another user's entry — it must cascade-delete on deletion of *either* account, not just the entry owner's (the existing single-owner cascade assumption doesn't hold here). Comment visibility is never stored or cached: every read re-checks `can_view_activity_detail` live, so a revoked fellow connection, a block, or a public→private flip silently stops a comment from rendering — it is never retroactively deleted for that reason. Comment bodies are exported/deleted alongside a user's other personal data on both sides of the relationship (as author and as entry-owner). The no-third-party-API rule applies to comment bodies exactly as it does to memos. Any comment notification stays in-app and content-free (no comment text, ever, in email/push).
