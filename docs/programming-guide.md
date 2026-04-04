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
│   │   ├── fetcher.py             # API data fetching per pair
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

- Uses the [Open Exchange Rates](https://openexchangeapi.com) API via the
  vendored `rates/services/openexchangeapi.py` SDK.
- Authenticates with `OPEN_EXCHANGE_RATES_APP_ID` from the environment.
- Calls `GET /v1/historical/{date}` once per calendar day in the requested
  range. All currency rates are USD-based, so the pair rate is computed as:
  `rates[quote_currency] / rates[base_currency]`.
- API responses are cached per date within the same process run — fetching
  multiple pairs together only makes one HTTP call per unique date.
- `high` and `low` are stored as `None` (the API does not provide intraday data).
- Uses `update_or_create(pair=pair, date=rate_date, ...)` to be idempotent.
- Raises exceptions — the caller decides what to do.

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
```

- Never raises exceptions: webhook errors are logged but do not interrupt the
  flow.
- Includes `pair_name` as a prefix in all messages.
- The webhook payload includes the `pair` field so the receiver can filter by
  pair.

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
ACCESS_PASSCODE = os.environ.get("ACCESS_PASSCODE", "")
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
     hx-get="{% url 'stats_partial' pair.slug %}"
     hx-trigger="every 300s"
     hx-swap="outerHTML">
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
logger.error("Error sending webhook")
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

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | *(dev value)* | Django secret key. Change in production. |
| `DEBUG` | `True` | Set to `False` for production. |
| `CSRF_TRUSTED_ORIGINS_EXTRA` | `*` | Comma-separated list of trusted hosts for CSRF validation. |
| `ACCESS_PASSCODE` | *(empty)* | Site access passcode. Empty = no protection. |
| `OPEN_EXCHANGE_RATES_APP_ID` | *(required)* | API key from [openexchangeapi.com](https://openexchangeapi.com). |

Example `.env` for production:

```env
SECRET_KEY=your-long-random-secret-key
DEBUG=False
CORS_ALLOWED_ORIGINS_EXTRA=yourdomain.com
CSRF_TRUSTED_ORIGINS_EXTRA=yourdomain.com
ACCESS_PASSCODE=your-secret-code
OPEN_EXCHANGE_RATES_APP_ID=your-api-key
```
