#!/usr/bin/env bash
# deploy.sh — initial VPS setup + subsequent updates for rates-monitor.
#
# Architecture: single Docker Compose service (web) that runs gunicorn +
# django-crontab inside one container. Caddy is installed separately on the
# host as a reverse proxy (see deploy/Caddyfile and docs/despliegue.md).
#
# Usage:
#   First deploy:   bash deploy/deploy.sh --setup
#   Update only:    bash deploy/deploy.sh
#
# Tested on: Ubuntu 22.04 / 24.04, Debian 12

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SETUP=false

for arg in "$@"; do
    [ "$arg" = "--setup" ] && SETUP=true
done

log()  { echo -e "\033[1;32m[deploy]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*"; }
die()  { echo -e "\033[1;31m[error]\033[0m $*" >&2; exit 1; }

# ── 1. Install Docker (first deploy only) ────────────────────────────────────
if $SETUP; then
    log "Checking Docker installation..."
    if ! command -v docker &>/dev/null; then
        log "Installing Docker..."
        curl -fsSL https://get.docker.com | sh
        usermod -aG docker "$USER" || true
        log "Docker installed. You may need to log out and back in for group changes."
    else
        log "Docker already installed: $(docker --version)"
    fi

    if ! docker compose version &>/dev/null; then
        die "Docker Compose v2 not found. Install Docker Engine >= 23."
    fi
fi

# ── 2. Create .env if it doesn't exist ───────────────────────────────────────

# first update repo
git pull

# validate env configs
ENV_FILE="$APP_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    [ -f "$APP_DIR/.env.example" ] || die ".env.example not found."
    log "Creating .env from .env.example..."
    cp "$APP_DIR/.env.example" "$ENV_FILE"
    warn "Edit $ENV_FILE — set SECRET_KEY, ACCESS_PASSCODE, and ALLOWED_HOSTS."
    warn "Press Enter when ready, or Ctrl-C to abort."
    read -r
fi


# ── 3. Build ──────────────────────────────────────────────────────────────────
cd "$APP_DIR"
log "Building Docker image..."
docker compose build --pull

# ── 4. Start the service ──────────────────────────────────────────────────────
# The entrypoint runs migrations + crontab add before gunicorn starts.
log "Starting web service..."
docker compose up -d

# ── 5. Health check ───────────────────────────────────────────────────────────
log "Waiting for app to be healthy..."
for i in $(seq 1 12); do
    if docker exec -it rates_web uv run python -c \
        "import urllib.request; urllib.request.urlopen('http://localhost:8000/login/')" \
        &>/dev/null 2>&1; then
        log "App is healthy."
        break
    fi
    [ "$i" -eq 12 ] && die "App did not become healthy after 60s. Check: docker compose logs web"
    sleep 5
done

# ── 6. Initial data fetch (first deploy only) ─────────────────────────────────
if $SETUP; then
    log "Fetching last 90 days of rates for all pairs..."
    docker exec -it rates_web uv run manage.py fetch_rates --days 90 --no-alerts
    log ""
    log "Cron jobs installed inside the container:"
    docker exec -it exec web uv run manage.py crontab show
fi

log "──────────────────────────────────────────────────────────"
log "Deployment complete. Service: $(docker compose ps --services)"
if $SETUP; then
    log ""
    log "Next steps:"
    log "  1. Install Caddy on the host (see docs/despliegue.md § Caddy)."
    log "  2. Copy deploy/Caddyfile to /etc/caddy/Caddyfile."
    log "  3. Replace YOUR_DOMAIN in the Caddyfile with your actual domain."
    log "  4. systemctl reload caddy"
fi
