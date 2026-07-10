# Mushin

Mushin (無心, "no-mind") is a social network for people who track. Log
activities, share your journey, and connect with others who show up. Public
profiles, mutual fellows connections, comments, and discovery make it a place
to share progress — not just record it.

The backend serves shared service-layer data through web HTMX templates and
native hypermedia surfaces.

## Stack

- Python 3.12, FastAPI, uv, Uvicorn
- Jinja2 templates
- HTMX v2 for web interactions
- Hyperview/HXML mobile surface, with `mobile-client/` as the React Native shell
- SQLite with WAL journaling
- Tailwind CSS v4
- Caddy v2 and systemd on Ubuntu 24.04

## Quick Start

```sh
uv sync
cp .env.example .env  # if needed for your local config
./run.sh
```

Visit `http://127.0.0.1:8000`. `./run.sh` starts Uvicorn with reload and, when
applicable, the Tailwind watcher.

Common commands:

```sh
uv run pytest
uv add <package>
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

## Structure

```text
app/
  auth/          # Session, OAuth, password, and user helpers
  middleware/    # Request middleware
  models/        # SQLite connection and migrations
  routes/        # FastAPI routes for web, public, admin, and data IO
  services/      # Shared owner-scoped business logic
  static/        # Tailwind source/output, JS, icons, images
  templates/     # Jinja2 pages and components
deploy/          # Production deploy entry point
infra/           # Caddy, systemd, backup, and retention units/scripts
meetings/        # Meeting outputs
mobile-client/   # Native shell
tests/           # pytest tests
.agents/         # Project-scope agent skills/config
AGENTS.md        # Codex/project automation instructions
```

## Application Model

The core model is `activity -> entry`. Authentication is required for product
use. Usernames are stable public identifiers, and private accounts may still be
discoverable by identity and activity names.

Visibility behavior:

- `public`: full record, including notes, visible to anyone.
- `private`: `/@{username}` shows activity names, counts, and non-clickable
  cards; `/@{username}/{slug}` redirects back to `/@{username}`.
- Fellows: accepted mutual connections can see the full record, including notes.

Every request-path query must be scoped by `owner_id`. User-facing copy is
centralized in `app/ui_strings.py`.

## CSS

Tailwind CSS v4 uses `@theme` in `app/static/src/input.css`. The compiled file
is `app/static/style.css`.

Build pipeline:

```text
app/static/src/input.css -> tailwindcss CLI -> app/static/style.css
```

Development runs the watcher through `./run.sh`. Commit the generated
`app/static/style.css`; production deploy verifies that tracked file is present
and does not build CSS on the server or in GitHub Actions.

## Database

Production SQLite data lives under `/opt/mushin/data/`, normally configured by
`DATABASE_PATH`. Local development defaults to `./data/app.db`.

Connections enable WAL mode, busy timeout, WAL autocheckpointing, journal size
limits, and foreign keys. Migrations live in `app/models/migrations`.

Do not copy a live WAL database with raw `cp` for backups. Use SQLite's online
backup API, as implemented by `infra/backup.sh`.

## Deployment

Pushes to `main` trigger `.github/workflows/deploy.yml`, which SSHes to the
production host as `deploy` and runs:

```sh
cd /opt/mushin/mushin && bash deploy/run.sh
```

`deploy/run.sh` performs:

1. Git sync to `origin/main`.
2. `uv sync --frozen --no-dev`.
3. Verify committed CSS exists at `app/static/style.css`.
4. Conditional Caddy config sync from `infra/mushin.caddy`.
5. `systemctl restart mushin`.
6. Health check against `http://127.0.0.1:8013/health`.

Required GitHub secrets:

- `SSH_HOST`: production host IP or DNS.
- `SSH_PRIVATE_KEY`: deploy user's SSH private key.

## Production Operations

Production layout:

```text
Internet -> Caddy :80/:443 -> Uvicorn 127.0.0.1:8013 -> SQLite WAL
```

Server users:

- `mushin`: runs the app, owns `/opt/mushin/mushin/` and `/opt/mushin/data/`,
  has no sudo and no login shell.
- `deploy`: used by GitHub Actions, has limited sudo for service reload/restart
  and Caddy config sync, and must not have `.env` access.
- `ubuntu`: manual break-glass admin.

The `deploy` user needs non-interactive sudo for the commands used by
`deploy/run.sh`. Install this with `visudo -f /etc/sudoers.d/mushin-deploy`:

```sudoers
deploy ALL=(root) NOPASSWD: /usr/bin/cp /opt/mushin/mushin/infra/mushin.caddy /etc/caddy/conf.d/mushin.caddy
deploy ALL=(root) NOPASSWD: /usr/bin/systemctl reload caddy, /usr/bin/systemctl restart mushin
```

Then set the sudoers file mode:

```sh
sudo chmod 440 /etc/sudoers.d/mushin-deploy
```

Important server paths:

- `infra/mushin.caddy` -> `/etc/caddy/conf.d/mushin.caddy`
- `infra/mushin.service` -> `/etc/systemd/system/mushin.service`
- Database and backups -> `/opt/mushin/data/`
- Production environment -> `/opt/mushin/.env`

Useful commands:

```sh
journalctl -u mushin -f
journalctl -u mushin-backup
journalctl -u mushin-guest-reaper
sudo systemctl status mushin
sudo systemctl reload caddy
```

## Backups

Daily SQLite snapshots are handled by:

- `infra/mushin-backup.timer`
- `infra/mushin-backup.service`
- `infra/backup.sh`

The backup script writes an online `.backup` snapshot, runs
`PRAGMA integrity_check`, and rotates old snapshots. Defaults:

- `MUSHIN_DB_PATH=/opt/mushin/data/app.db`
- `MUSHIN_BACKUP_DIR=/opt/mushin/data/backups`
- `MUSHIN_BACKUP_RETENTION=7`

One-time install on production:

```sh
sudo cp infra/mushin-backup.service infra/mushin-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mushin-backup.timer
```

Restore:

```sh
sudo systemctl stop mushin
sudo -u mushin cp /opt/mushin/data/backups/app-<timestamp>.db /opt/mushin/data/app.db
sudo systemctl start mushin
```

## Guest Retention

Guest retention is enforced by:

- `infra/mushin-guest-reaper.timer`
- `infra/mushin-guest-reaper.service`
- `app/services/guest_reaper.py`

Rules:

- Zero-entry guests are purged after 7 days.
- Inactive guests are purged after 30 days.
- Real accounts using `kakao`, `google`, or `email` are never matched.

Dry run:

```sh
uv run python -m app.services.maintenance.guest_reaper --dry-run
```

One-time install on production:

```sh
sudo cp infra/mushin-guest-reaper.service infra/mushin-guest-reaper.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mushin-guest-reaper.timer
```

## Monitoring

- Health endpoint: `GET /health` returns `{"status": "ok"}`.
- External monitor target: `https://mushin.aqnas.xyz/health`.
- App logs: `journalctl -u mushin -f`.
- Caddy access logs: `/var/log/caddy/mushin-access.log`.

If SSH is unavailable, use the cloud provider's console or serial connection
and log in as `ubuntu`.

## Secrets

Do not commit `.env`, local databases, backup files, or secret values.

Production secrets live in `/opt/mushin/.env`. Deploy secrets live in GitHub
Actions as `SSH_HOST` and `SSH_PRIVATE_KEY`.

## License

Copyright (c) 2026 AQNAS. All rights reserved. See [LICENSE](LICENSE).
