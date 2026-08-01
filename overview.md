# Exchange Rate Monitor — Project Overview

## Product purpose

Exchange Rate Monitor is a personal investment-control product focused on an
apartment purchase in Brazil. It combines currency timing, actual conversion
history, and CUB-SC-adjusted contractual obligations in one auditable workspace.

The current product answers three practical questions:

1. Is UYU → BRL better directly or through USD right now?
2. How much capital has actually been converted, and at what effective rate?
3. What apartment payments are due, how did CUB change them, and what remains?

The interface is Spanish-first. Contract amounts and CUB values are stored in
BRL. SQLite is the deliberate database choice for the current single-owner
deployment; PostgreSQL is a scale trigger, not unfinished work.

## Current development stage

The product is feature-complete for personal use and is in the stabilization
stage. The priority is reliable operation, provenance, backups, automated
quality gates, and a clean boundary for later multi-tenant evolution.

Delivered capabilities include:

- monitoring USD-BRL, UYU-USD, and UYU-BRL;
- direct-versus-indirect UYU → BRL route comparison;
- MA30/MA90, deviation, momentum, volatility, signal, and allocation guidance;
- AwesomeAPI and optional Open Exchange Rates data sources;
- local OER quota accounting, cooldowns, and weekend rate mirroring;
- Telegram alerts and twice-daily weekday snapshots;
- actual FX purchase history with weighted effective rates;
- property plans with entry terms, monthly installments, yearly reinforcements,
  and keys payments;
- exact and provisional CUB-SC adjustment calculations;
- partial payments, voided corrections, final overrides, and protected history;
- visible source URLs for every current and stored CUB value;
- responsive Django/HTMX dashboards and Django admin.

## Architecture

```text
Caddy (host, TLS)
        |
        v
Docker Compose
  web container
    Gunicorn worker -> Django/HTMX
    APScheduler thread -> rate refresh + Telegram jobs
            |
       SQLite volume
```

The container entrypoint runs migrations with scheduling disabled, then exports
`RUN_SCHEDULER=1` immediately before starting one Gunicorn worker. This keeps
tests and management commands inert while retaining the low memory footprint of
one application container. More Gunicorn workers must not be enabled until the
scheduler is externalized or given distributed locking.

### Main modules

```text
config/                         Django settings and URL configuration
rates/
  models.py                     FX, quota, purchase, CUB, and payment records
  views.py                      Exchange-rate and purchase workflows
  payment_views.py              Property plan and payment workflows
  services/
    fetcher.py                  AwesomeAPI integration
    oer_fetcher.py              Open Exchange Rates integration
    oer_quota.py                Local quota policy
    market_calendar.py          Weekend mirroring
    indicators.py               Technical indicators
    decision.py                 Signal and allocation engine
    cross_pair.py               Route comparison
    alerts.py                   Telegram delivery
    cub_fetcher.py              Assisted CUB source extraction
    payment_calculations.py     Contract schedule and adjustment calculations
  management/commands/
    fetch_rates.py              Manual/scheduled data refresh
    run_scheduler.py            Optional standalone scheduler for local testing
tests/                          Django, service, UI, and regression tests
deploy/                         Container entrypoint, deployment helper, Caddy
```

## Data and audit model

- `CurrencyPair`, `ExchangeRate`, and `PairConfig` hold rate data and strategy.
- `SourceQuotaUsage` tracks local OER consumption.
- `Purchase` records executed currency conversions.
- `PropertyPurchasePlan` owns a housing contract.
- `PaymentSeries` defines recurring contractual groups.
- `PaymentObligation` stores individual due dates and locked calculations.
- `PaymentTransaction` is append-oriented; corrections are voided, not deleted.
- `CubIndexValue` stores the applicable month, value, variation, verification
  timestamp, and source URL.

CUB previews never write automatically. A user must confirm a detected value.
The Vivienda UI links directly to the configured source and to each stored
record's source so the extracted value can be independently checked.

## Runtime schedule

All schedules use UTC:

| Job | Schedule | Purpose |
|---|---|---|
| Morning snapshot | Monday-Friday 07:00 | Refresh recent rates and notify Telegram |
| Midday snapshot | Monday-Friday 12:30 | Refresh recent rates and notify Telegram |
| Safety backfill | Daily 02:00 | Refresh history or mirror locally under OER policy |

## Quality baseline

The supported verification gate is:

```bash
uv run ruff check .
uv run ruff format --check .
uv run manage.py check
uv run manage.py makemigrations --check --dry-run
uv run pytest --cov-fail-under=95
docker compose config -q
```

GitHub Actions runs the same checks for pushes and pull requests targeting
`develop` or `main`. Pytest enforces a 95% project coverage floor to prevent
silent regression while allowing pragmatic room for framework glue.

## Product direction

The current product remains intentionally single-owner and SQLite-backed. The
next phases are documented in [docs/product-roadmap.md](docs/product-roadmap.md).
Multi-tenancy, organization roles, PostgreSQL, billing, and builder/real-estate
workflows should be introduced together only after concrete demand justifies
the operational complexity.
