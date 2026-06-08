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

_(Add any project-wide rules here — naming conventions, domain constraints, integration specifics.)_
