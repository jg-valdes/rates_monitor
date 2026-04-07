# Programming Guide — Exchange Rate Monitor

Conventions, design patterns, and guide for extending the project.

---

## Project structure

```
rates_monitor/
├── config/                        # Django configuration (settings, urls, wsgi)
├── rates/                         # Single Django app
│   ├── migrations/                # 0001–0005 (schema + data + Purchase)
│   ├── services/                  # Pure business logic (no Django)
│   │   ├── fetcher.py             # AwesomeAPI data fetching per pair
│   │   ├── oer_fetcher.py         # Open Exchange Rates fetcher (cross-rate math)
│   │   ├── indicators.py          # Technical indicator computation
│   │   ├── decision.py            # Signal engine and capital allocation
│   │   ├── cross_pair.py          # UYU → BRL route comparator
│   │   └── alerts.py              # Webhook notifications
│   ├── templatetags/
│   │   └── rates_extras.py        # Custom template filters
│   ├── management/commands/
│   │   └── fetch_rates.py         # CLI command for cron (all pairs)
│   ├── templates/rates/
│   │   ├── login.html             # Access passcode form (standalone)
│   │   ├── overview.html          # Summary page (route comparator + capital)
│   │   ├── dashboard.html         # Per-pair dashboard
│   │   └── partials/              # HTMX fragments
│   │       ├── stats.html         # Indicator/signal cards (auto-refresh)
│   │       ├── config_form.html   # Per-pair configuration
│   │       └── purchases.html     # Deployed capital (HTMX add/delete)
│   ├── models.py                  # CurrencyPair, ExchangeRate, Purchase, PairConfig
│   ├── views.py                   # All views + helpers
│   ├── urls.py                    # Routes with lowercase slugs
│   ├── middleware.py              # PasscodeMiddleware
│   ├── context_processors.py     # Injects all_pairs into every template
│   ├── translations.py            # Internal constants → Spanish label mapping
│   └── admin.py
├── templates/
│   └── base.html                  # Global layout (nav with pair tabs, logout)
└── docs/
```

---

## Design principles

### 1. Separation of logic and framework

All business logic lives in `rates/services/`. Those modules are **pure Python
functions**: they do not import Django, do not make queries, do not use `request`.
This makes them easy to test and reuse from any context (views, management
commands, scripts).

```python
# Correct — pure function, testable in isolation
def compute_deviation(rate: float, ma90: float) -> float:
    return round((rate - ma90) / ma90 * 100, 4)

# Wrong — mixes logic with data access
def compute_deviation_from_db():
    rate = ExchangeRate.objects.last().rate  # unnecessary coupling
    ...
```

### 2. Views are orchestrators

Views in `rates/views.py` do one thing: fetch data from the ORM, call services,
and build the template context. They contain no business logic.

```python
def dashboard(request, pair_code):
    pair       = get_object_or_404(CurrencyPair, code=pair_code.upper(), active=True)
    rates_list = list(ExchangeRate.objects.filter(pair=pair).order_by("date"))
    config     = _get_or_create_config(pair)
    indicators = compute_all(rates_list)          # service
    decision   = build_decision(indicators, config) # service
    return render(request, "rates/dashboard.html", {...})
```

### 3. Domain constants are always in English

Values stored in the database and used in Python comparisons (`STRONG BUY`,
`HIGH`, `up`) are always kept in English. Spanish translations are for display
only, centralised in `rates/translations.py`.

**Why:** mixing presentation language with domain language would require a
database migration just to rename a signal.

### 4. Currency pairs are managed entities

No pair code is hardcoded in the business logic. All functions receive a
`CurrencyPair` object or a pre-filtered list of rates. Adding a new pair only
requires inserting a row into the `CurrencyPair` table (and its `PairConfig`) —
the rest of the system detects it automatically.

---

## Models

### `CurrencyPair`

Central entity. Holds the code (`USD-BRL`), a human-readable name, the
AwesomeAPI code, and active status.

**Computed properties** (no database columns):
- `slug` → `code.lower()`, used in URLs
- `base_currency` → left part of the code (`USD` in `USD-BRL`)
- `quote_currency` → right part of the code (`BRL` in `USD-BRL`)

### `ExchangeRate`

One record per day per pair. Unique constraint `(pair, date)`. Fields `high`
and `low` are optional.

### `PairConfig`

`OneToOne` relation with `CurrencyPair`. Stores decision thresholds, monthly
budget, and alert configuration per pair. Created automatically with defaults if
missing (`_get_or_create_config(pair)`).

