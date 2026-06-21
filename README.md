# Mushin

Mushin is a social network for people who'd rather log than scroll: no feed, no followers, no strangers — just your record, and the fellows you connect with by mutual consent.

Part of the [AQNAS](https://aqnas.xyz) studio.

## Stack

- Python 3.12, FastAPI, uvicorn
- Jinja2 templates
- HTMX v2 (web), Hyperview/HXML (mobile)
- SQLite with WAL journaling
- Tailwind v4
- Caddy v2 (TLS via Cloudflare DNS challenge)
- systemd on Ubuntu 24.04

## Development

```sh
# Install uv if you haven't: https://docs.astral.sh/uv/
uv sync

# Copy env template and fill in
cp .env.example .env

# Run locally
uv run uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000`.

## Testing

```sh
uv run pytest
```

End-to-end tests use Playwright via the `playwright-cli` skill — see `tests/e2e/`.

## Deploy

Automated via GitHub Actions on push to `main`. The workflow SSHes to the production host, pulls, runs `uv sync`, and restarts the systemd service.

First-time setup of a new deploy target requires manual bootstrap — see `deploy/bootstrap.sh` and the `deploy-procedure` skill in [aqnas-studio](https://github.com/yjaquinas/aqnas-studio).

## Structure

```
app/         # FastAPI app (routes, models, services)
templates/
  web/       # HTMX templates (.html.jinja2)
  mobile/    # Hyperview templates (.hxml.jinja2)
  components/ # Shared fragments
mobile-client/ # React Native shell
tests/       # pytest (unit, integration, e2e)
deploy/      # Caddy + systemd configs, bootstrap
meetings/    # Meeting outputs from /run-meeting
.claude/     # Project-scope Claude Code config
```

## License

Copyright (c) 2026 AQNAS. All rights reserved. See [LICENSE](LICENSE).
