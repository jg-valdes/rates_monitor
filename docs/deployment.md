# Deployment Guide — Exchange Rate Monitor

How to run the system in production on a VPS using a single Docker container that
runs both the web server and the scheduled tasks (django-crontab), with Caddy
installed on the host as a reverse proxy with automatic HTTPS.

---

## Production architecture

```
Internet
   │
   ▼
Caddy (host)  :80 / :443     ← reverse proxy + automatic TLS (Let's Encrypt)
   │                            installed directly on the operating system
   │ proxy_pass localhost:8003
   ▼
Docker: web  :8000            ← Django + Gunicorn (PID 1)
              └─ cron (same container) ← django-crontab + system cron daemon
              └─ /app/data/db.sqlite3 ← persistent Docker volume
```

**A single container** holds both the web server and the task scheduler.
Caddy runs outside Docker, directly on the host, and acts as the sole public
entry point.

---

## How the cron works (django-crontab)

`django-crontab` registers Django tasks in the operating system crontab of the
container. Debian's `cron` daemon runs in the background inside the same
container as gunicorn.

**Configuration in `config/settings.py`:**

```python
CRONJOBS = [
    ("0 * * * *",  "rates.cron.fetch_rates_hourly"),         # every hour
    ("0 2 * * *",  "rates.cron.fetch_rates_daily_backfill"), # 02:00 UTC daily
]
```

**What each task does:**

| Task | Schedule | Equivalent command |
|---|---|---|
| `fetch_rates_hourly` | Every hour | `manage.py fetch_rates --days 3` (with alerts) |
| `fetch_rates_daily_backfill` | 02:00 UTC | `manage.py fetch_rates --days 90 --no-alerts` |

The container entrypoint (`deploy/entrypoint.sh`) runs on startup:

```
migrate → crontab add → cron (bg) → gunicorn (fg, PID 1)
```

This means jobs are installed into the crontab on every container restart,
which is safe and idempotent.

**View registered jobs:**

```bash
docker compose exec web uv run manage.py crontab show
```

**Run a job manually:**

```bash
docker compose exec web uv run manage.py fetch_rates --days 3
```

---

## VPS requirements

