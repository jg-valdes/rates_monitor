#!/bin/sh
# Docker entrypoint — runs inside the web container on every start.
#
# Order:
#   1. Apply pending migrations (idempotent, safe on restart)
#   2. Create superuser if DJANGO_SUPERUSER_USERNAME is set (skips if already exists)
#   3. Hand off to gunicorn (PID 1)
#
# Scheduled jobs (fetch_rates) are handled by the APScheduler background
# thread that starts inside gunicorn via RatesConfig.ready().

set -e

log() { echo "[entrypoint] $*"; }

# 1. Migrations
log "Running migrations..."
uv run manage.py migrate --noinput

# 2. Superuser (only runs when the env var is set; safe to re-run — skips if exists)
if [ -n "$DJANGO_SUPERUSER_USERNAME" ]; then
    log "Creating superuser '$DJANGO_SUPERUSER_USERNAME' (no-op if already exists)..."
    uv run manage.py createsuperuser --noinput 2>&1 | grep -v "already exists" || true
fi

# 3. Start gunicorn as PID 1 so Docker signals are handled correctly
log "Starting gunicorn..."
exec uv run gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 1 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
