# Deployment Guide — Exchange Rate Monitor

This guide deploys the application to one Linux VPS with Docker Compose, Caddy,
and a persistent SQLite volume.

## Production architecture

```text
Internet
   |
   v
Caddy on host (:80/:443)
   |
   v
web container (:8000, published only as localhost:8003)
   |-- one Gunicorn worker -> Django/HTMX
   |-- one guarded APScheduler background thread
   |
          /app/data/db.sqlite3
          persistent Docker volume
```

Compose starts one low-footprint `web` service. Its entrypoint applies migrations
and optionally creates the administrator with scheduling disabled. Immediately
before Gunicorn starts, it exports `RUN_SCHEDULER=1`; `RatesConfig.ready()` then
starts APScheduler once inside the only web worker.

The flag defaults to false, so tests, migrations, and ordinary management
commands do not create scheduler threads. Keep Gunicorn at one worker. Multiple
workers would each own a scheduler and duplicate jobs.

## Schedule

All times are UTC:

| Job | Schedule | Action |
|---|---|---|
| Morning refresh | Monday-Friday 07:00 | Fetch 3 days and send Telegram snapshots |
| Midday refresh | Monday-Friday 12:30 | Fetch 3 days and send Telegram snapshots |
| Safety backfill | Daily 02:00 | Fetch 90 days or apply the configured OER fallback |

Jobs coalesce missed executions, allow a one-hour misfire grace period, and
permit only one instance of each job at a time.

## VPS requirements

- Ubuntu 22.04/24.04 or Debian 12;
- Docker Engine with Compose v2;
- a domain pointing to the VPS if HTTPS is required;
- at least 1 vCPU, 1 GB RAM, and enough storage for backups;
- outbound HTTPS access to the selected rate source, Telegram, and the CUB URL.

## Configuration

Copy the environment template and set production values:

```bash
cp .env.example .env
```

At minimum, review:

```env
SECRET_KEY=<long-random-value>
DEBUG=False
ALLOWED_HOSTS=rates.example.com
CSRF_TRUSTED_ORIGINS_EXTRA=https://rates.example.com
ACCESS_PASSCODE=<private-access-code>

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

EXCHANGE_RATE_SOURCE=awesomeapi
# OPENEXCHANGERATES_APP_ID=

CUB_SOURCE_URL=https://www.sindusconbc.com.br/cub/
CUB_CURRENT_SOURCE_URL=https://sinduscon-fpolis.org.br/servico/cub-mensal/

DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@example.com
DJANGO_SUPERUSER_PASSWORD=<strong-password>
```

`CUB_SOURCE_URL` provides prior months. `CUB_CURRENT_SOURCE_URL` provides the
current month's "Residencial Médio" card. The source used for each confirmed
value is stored and displayed in the Vivienda workspace. The assisted importer
never saves a value until it is explicitly confirmed.

Do not commit `.env` or copy its secrets into issue reports or logs.

## First deployment

```bash
git clone <repo-url> /opt/rates-monitor
cd /opt/rates-monitor
cp deploy/deploy.template.sh deploy/deploy.sh
chmod +x deploy/deploy.sh
bash deploy/deploy.sh --setup
```

The helper pulls the current branch, creates `.env` if needed, builds the image,
starts Compose, waits for the web health check, and performs the initial rate
load. Review the generated `.env` before continuing when prompted.

Check the application:

```bash
docker compose ps
docker compose logs --tail=100 web
```

## Caddy

Install Caddy on the host, copy `deploy/Caddyfile`, replace `YOUR_DOMAIN`, and
validate before reloading:

```bash
cp deploy/Caddyfile /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

Caddy should proxy to `localhost:8003`. The application port is intentionally
not published on every network interface.

## Updating

From the deployed branch:

```bash
cd /opt/rates-monitor
bash deploy/deploy.sh
docker compose ps
```

The container applies pending migrations before enabling the in-process
scheduler and starting Gunicorn.

For safer releases, take a database backup first and verify CI on the commit
being deployed.

## Operations

### Logs

```bash
docker compose logs -f web
```

### Status and health

```bash
docker compose ps
curl -I http://localhost:8003/login/
```

### Manual rate refresh

```bash
docker compose exec web uv run manage.py fetch_rates --days 3
```

### Django checks

```bash
docker compose exec web uv run manage.py check
docker compose exec web uv run manage.py showmigrations
```

### Restart the application

```bash
docker compose restart web
```

## SQLite backup and restore

SQLite is appropriate for the current single-owner, single-host workload. Back
it up using SQLite's online backup command so the copy is consistent while the
application is running.

Create a dated host directory and run:

```bash
mkdir -p backups
docker compose exec -T web uv run python manage.py shell -c \
  "import sqlite3; source=sqlite3.connect('/app/data/db.sqlite3'); target=sqlite3.connect('/app/data/backup.sqlite3'); source.backup(target); target.close(); source.close()"
docker compose cp web:/app/data/backup.sqlite3 backups/db-$(date +%Y%m%d-%H%M%S).sqlite3
```

Copy backups to storage outside the VPS and define a retention policy. A backup
is not proven until a restore drill succeeds.

To restore, first stop the application and preserve the current database:

```bash
docker compose stop web
docker compose cp web:/app/data/db.sqlite3 backups/db-before-restore.sqlite3
docker compose cp backups/<backup-file>.sqlite3 web:/app/data/db.sqlite3
docker compose up -d web
docker compose exec web uv run manage.py check
```

Verify the dashboard, a property plan, stored payments, and CUB history after
restoration. Keep the pre-restore copy until verification is complete.

## Troubleshooting

### Web is unhealthy

```bash
docker compose logs --tail=200 web
docker compose exec web uv run manage.py check
```

Typical causes are invalid production hosts/origins, a missing data directory,
or a failed migration.

### Scheduler is not running

```bash
docker compose ps web
docker compose logs --tail=200 web
```

Look for APScheduler startup or job messages in the web log. Confirm the
entrypoint exports `RUN_SCHEDULER=1` and Gunicorn still uses exactly one worker.
Do not start `manage.py run_scheduler` beside the production container.

### CUB import fails

Open the exact URL shown in the Vivienda workspace. Confirm that
both CUB source URLs are reachable from the browser and the container:

```bash
docker compose exec web uv run python -c \
  "import os, requests; [(lambda r, u: print(r.status_code, u))(requests.get(u, timeout=15), u) for u in (os.environ['CUB_SOURCE_URL'], os.environ['CUB_CURRENT_SOURCE_URL'])]"
```

The failure does not modify saved CUB values. Enter a verified value manually
with its source URL if the official page layout changed.

## When to leave SQLite

Do not migrate databases merely to make the product appear more mature. Move to
PostgreSQL when there are multiple application hosts, meaningful concurrent
writes, tenant isolation/reporting requirements, or stricter recovery targets.
Those triggers and the surrounding SaaS work are defined in
[product-roadmap.md](product-roadmap.md).