- Ubuntu 22.04 / 24.04 or Debian 12
- 1 vCPU, 512 MB RAM
- Docker Engine ≥ 23 (includes Compose v2)
- Ports 80 and 443 open in the firewall
- A domain pointing to the server (required for Caddy's TLS certificate)

---

## First deployment

### 1. Clone the repository

```bash
git clone <repo-url> /opt/rates-monitor
cd /opt/rates-monitor
```

### 2. Create and edit `.env`

```bash
cp .env.example .env
nano .env
```

Minimum required values:

```env
SECRET_KEY=<50-character-random-string>
DEBUG=False
ALLOWED_HOSTS=yourdomain.com
CSRF_TRUSTED_ORIGINS_EXTRA=yourdomain.com
ACCESS_PASSCODE=<your-access-code>
```

To generate `SECRET_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

### 3. Run the deployment script

```bash
cp deploy/deploy.template.sh deploy/deploy.sh
chmod +x deploy/deploy.sh
bash deploy/deploy.sh --setup
```

The script:
1. Installs Docker if not present
2. Builds the Docker image
3. Starts the container (the entrypoint applies migrations and installs the crontab automatically)
4. Verifies the app responds at `localhost:8000` (inside the container)
5. Loads 90 days of initial rate data

### 4. Install and configure Caddy on the host

```bash
# Ubuntu / Debian
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install caddy
```

### 5. Configure the Caddyfile

The repository includes a template at `deploy/Caddyfile`. Copy and edit it:

```bash
cp /opt/rates-monitor/deploy/Caddyfile /etc/caddy/Caddyfile
nano /etc/caddy/Caddyfile
```

Replace `YOUR_DOMAIN` with your actual domain:

```caddy
yourdomain.com {
    reverse_proxy localhost:8003
    ...
}
```

Apply the configuration:

```bash
caddy validate --config /etc/caddy/Caddyfile   # verify syntax
systemctl reload caddy
```

Caddy issues and renews the TLS certificate automatically. Check the status:

```bash
systemctl status caddy
journalctl -u caddy -f
```

---

## Updates

```bash
cd /opt/rates-monitor
# only if you've made changes to deploy.template.sh; you should pull changes and repeat steps for copy template and give it executable permission)
# git pull (if deploy template ahs changes) + repeat steps for copy template and chmod +x
bash deploy/deploy.sh
```

The script rebuilds the image and restarts the container. The entrypoint applies
pending migrations and installs updated cron jobs on every startup.

---

## Common operations

### Logs

```bash
docker compose logs -f web      # gunicorn + cron job output
docker compose logs web         # full history
```

Cron jobs log through Django's logging system, so their output appears mixed
with gunicorn logs in the same stream.

### Restart the container

```bash
docker compose restart web
```

### Shell inside the container

```bash
docker compose exec web bash
```

### Management commands

```bash
# View registered cron jobs
docker compose exec web uv run manage.py crontab show

# Force an update now
docker compose exec web uv run manage.py fetch_rates --days 3

# Specific pair
docker compose exec web uv run manage.py fetch_rates --pair usd-brl --days 90

# Create superuser for /admin/
docker compose exec web uv run manage.py createsuperuser

# Django shell
docker compose exec web uv run manage.py shell
```

### Database backup

```bash
# Copy inside the volume (stays in /app/data/)
docker compose exec web cp /app/data/db.sqlite3 /app/data/db.backup.$(date +%Y%m%d).sqlite3

# Download to the host
docker run --rm \
  -v rates-monitor_data:/data \
  -v $(pwd):/backup \
  alpine cp /data/db.sqlite3 /backup/db_backup_$(date +%Y%m%d).sqlite3
```

### Reload Caddy (after Caddyfile changes)

```bash
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Django secret key. Generate randomly. |
| `DEBUG` | Yes | Must be `False` in production. |
| `ALLOWED_HOSTS` | Yes (prod) | Comma-separated domains/IPs. Required when `DEBUG=False`. |
| `CSRF_TRUSTED_ORIGINS_EXTRA` | Yes (prod) | Comma-separated origins for CSRF validation (e.g. `https://yourdomain.com`). |
| `ACCESS_PASSCODE` | No | Site access passcode. Empty = no protection. |
| `TELEGRAM_BOT_TOKEN` | No | Telegram bot token from @BotFather. Both Telegram vars must be set for alerts to send. |
| `TELEGRAM_CHAT_ID` | No | Target Telegram chat/group/channel ID. |
| `DATA_DIR` | No | Database directory. Docker Compose sets this to `/app/data`. |
| `EXCHANGE_RATE_SOURCE` | No | `awesomeapi` (default, free) or `openexchangerates`. |
| `OPENEXCHANGERATES_APP_ID` | No* | Required when `EXCHANGE_RATE_SOURCE=openexchangerates`. |

**Default source:** [AwesomeAPI](https://economia.awesomeapi.com.br) — free, no registration,
no API key. Requests are throttled automatically: 1 s delay between pairs and exponential
backoff on HTTP 429 responses.

**Alternative source:** [Open Exchange Rates](https://openexchangerates.org) — set
`EXCHANGE_RATE_SOURCE=openexchangerates` and provide `OPENEXCHANGERATES_APP_ID`. The free
plan supports current rates only; historical backfills require a paid plan (the app detects
the plan tier automatically and falls back to current-only on HTTP 403).

When `DEBUG=False`, the following security settings are applied automatically —
no additional env vars are needed:

| Setting | Value |
|---|---|
| `SECURE_SSL_REDIRECT` | `True` |
| `SECURE_HSTS_SECONDS` | `31536000` (1 year, with subdomains + preload) |
| `SESSION_COOKIE_SECURE` | `True` |
| `CSRF_COOKIE_SECURE` | `True` |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `True` |

> Caddy already handles HTTPS termination and HTTP→HTTPS redirects on the host.
> `SECURE_SSL_REDIRECT` inside Django causes no double-redirect because Caddy
> forwards the `X-Forwarded-Proto: https` header, which Django reads correctly.

---

## Caddy — template reference

The `deploy/Caddyfile` file is a ready-to-copy template. It is designed for
Caddy running on the host, proxying to the Docker container at `localhost:8003`.

```caddy
YOUR_DOMAIN {
    reverse_proxy localhost:8003

    header {
        X-Frame-Options        DENY
        X-Content-Type-Options nosniff
        Referrer-Policy        strict-origin-when-cross-origin
    }

    log {
        output stdout
        format console
    }
}
```

Caddy automatically handles:
- TLS certificate from Let's Encrypt (issuance and renewal)
- HTTP → HTTPS redirect
- TLS 1.2 / 1.3 with modern cipher suites
- HTTP/3 (QUIC)

**For local development without a domain**, replace `YOUR_DOMAIN` with `localhost`
and Caddy will use a locally-trusted self-signed certificate. Or use `:80` to
serve without TLS.

---

## Troubleshooting

**App not responding at `localhost:8003`**

```bash
docker compose logs web         # look for gunicorn or migration errors
docker compose ps               # verify the container is running
```

**Caddy not issuing the TLS certificate**

```bash
journalctl -u caddy -n 50
# Common causes:
# - Port 80 or 443 not reachable from the internet
# - Domain does not point to the server's IP
# - YOUR_DOMAIN was not replaced in the Caddyfile
```

**Cron not running the tasks**

```bash
# Check what is in the system crontab inside the container
docker compose exec web crontab -l

# Verify the cron daemon is running
docker compose exec web pgrep cron && echo "OK" || echo "cron not running"

# Reinstall manually
docker compose exec web uv run manage.py crontab remove
docker compose exec web uv run manage.py crontab add
docker compose exec web uv run manage.py crontab show
```

**Migration errors on update**

```bash
docker compose stop web
docker compose run --rm web uv run manage.py migrate --noinput
docker compose start web
```

**`database is locked` (SQLite concurrency)**

Under normal conditions this should not occur because only one process writes
(gunicorn has 1 worker and cron runs one job at a time thanks to
`CRONTAB_LOCK_JOBS = True`). If it persists, migrate to PostgreSQL.

---

## Migrating to PostgreSQL (optional)

1. `uv add psycopg2-binary`
2. Update `DATABASES` in `config/settings.py`
3. Add a `db` service in `docker-compose.yml`
4. Export: `docker compose exec web uv run manage.py dumpdata > backup.json`
5. `migrate` + `loaddata backup.json`
