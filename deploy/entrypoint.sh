#!/bin/sh
# Docker entrypoint — runs inside the web container on every start.
#
# Order:
#   1. Apply pending migrations (idempotent, safe on restart)
#   2. Register cron jobs with the system crontab via django-crontab
#   3. Start the system cron daemon in the background
#   4. Hand off to gunicorn (PID 1)

set -e

log() { echo "[entrypoint] $*"; }

# 1. Migrations
log "Running migrations..."
uv run manage.py migrate --noinput

# 2. Register jobs — django-crontab writes to the user's crontab.
#    Running this on every start is safe: it replaces the existing entries.
log "Installing cron jobs..."
uv run manage.py crontab add

log "Registered jobs:"
uv run manage.py crontab show

# 3. Start cron daemon (Debian's cron daemonises itself, freeing the shell)
log "Starting cron daemon..."
cron

# 4. Start gunicorn as PID 1 so Docker signals are handled correctly
log "Starting gunicorn..."
exec uv run gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 1 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
