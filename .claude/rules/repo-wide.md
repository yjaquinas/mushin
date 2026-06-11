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

### Personal data (PIPA)

- Every `owner_id`-scoped row is personal data under Korea's PIPA (개인정보보호법) — **including free-text memos**, which can contain anything (health, names, locations).
- **Account deletion must cascade** to all of a user's data (`category`, `sub_tally`, `field_def`, `tag`, `entry`, `entry_tag`, `entry_value`, `match`, `level_rule`, memos) — a deletion that leaves orphaned data is a PIPA failure. Enforce via `ON DELETE CASCADE` from `user`.
- **No memo content (or any `owner_id`-scoped data) may be sent to a third-party API** — no LLM "summarize your progress", no analytics capturing memo text, no error-tracker that might log a memo. Adding any such feature requires a privacy-policy update + fresh explicit consent, never a quiet add.
- Data export/deletion tooling must include memos to make the access/deletion rights honest.
- **Anonymous guest accounts are data subjects too.** A guest `owner_id` (behind a device cookie) holds personal data on our server and is in PIPA scope exactly like a logged-in user. Guests therefore need: disclosure (the 처리방침 covers guests; data is on the server, not on-device — never imply otherwise), a cookie-bound deletion control, and a defined **retention window** enforced by the guest-reaper timer (purge zero-entry guests ~7d, inactive guests ~30d). Never leave un-authenticatable orphan guest rows accumulating.
