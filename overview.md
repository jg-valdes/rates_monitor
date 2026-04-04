# Exchange Rate Monitor — Project Overview

## Goal

Personal tool to find the best route for converting Uruguayan Pesos (UYU)
to Brazilian Reais (BRL), with or without passing through Dollars (USD) as an
intermediate step.

The system monitors 3 currency pairs individually (technical signals per pair) and
calculates in real time which route yields more BRL per Uruguayan peso.

**Possible routes:**

| Route     | Path            | Pairs used               |
|-----------|-----------------|--------------------------|
| Direct    | UYU → BRL       | UYU-BRL                  |
| Indirect  | UYU → USD → BRL | UYU-USD + USD-BRL        |

**Monitored pairs:**

| Pair    | Meaning                              | Role in the decision    |
|---------|--------------------------------------|-------------------------|
| USD-BRL | How many reais per 1 dollar          | Indirect route (step 2) |
| UYU-USD | How many dollars per 1 Uruguayan peso | Indirect route (step 1) |
| UYU-BRL | How many reais per 1 Uruguayan peso  | Direct route            |

**Data source:** [AwesomeAPI](https://economia.awesomeapi.com.br) — public endpoint by default; set `AWESOMEAPI_KEY` for higher rate limits
**UI language:** Spanish (Spain/Cuba)
**Database:** SQLite

---

## Current Status — Implemented

### Tech stack

- **Backend:** Python 3.14 + Django 6
- **Frontend:** Django Templates + HTMX 2.0 + Tailwind CSS (CDN)
- **Charts:** Chart.js 4.4
- **Package manager:** uv

### Project structure

```
rates_monitor/
├── config/
│   ├── settings.py          # ACCESS_PASSCODE, middleware, context processor
│   ├── urls.py
│   └── wsgi.py
├── rates/
│   ├── models.py            # CurrencyPair, ExchangeRate, PairConfig
│   ├── views.py             # login, logout, overview, dashboard, stats, refresh, config
│   ├── urls.py              # routes with lowercase slugs
│   ├── admin.py             # CurrencyPair, ExchangeRate, PairConfig
│   ├── middleware.py        # PasscodeMiddleware
│   ├── context_processors.py # injects all_pairs into every template
│   ├── translations.py      # Spanish labels for internal English constants
│   ├── templatetags/
│   │   └── rates_extras.py  # filters: signal_label, confidence_label, momentum_label
│   ├── services/
│   │   ├── fetcher.py       # fetch_and_store(pair, days)
│   │   ├── indicators.py    # MA, deviation, momentum, volatility
│   │   ├── decision.py      # signal, confidence, capital allocation
│   │   ├── cross_pair.py    # UYU→BRL route comparator
│   │   └── alerts.py        # webhook notifications
│   ├── management/commands/
│   │   └── fetch_rates.py   # CLI command to fetch rates
│   ├── migrations/
│   │   ├── 0001_initial.py
│   │   ├── 0002_currency_pair_pair_config.py  # schema
│   │   ├── 0003_seed_pairs.py                 # seed data
│   │   └── 0004_finalize_exchange_rate.py     # constraints + removes UserConfig
│   └── templates/rates/
│       ├── login.html
│       ├── overview.html
│       ├── dashboard.html
│       └── partials/
│           ├── stats.html
│           └── config_form.html
└── templates/
    └── base.html            # nav with pair tabs + logout button
```

### Models

**`CurrencyPair`**
- `code` — e.g. `"USD-BRL"` (unique)
- `name` — e.g. `"Dólar / Real"`
- `api_code` — code used in the AwesomeAPI URL
- `active` — enabled/disabled
- `slug` (property) — `code.lower()`, used in URLs

**`ExchangeRate`**
- `pair` → FK to `CurrencyPair`
- `date`, `rate`, `high`, `low`, `created_at`
- Unique constraint: `(pair, date)`

**`PairConfig`** (OneToOne with CurrencyPair)
- `monthly_budget`, `threshold_strong_buy`, `threshold_moderate_buy`, `threshold_do_not_buy`
- `alert_webhook_url`, `alert_on_strong_buy`, `alert_on_deviation_above`, `alert_on_rate_above`

### URLs

| Method | URL                        | View             |
|--------|----------------------------|------------------|
| GET    | `/`                        | overview         |
| GET    | `/login/`                  | login_view       |
| POST   | `/login/`                  | login_view       |
| GET    | `/logout/`                 | logout_view      |
| GET    | `/overview/`               | overview         |
| GET    | `/<pair_code>/`            | dashboard        |
| GET    | `/<pair_code>/stats/`      | stats_partial    |
| POST   | `/<pair_code>/refresh/`    | refresh_data     |
| POST   | `/<pair_code>/config/`     | update_config    |

### Indicators engine (per pair)

- **MA 30 / MA 90** — simple moving average
- **Deviation** — `(rate - MA90) / MA90 * 100`
- **Momentum** — trend of the last 3 values (`up` / `down` / `neutral`)
- **Volatility** — mean absolute daily change over the last 14 days

### Decision engine (per pair)

| Deviation         | Signal          | Allocation |
|-------------------|-----------------|------------|
| > +3%             | STRONG BUY      | 150%       |
| > +1.5%           | MODERATE BUY    | 100%       |
| between -1% and +1.5% | NEUTRAL    | 50%        |
| < -1%             | DO NOT BUY      | 20%        |

Confidence adjusted by momentum: `STRONG BUY + up = HIGH`, etc.

### Route comparator (cross_pair.py)

```
direct_rate   = UYU-BRL rate             (BRL per 1 UYU)
indirect_rate = UYU-USD rate × USD-BRL   (BRL per 1 UYU via USD)
best_route    = whichever yields more BRL per peso
```

Shown on `/overview/` with percentage advantage.

### Security

- `ACCESS_PASSCODE` in `.env` activates protection (empty = disabled in dev)
- `PasscodeMiddleware` blocks all routes except `/login/` and `/logout/`
- Comparison with `hmac.compare_digest` (constant-time)
- Signed token with `signing.dumps()` stored in `rm_access` cookie
  (`httponly`, `samesite=Lax`, `secure` in production, 24h expiry)

### Alerts

Configurable webhook per pair. Fires when:
- STRONG BUY signal is active (if enabled)
- Deviation exceeds configured threshold
- Rate exceeds configured threshold

Payload includes: pair, signal, rate, deviation, confidence, suggested amount.

### CLI command

```bash
# Fetch all active pairs (90 days by default)
uv run manage.py fetch_rates

# Specific pair, last 3 days, no alerts
uv run manage.py fetch_rates --pair usd-brl --days 3 --no-alerts
```

Prints indicators per pair and the route comparator at the end.

---

## Running locally

```bash
# Install dependencies
uv sync

# Apply migrations (includes the 3 pairs and migrated data)
uv run manage.py migrate

# Seed initial rates
uv run manage.py fetch_rates

# Start server
uv run manage.py runserver
```

Open `http://localhost:8000` — redirects to `/overview/`.

To enable the passcode:
```bash
export ACCESS_PASSCODE=your-secret
```

---

### Purchase tracking

`Purchase` model to record actual conversions executed by the user.

**Fields:** `pair`, `date`, `amount_spent` (base currency), `amount_received` (quote currency), `note`, `created_at`
**Computed property:** `effective_rate = amount_received / amount_spent`

Per pair the dashboard shows:
- Total spent / total received / weighted average rate / trade count
- Individual purchases table with delete button (HTMX)
- Inline form to record new purchases

On `/overview/`: consolidated table of capital deployed across all three pairs.

Currencies are derived automatically from the pair code (`USD-BRL` → spends `USD`, receives `BRL`).

---

### Deployment (Docker Compose)

| Component      | Where it runs          | Role |
|----------------|------------------------|------|
| `web` (Docker) | single container       | Django + Gunicorn + django-crontab + system cron |
| Caddy (host)   | VPS operating system   | Reverse proxy + automatic TLS (Let's Encrypt) |

A single container runs gunicorn and the system `cron` daemon. Scheduled tasks
are registered via `django-crontab` on container startup.
Caddy is installed directly on the host and proxies to `localhost:8003`.

**Initial VPS deployment:**
```bash
git clone <repo> /opt/rates-monitor
cd /opt/rates-monitor
bash deploy/deploy.sh --setup
```

**Update:**
```bash
git pull && bash deploy/deploy.sh
```

The `cron` service updates rates every hour without manual intervention
(full 90-day backfill at 02:00 UTC daily).

→ Full guide: [docs/deployment.md](docs/deployment.md)

---

## Pending / Next steps

- Migrate database to PostgreSQL in production (optional; see docs/deployment.md)
