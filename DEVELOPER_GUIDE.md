# Developer Guide — mushin

How the infrastructure works, how to develop locally, and what to do when things break.

---

## 1. Repo structure

```
mushin/
├── app/                          # FastAPI application
│   ├── main.py                   # App factory, routes, lifespan hook
│   ├── models.py                 # Database models (if using SQLite)
│   ├── database.py               # SQLite engine, pragmas, session factory
│   ├── routes/                   # Route modules
│   ├── static/                   # CSS, JS, images
│   │   └── src/input.css         # Tailwind v4 source (style.css built at runtime, gitignored)
│   └── templates/                # Jinja2 templates
├── infra/                        # Server config and operational scripts
│   ├── mushin.caddy      # Per-site Caddy config: TLS, headers, reverse proxy
│   └── mushin.service    # systemd unit
├── deploy/
│   └── run.sh                    # Deploy entry point (called by GitHub Actions)
├── .github/workflows/
│   └── deploy.yml                # SSH deploy on push to main
├── run.sh                        # Local dev server (Tailwind watcher + uvicorn)
├── AGENTS.md                     # Project-level Codex instructions
├── pyproject.toml
└── uv.lock
```

### Where each `infra/` file lives on the server

| Repo file | Server location |
|-----------|----------------|
| `infra/mushin.caddy` | `/etc/caddy/conf.d/mushin.caddy` |
| `infra/mushin.service` | `/etc/systemd/system/mushin.service` |

`bootstrap-project.sh` (from the studio repo) installs these on first deploy.
`deploy/run.sh` re-syncs the Caddy config on subsequent deploys when it changes.

---

## 2. Server users

| User | Purpose | Scope |
|------|---------|-------|
| `mushin` | Runs the app via systemd | Owns `/opt/mushin/mushin/` and `/opt/mushin/data/`. No sudo, no login shell. |
| `deploy` | GitHub Actions deploys | In `mushin` group (group-write access to repo). Allowed via sudoers: `systemctl restart mushin`, `systemctl reload caddy`, `systemctl status *`, `cp infra/*.caddy /etc/caddy/conf.d/`. No `.env` access (`.env` is mode 600 owned by service user). |
| `ubuntu` | Manual admin (you) | Full sudo. Nothing automated uses this user. |

Blast radius containment: app exploit = trapped in `mushin` (no sudo,
`NoNewPrivileges=true`). Deploy key leak = can push code but can't read `.env`
or escalate. See `deploy/run.sh` and the infra files for the ownership model.

### systemd sandboxing (`infra/mushin.service`)

Defaults: `NoNewPrivileges=true`, `ProtectSystem=strict`, `ProtectHome=true`,
`PrivateTmp=true`, `ReadWritePaths=/opt/mushin/data /opt/mushin/.uv-cache`.

---

## 3. Deploy flow

Push to `main` → GitHub Actions SSHes into the production host as `deploy` → runs `deploy/run.sh` in this repo.

The workflow itself is a thin one-liner:

```yaml
- name: Deploy
  run: |
    ssh deploy@$SSH_HOST "cd /opt/mushin/mushin && bash deploy/run.sh"
```

`deploy/run.sh` then runs six steps:

1. **Git sync** — `sg "mushin" -c "git fetch origin main && git reset --hard origin/main"`. Uses `sg` to activate the `mushin` group for the wrapped command (ensures git's writes inside `.git/objects/` land with consistent group ownership, since deploy's primary group is `deploy`). Uses `reset --hard` (not `pull`) so any server-side divergence is discarded — source of truth is `origin/main`.
2. **Dependency sync** — `uv sync --frozen --no-dev`. Honors `uv.lock`; refuses to update.
3. **Asset build** (if applicable) — auto-installs the Tailwind standalone CLI to `~/.local/bin/tailwindcss` if missing, then runs `tailwindcss --minify`. Skipped if `app/static/src/input.css` doesn't exist (non-Tailwind projects).
4. **Caddy config sync** (if changed) — diffs `infra/mushin.caddy` against `/etc/caddy/conf.d/mushin.caddy`. Copies via `sudo cp` and `sudo systemctl reload caddy` if different. Skipped if missing or unchanged.
5. **Service restart** — `sudo systemctl restart mushin`.
6. **Health check** — polls `http://127.0.0.1:8013/health` up to 5 times (2s intervals). Fails if no HTTP 200.

Concurrency: GitHub Actions serializes per-workflow by default (second deploy waits for first). Job timeout: 5 minutes.

GitHub secrets required:
- `SSH_HOST` — production host IP or DNS
- `SSH_PRIVATE_KEY` — deploy user's SSH private key (paste contents including the `-----BEGIN`/`-----END` markers)

---

## 4. Architecture

