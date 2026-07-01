# Mushin

Mushin is a social network for people who'd rather log than scroll: no feed, no followers, no strangers — just your record, and the fellows you connect with by mutual consent.

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

### Development workflow

Local: `./run.sh` (starts uvicorn with `--reload` and, if applicable,
the Tailwind watcher). URL: http://127.0.0.1:8000.

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
.agents/     # Project-scope Codex skills/config
AGENTS.md    # Project-level Codex instructions
```

## Deployment

Push to `main` triggers `.github/workflows/deploy.yml`, which SSHes into
the production host and runs `deploy/run.sh` in this repo. See the studio's
`deploy-procedure` skill for the full model.

`deploy/run.sh` handles: git sync (`git fetch + reset --hard`),
`uv sync --frozen --no-dev`, optional Tailwind build, conditional Caddy
config sync from `infra/mushin.caddy`, `systemctl restart`, and
health check via `GET /health`.

GitHub secrets:

- `SSH_HOST` — production host IP or DNS
- `SSH_PRIVATE_KEY` — deploy user's SSH private key

## License

Copyright (c) 2026 AQNAS. All rights reserved. See [LICENSE](LICENSE).