### `Purchase`

Records actual conversions executed by the user. Fields: `pair`, `date`,
`amount_spent` (base currency), `amount_received` (quote currency), `note`.
The effective rate (`effective_rate`) is a computed property:
`amount_received / amount_spent`.

---

## Service layer

### `services/fetcher.py`

```python
def fetch_and_store(pair: CurrencyPair, days: int = 90) -> tuple[int, int]:
```

- Uses [AwesomeAPI](https://economia.awesomeapi.com.br) — free, no API key required.
- Calls `GET /json/daily/{pair.api_code}/{days}` once per pair, returning up to
  `days` records newest-first. One HTTP request covers the whole date range.
- `bid`, `high`, and `low` are stored directly from the response (no cross-rate math).
- Uses `update_or_create(pair=pair, date=rate_date, ...)` so re-runs are idempotent.
- Retries up to 3 times with exponential backoff (2 s → 4 s) on HTTP 429.
- Callers should add a delay between pairs to avoid rate limiting (the management
  command waits 1 s between pairs; single-pair view refreshes are safe as-is).
- Active when `EXCHANGE_RATE_SOURCE=awesomeapi` (the default).

### `services/oer_fetcher.py`

```python
def fetch_and_store(days: int = 90) -> tuple[int, int]:
```

- Uses [Open Exchange Rates](https://openexchangerates.org). Requires
  `OPENEXCHANGERATES_APP_ID` in settings.
- OER uses USD as the fixed base, so all three pairs are derived from a
  **single API call** that returns `BRL` and `UYU` rates relative to USD:

  ```
  USD-BRL  = rates["BRL"]                  (direct)
  UYU-USD  = 1 / rates["UYU"]             (inverted)
  UYU-BRL  = rates["BRL"] / rates["UYU"]  (cross via USD)
  ```

- `days == 1` → fetches `/api/latest.json` (always available, free tier).
- `days > 1` → iterates business days calling `/api/historical/YYYY-MM-DD.json`.
  On HTTP 403 (free-plan restriction) the loop aborts and falls back to
  latest-only automatically.
- `high` / `low` are stored as `None` (OER free tier does not provide intraday range).
- Active when `EXCHANGE_RATE_SOURCE=openexchangerates`.

**Switching sources:** set `EXCHANGE_RATE_SOURCE` in `.env`. The management
command and `refresh_data` view both read this setting and dispatch accordingly.
No other code changes are required.

### `services/indicators.py`

Pure functions that receive lists of floats and return floats:

```python
def compute_ma(values: list[float], window: int) -> float | None: ...
def compute_deviation(rate: float, ma90: float) -> float: ...
def compute_momentum(values: list[float]) -> str: ...   # "up" | "down" | "neutral"
def compute_volatility(values: list[float], window: int = 14) -> float: ...
def compute_all(rates_list) -> dict | None: ...         # orchestrator
def compute_rolling_ma(values: list[float], window: int) -> list[float | None]: ...
```

`compute_rolling_ma` returns `None` for the first `window-1` points so that
Chart.js leaves that portion of the line blank.

### `services/decision.py`

```python
def build_decision(indicators: dict, config: PairConfig) -> dict:
    # Returns: signal, confidence, suggested_amount, allocation_pct, color
```

The signal constants (`STRONG_BUY`, etc.) must never change — they are stored
in the database and compared in code.

### `services/cross_pair.py`

Compares the two possible routes for converting UYU → BRL:

```python
def compute_cross_pair() -> dict | None:
    # direct_rate   = UYU-BRL rate
    # indirect_rate = UYU-USD rate × USD-BRL rate
    # Returns None if any pair has no data yet
```

Returns `None` with graceful degradation when data is missing for any of the
three pairs.

### `services/alerts.py`

```python
def check_and_send(indicators, decision, config, pair_name: str = "") -> list[str]:
def send_test_alert(indicators, decision, config, pair_name: str) -> bool:
```

- Sends via the Telegram Bot API (`sendMessage`) using `TELEGRAM_BOT_TOKEN` and
  `TELEGRAM_CHAT_ID` from settings. Both must be set; if either is empty, sending
  is skipped silently (returns `False`).
- `check_and_send` — evaluates three conditions (strong-buy signal, deviation
  threshold, rate threshold) and calls `_send_telegram` for each triggered one.
  Network errors are logged but never re-raised, so they cannot interrupt the
  cron flow.
- `send_test_alert` — sends the same message format as production alerts using
  live indicator data. Called by the per-pair **Enviar Alerta** button and the
  global **📤 Enviar** nav button (`send_all_alerts` view).
- `_build_message` — shared helper that formats the Telegram Markdown message.
  Includes: signal emoji, pair name, Spanish signal label, current rate, deviation
  vs MA90, MA30, MA90, momentum emoji + label, confidence, and suggested allocation.

**Emoji maps** (internal constant → display character):

| Dict | Keys | Values |
|---|---|---|
| `_SIGNAL_EMOJI` | `STRONG BUY`, `MODERATE BUY`, `NEUTRAL`, `DO NOT BUY` | 🚀 📈 📊 🛑 |
| `_CONFIDENCE_EMOJI` | `HIGH`, `MEDIUM`, `LOW` | 🟢 🟡 🔴 |
| `_MOMENTUM_EMOJI` | `up`, `down`, `neutral` | ↗️ ↘️ ➡️ |

---

## Security — PasscodeMiddleware

`rates/middleware.py` intercepts all requests. If `settings.ACCESS_PASSCODE` is
set:

1. Exempt paths: `/login/`, `/logout/`, `/admin/` — pass through without check.
2. Validates the `rm_access` cookie with `django.core.signing.loads(max_age=86400)`.
3. If the cookie is missing or expired → redirects to `/login/?next=<path>`.

The passcode comparison in `login_view` uses `hmac.compare_digest` (constant-time,
safe against timing attacks). The signed token uses Django's `SECRET_KEY` — no
additional database table is needed.

```python
# settings.py
ACCESS_PASSCODE = config("ACCESS_PASSCODE", default="")
# Empty → middleware disabled (development convenience)
```

---

## Templates and HTMX

### Structure

```
templates/base.html                    ← global layout (pair tabs, logout)
rates/templates/rates/
  login.html                           ← standalone (does not extend base.html)
  overview.html                        ← extends base.html
  dashboard.html                       ← extends base.html
  partials/
    stats.html                         ← HTMX polling every 300s
    config_form.html                   ← HTMX POST per pair
    purchases.html                     ← HTMX add/delete purchases
```

### Auto-refresh pattern (polling)

The `div#stats-section` in `stats.html` auto-refreshes with `hx-trigger="every 300s"`.
For polling to continue after an `outerHTML` swap, the returned partial **must
include the same HTMX attributes** on its root element — including the correct
pair URL:

```html
<div id="stats-section"
     hx-get="{% url 'rates:stats_partial' pair.slug %}"
     hx-trigger="every 300s"
     hx-swap="outerHTML">
```

### URL namespacing

All URL names are scoped under the `rates` namespace (`app_name = "rates"` in
`rates/urls.py`). Always use the namespaced form in templates and `reverse()` calls:

```html
{% url 'rates:dashboard' pair.slug %}
{% url 'rates:overview' %}
{% url 'rates:update_config' pair.slug %}
```

```python
from django.urls import reverse
reverse("rates:dashboard", kwargs={"pair_code": "usd-brl"})
```

### Pair-scoped parameterised URLs

All partial URLs use `pair.slug` (lowercase). The pair is always available in
context because:
- Dashboard views pass it explicitly.
- The `active_pairs` context processor injects `all_pairs` into all templates
  for the nav.

### CSRF with HTMX

The token is injected globally in `base.html`:

```html
<meta name="htmx-config" content='{"defaultHeaders":{"X-CSRFToken":"{{ csrf_token }}"}}'>
```

`login.html` is standalone (does not extend `base.html`) and uses
`{% csrf_token %}` directly in the form.

### Template filters

```html
{% load rates_extras %}
{{ decision.signal|signal_label }}        {# "COMPRA FUERTE" #}
{{ decision.confidence|confidence_label }} {# "ALTA" #}
{{ indicators.momentum|momentum_label }}   {# "al alza ↑" #}
```

---

## Code conventions

### Naming

- **Functions:** `snake_case`, verb + noun (`compute_all`, `fetch_and_store`, `build_decision`)
- **Domain constants:** `UPPER_SNAKE_CASE` (`STRONG_BUY`, `DO_NOT_BUY`)
- **Templates:** `snake_case.html`, partials in `partials/` subdirectory
- **URL slugs:** always lowercase (`usd-brl`, `uyu-brl`)

### Type hints

All service functions use type hints with `|` for unions (Python 3.10+):

```python
def compute_ma(values: list[float], window: int) -> float | None: ...
def compute_cross_pair() -> dict | None: ...
```

### Logging

Use the module-level logger, never `print()`:

```python
logger = logging.getLogger(__name__)
logger.info("Fetching 90 days of USD-BRL")
logger.warning("Alert triggered")
logger.error("Error sending Telegram alert for %s: %s", pair_name, exc)
```

---

## How to add a new currency pair

1. Insert into the database (or create a data migration):
   ```python
   pair = CurrencyPair.objects.create(
       code="EUR-BRL", name="Euro / Real", api_code="EUR-BRL", active=True
   )
   PairConfig.objects.create(pair=pair)
   ```

2. Seed historical data:
   ```bash
   uv run manage.py fetch_rates --pair eur-brl --days 90
   ```

3. The pair appears automatically in the navigation, in the overview, and in the
   route comparator if `cross_pair.py` is updated to include it.

## How to add a new signal

1. Add the constant in `services/decision.py`:
   ```python
   EXTREME_BUY = "EXTREME BUY"
   ```
2. Update `SIGNAL_MULTIPLIERS` and `SIGNAL_CSS`.
3. Update `get_signal()` with the new condition.
4. Add the translation in `rates/translations.py`.
5. Update the `{% if %}` blocks in the templates.

## How to add a new indicator

1. Write a pure function in `services/indicators.py`.
2. Add the result to the `compute_all()` dict.
3. Use it in `build_decision()` if it affects the signal.
4. Display it in `partials/stats.html`.

---

## Code quality

[ruff](https://docs.astral.sh/ruff/) is used for formatting and linting. It is
a dev-only dependency (not installed in Docker production builds).

```bash
# Format all Python files
uv run ruff format .

# Lint (and auto-fix what can be fixed)
uv run ruff check --fix .
```

Configuration lives in `pyproject.toml` under `[tool.ruff]`. The selected rules
are `E` (pycodestyle errors), `F` (pyflakes), and `I` (isort import order).

---

## Testing

Services are pure functions → testable without a database or HTTP:

```python
from rates.services.indicators import compute_deviation, compute_momentum
from rates.services.cross_pair import compute_cross_pair

def test_positive_deviation():
    assert compute_deviation(5.80, 5.50) == pytest.approx(5.45, rel=1e-2)

def test_upward_momentum():
    assert compute_momentum([5.0, 5.1, 5.2]) == "up"
```

To test views with queries, use `@pytest.mark.django_db` with pytest-django fixtures.

---

## Environment variables

All variables are read by [python-decouple](https://github.com/HBNetwork/python-decouple),
which looks for them in `.env`, then in the OS environment. No `os.environ` calls remain
in `settings.py`.

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | *(dev value)* | Django secret key. Change in production. |
| `DEBUG` | `True` | Set to `False` for production. |
| `ALLOWED_HOSTS` | *(empty)* | Comma-separated domains/IPs. Required when `DEBUG=False`. In dev (`DEBUG=True`) all hosts are allowed automatically. |
| `CSRF_TRUSTED_ORIGINS_EXTRA` | *(empty)* | Comma-separated origins for CSRF validation in production (e.g. `https://yourdomain.com`). |
| `ACCESS_PASSCODE` | *(empty)* | Site access passcode. Empty = no protection. |
| `TELEGRAM_BOT_TOKEN` | *(empty)* | Telegram bot token from @BotFather. Both Telegram vars must be set for alerts to send. |
| `TELEGRAM_CHAT_ID` | *(empty)* | Target Telegram chat/group/channel ID. |
| `EXCHANGE_RATE_SOURCE` | `awesomeapi` | Rate data source: `awesomeapi` or `openexchangerates`. |
| `OPENEXCHANGERATES_APP_ID` | *(empty)* | Required when `EXCHANGE_RATE_SOURCE=openexchangerates`. Get a free key at openexchangerates.org. |
| `DATA_DIR` | *(project root)* | Directory for `db.sqlite3`. Docker Compose sets this to `/app/data`. |

When `DEBUG=False`, Django automatically sets `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`
(1 year), `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, and `SECURE_CONTENT_TYPE_NOSNIFF`.
These do not need env vars.

Example `.env` for production:

```env
SECRET_KEY=your-long-random-secret-key
DEBUG=False
ALLOWED_HOSTS=yourdomain.com
CSRF_TRUSTED_ORIGINS_EXTRA=yourdomain.com
ACCESS_PASSCODE=your-secret-code
# Optional: switch to Open Exchange Rates
# EXCHANGE_RATE_SOURCE=openexchangerates
# OPENEXCHANGERATES_APP_ID=your-oer-app-id
```
