# Exchange Rate Monitor

Personal tool to find the best timing and route for converting
Uruguayan Pesos (UYU) to Brazilian Reais (BRL), monitoring three currency pairs
with technical indicators and an automatic route comparator.

**Monitored pairs:** USD-BRL · UYU-USD · UYU-BRL

---

## Quick start (local development)

```bash
uv sync
uv run manage.py migrate
uv run manage.py fetch_rates
uv run manage.py runserver
```

Open **http://localhost:8000**.

---

## Production deployment

A single Docker container runs gunicorn and django-crontab (built-in scheduler).
Caddy is installed on the host as a reverse proxy with automatic HTTPS.

```bash
git clone <repo> /opt/rates-monitor
cd /opt/rates-monitor
bash deploy/deploy.sh --setup
```

The cron scheduler updates rates **every hour** without manual intervention.
A ready-to-use Caddyfile template is provided at `deploy/Caddyfile`.

→ Full guide: [docs/deployment.md](docs/deployment.md)

---

## Documentation

| Document | Contents |
|---|---|
| [overview.md](overview.md) | Project overview, architecture, and current status |
| [docs/user-guide.md](docs/user-guide.md) | App usage, signals, configuration |
| [docs/programming-guide.md](docs/programming-guide.md) | Code structure, patterns, extension points |
| [docs/deployment.md](docs/deployment.md) | Docker Compose, VPS, SSL, cron, backups |

---

## Environment variables

Copy `.env.example` to `.env` and adjust the values:

```env
SECRET_KEY=…          # Django secret key (required in production)
DEBUG=False
CORS_ALLOWED_ORIGINS_EXTRA=…       # server domain or IP
CSRF_TRUSTED_ORIGINS_EXTRA=…       # server domain or IP
ACCESS_PASSCODE=…     # access passcode (empty = no protection)
DATA_DIR=             # database directory (Docker sets this automatically)
```

---

## Stack

Python 3.14 · Django 6 · Gunicorn · django-crontab · Caddy · HTMX · Tailwind CSS · Chart.js · SQLite · Docker

## Screenshots

### Login (only if you define an ACCESS_PASSCODE on env)

![Login](docs/screenshots/login.png)

### Dashboard

![Dashboard with current status for each pair](docs/screenshots/dashboard.png)

### Pair details

![Pair panel with details](docs/screenshots/uyu_brl_details.png)