```
Internet → Cloudflare DNS → Production host (Ubuntu 24.04)
  ├── Caddy (80/443, auto TLS via Cloudflare DNS challenge)
  │   ├── /static/* → file_server from /opt/mushin/mushin/app/static/
  │   ├── /* → reverse_proxy 127.0.0.1:8013 (sets X-Real-IP)
  │   └── www.mushin.aqnas.xyz → 301 → mushin.aqnas.xyz
  ├── uvicorn (2 workers, systemd as mushin user)
  │   ├── / — main app routes
  │   ├── /health — {"status": "ok"}
  │   └── ... (project-specific routes — document below)
  └── SQLite WAL → /opt/mushin/data/app.db (if project uses SQLite)
```

### Project-specific routes

{Document the main entry points: paths, what they return, auth requirements.}

### Network security

- Ingress: ports 22, 80, 443 only (cloud security list + UFW on host)
- fail2ban: 3 SSH failures in 10 min → 1 hour ban
- SSH: key-based only, `PermitRootLogin prohibit-password`
- Unattended security upgrades enabled (no auto-reboot)

### Security headers (Caddy)

Defaults set in `infra/mushin.caddy`:
- CSP: tight by default — `default-src 'self'`, restrict scripts and styles
- HSTS: 1 year, includeSubDomains, preload
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Server` header removed

Customize CSP for your project — add CDN domains, font hosts, analytics, etc. as needed.

---

## 5. CSS architecture (if using Tailwind)

Tailwind CSS v4 with `@theme` in `app/static/src/input.css`. The compiled output `app/static/style.css` is gitignored and built at runtime:

- **Dev:** `run.sh` spawns `tailwindcss --watch` in background alongside uvicorn
- **Prod:** `deploy/run.sh` runs `tailwindcss --minify` before restarting the service

### Build pipeline

```
app/static/src/input.css  →  tailwindcss CLI  →  app/static/style.css (gitignored)
```

`input.css` uses three Tailwind v4 directives:
- `@import "tailwindcss"` — pulls in the framework
- `@source "..."` — paths Tailwind scans for utility classes (typically `../../templates/**/*.jinja2`, `../../static/*.js`)
- `@theme { ... }` — project color, font, spacing definitions

### Component extraction convention

When a single element exceeds ~10 Tailwind utility classes, extract it to a named class in `@layer components` inside `input.css`. Document the resulting component classes in this section.

---

## 6. Database (if using SQLite)

- **Production:** `/opt/mushin/data/app.db` (via `DATABASE_URL` env var)
- **Local dev:** `./app.db` in working directory (default)

### Pragmas (set on every connection)

WAL mode, 5s busy timeout, 1000-page autocheckpoint, 64 MiB journal limit, foreign keys ON.

### Schema

{Describe your tables: name, key columns, indexes, foreign keys, any seeding behavior on first startup.}

### Migrations

Manual (Alembic planned). Document any migration steps performed here.

---

## 7. Backups

Daily SQLite snapshot, taken via `infra/mushin-backup.timer` →
`infra/mushin-backup.service` (oneshot, `User=mushin`), which runs
`infra/backup.sh`.

### Snapshot, never `cp`

WAL mode keeps recent writes in `app.db-wal`, separate from `app.db`. A raw
`cp`/`rclone` of `app.db` while the app is running can capture a `.db` file
that's missing those writes — a corrupt-looking, incomplete snapshot. The
backup script **always** uses SQLite's online backup API via the `sqlite3`
CLI:

```bash
sqlite3 /opt/mushin/data/app.db ".backup '/opt/mushin/data/backups/app-<timestamp>.db'"
```

This produces a single self-contained, consistent file regardless of
concurrent writers.

### What the script does (`infra/backup.sh`)

1. `.backup` snapshot to `/opt/mushin/data/backups/app-<UTC timestamp>.db`
   (directory created if missing).
2. `PRAGMA integrity_check` on the snapshot — if it doesn't return `ok`, the
   snapshot is deleted and the script exits non-zero (failure is visible via
   `systemctl status mushin-backup` / `journalctl -u mushin-backup`).
3. Rotation: keeps the newest `MUSHIN_BACKUP_RETENTION` snapshots (default 7,
   ~one week of daily backups), deletes older ones.

Configurable via environment (set in `/opt/mushin/.env` if overriding
defaults):

| Variable | Default | Meaning |
|---|---|---|
| `MUSHIN_DB_PATH` | `/opt/mushin/data/app.db` | Source DB |
| `MUSHIN_BACKUP_DIR` | `/opt/mushin/data/backups` | Snapshot output directory |
| `MUSHIN_BACKUP_RETENTION` | `7` | Number of daily snapshots to keep |
| `MUSHIN_BACKUP_DATE_STAMP` | `$(date -u +%Y%m%d-%H%M%S)` | Override for testing/reproducibility |

### Timer

`mushin-backup.timer` runs `mushin-backup.service` daily at 03:15 UTC (with up
to a 5-minute random delay to avoid thundering-herd on shared hosts).
`Persistent=true` means a missed run (host was down) fires shortly after boot.

### Off-host copy

`/opt/mushin/data/backups/` is **inside** `mushin.service`'s existing
`ReadWritePaths=/opt/mushin/data` — no systemd unit change was needed for
either new timer. The existing host-level rclone job ships the contents of
`/opt/mushin/data/backups/` to off-host object storage; this repo doesn't run
rclone itself.

### Install (one-time, on the production host)

```bash
sudo cp infra/mushin-backup.service infra/mushin-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mushin-backup.timer
```

### Restore

```bash
sudo systemctl stop mushin
sudo -u mushin cp /opt/mushin/data/backups/app-<timestamp>.db /opt/mushin/data/app.db
sudo systemctl start mushin
```

(Stopping the service first avoids restoring under a live WAL.)

---

## 8. Guest retention (PIPA)

Anonymous guest accounts (`user.auth_provider = 'guest'`, no signup) are
personal data on the server, in scope for Korea's PIPA exactly like a
logged-in account. Two retention windows, enforced daily by
`infra/mushin-guest-reaper.timer` → `infra/mushin-guest-reaper.service`
(oneshot, `User=mushin`), which runs `uv run python -m app.services.guest_reaper`:

| Condition | Default window | Rule |
|---|---|---|
| Zero-entry guest | **7 days** | `user.created_at` older than 7 days AND no rows in `entry` for that owner |
| Inactive guest | **30 days** | `user.last_active_at` (or `created_at` if never set) older than 30 days, regardless of entry count |

Either condition alone is sufficient to purge. A purge deletes the `user` row;
`ON DELETE CASCADE` from `user` (migration 0001) removes every dependent row
(`category`, `activity`, `field_def`, `tag`, `entry`, `entry_tag`,
`entry_value`, `match`) in the same transaction — no orphans.

**Real accounts (`kakao`, `google`, `email`) are never matched** — the purge
query is hard-filtered to `auth_provider = 'guest'`.

These two windows (7 days zero-entry / 30 days inactive) are the values to
cite in the 개인정보처리방침 guest-data retention disclosure.

### Implementation

- Logic: `app/services/guest_reaper.py` — `purge_guests(conn, *, now, zero_entry_days=7, inactive_days=30, dry_run=False)`. `now` is injectable for tests; this is the only place in the codebase that legitimately queries across all owners (a maintenance job, not a request-path accessor — kept separate from the owner-scoped helpers in `app/services/_db.py`).
- CLI: `uv run python -m app.services.guest_reaper [--dry-run] [--zero-entry-days N] [--inactive-days N]`.

### Dry run

```bash
cd /opt/mushin/mushin
uv run python -m app.services.guest_reaper --dry-run
```

Logs (via structlog, `guest_reaper.would_purge`) every user id that *would* be
purged, without deleting anything. Useful for verifying the thresholds before
trusting the timer.

### Timer

`mushin-guest-reaper.timer` runs daily at 03:45 UTC (staggered after the
backup timer), with up to a 5-minute random delay and `Persistent=true`.

### Install (one-time, on the production host)

```bash
sudo cp infra/mushin-guest-reaper.service infra/mushin-guest-reaper.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mushin-guest-reaper.timer
```

---

## 9. Local development

### Quick start

```bash
./run.sh    # Tailwind watcher (background, if applicable) + uvicorn --reload on :8000
```

No `.env` needed for first-run if the database auto-creates with seed data.

### Environment

Recommended: OrbStack Ubuntu 24.04 container (`aqnas-dev`). Avoids macOS-specific quirks; matches production OS.

### Common dev commands

```bash
./run.sh                              # Start dev server
uv run pytest                         # Run tests
uv add <package>                      # Add a dependency (updates pyproject.toml + uv.lock)
uv sync                               # Sync deps from uv.lock
```

---

## 10. Monitoring and break-glass

### Monitoring

- **UptimeRobot or similar:** monitor `https://mushin.aqnas.xyz/health` for 200 OK
- **Health endpoint:** `GET /health` → `{"status": "ok"}`
- **App logs:** `journalctl -u mushin -f`
- **Caddy logs:** `/var/log/caddy/mushin-access.log`

### Break-glass (can't SSH in)

1. Cloud provider console → select VM
2. Open the console/serial connection
3. Log in as `ubuntu`, fix the issue

The serial console bypasses the network entirely. Document the exact navigation path for your cloud provider here.

---

## Appendix: Secrets and auth

### Secrets

| Secret | Location | Used by |
|--------|----------|---------|
| `{secret-name}` | `/opt/mushin/.env` (prod) | `{where used}` |
| `SSH_HOST` | GitHub repo secret | `deploy.yml` |
| `SSH_PRIVATE_KEY` | GitHub repo secret | `deploy.yml` |

**Not in git:** `.env`, `app.db`, backup files, secret values.

### Rate limiting (if applicable)

{Document any per-endpoint rate limits and the library used (e.g. slowapi).}

### Auth (if applicable)

{Document the project's auth model — HTTP Basic, session cookies, OAuth, etc.
Include any anti-brute-force measures and CSRF approach.}
