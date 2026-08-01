# User Guide — Exchange Rate Monitor

This app helps you find the best timing and route for converting Uruguayan Pesos
(UYU) to Brazilian Reais (BRL), by monitoring three currency pairs with simple
technical indicators.

---

## Installation and first use

### Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) installed

### Steps

```bash
# 1. Go to the project directory
cd rates_monitor

# 2. Install dependencies
uv sync

# 3. Create the database (includes the three pairs automatically)
uv run manage.py migrate

# 4. Fetch the last 90 days of rates for all pairs
uv run manage.py fetch_rates

# 5. Start the server
uv run manage.py runserver
```

Open your browser at **http://localhost:8000**.

### Access passcode (production)

If the site is on a publicly accessible server, set the `ACCESS_PASSCODE`
environment variable before starting:

```bash
export ACCESS_PASSCODE=your-secret-code
uv run manage.py runserver
```

With the passcode configured, the first time you visit the site you will see an
access form. The session lasts 24 hours.

---

## Navigation

The top bar shows four sections:

| Tab | Contents |
|---|---|
| **Resumen** | Route comparator + status of all three pairs + deployed capital |
| **Vivienda** | Property contract, CUB adjustment, schedule, and payment progress |
| **USD-BRL** | Dollar / Real pair dashboard |
| **UYU-USD** | Uruguayan Peso / Dollar pair dashboard |
| **UYU-BRL** | Uruguayan Peso / Real pair dashboard |

The right side of the nav bar has four controls:

- **↻ Actualizar** (dashboard pages only) — fetches the latest rate from the API
  and refreshes the indicator cards.
- **⚙ Cuota OER** (all pages) — manually checks the current Open Exchange Rates
  quota status and shows plan, usage, remaining requests, and the app's local
  safety guard.
- **📤 Enviar** (all pages) — sends a Telegram message with the current status
  for every active pair. Shows ✓ / ⚠ / ✕ feedback inline.
- **Salir** — ends the session (only shown when `ACCESS_PASSCODE` is set).

---

## Vivienda and property payments

The **Vivienda** section keeps the house contract separate from currency
conversions. On first use, enter the contract date and base CUB, then configure:

- an optional entry payment split into one or more independently tracked terms,
- monthly installments with their first due date, quantity, and base amount,
- optional yearly reinforcements,
- an optional keys-payment milestone,
- whether CUB applies independently to each payment series.

Review the generated calendar before creating the plan. Monthly dates preserve
the selected day when possible and use the last valid day for shorter months.

Use **Editar plan** to change the contract, CUB base, installment count,
amounts, entry terms, reinforcements, or keys payment. Saving regenerates only obligations
without payment history. Paid or explicitly closed obligations preserve their
date, base amount, CUB snapshot, and adjusted amount; correct those rows
individually from **Editar cuota protegida manualmente**.

### How the CUB calculation works

For obligations adjusted by CUB, the expected amount is:

```
base amount × CUB applicable to the due month ÷ contract base CUB
```

The result is rounded to BRL cents. When the exact future month is not stored,
the page uses the latest verified CUB only as a **provisional** forecast. Add a
value manually or use **Consultar fuente** to preview values from Sinduscon BC;
assisted values are saved only after confirmation. The card always displays the
exact source URL used for the current value, and every stored value in
**Gestionar valores CUB** has its own **Ver fuente** link for manual comparison.
The assisted review selects all detected months by default so they can be
confirmed in one request. Existing months show the saved and proposed values,
monthly variations, and the absolute and percentage difference. Uncheck any
proposal you want to decline, or discard the complete review without saving.
Confirming a new or corrected CUB never recalculates an obligation that already
has an active payment or was explicitly closed. Historical obligations can only
be changed through their manual editor.

### Recording payments

Open the action menu on any obligation to register one or more partial payments.
The page shows expected, paid, balance, and variance amounts. A payment entered
by mistake can be voided: it remains visible in history but stops contributing
to totals. Use **Cerrar como pagado** when the builder's final invoiced amount
differs from the calculated value.

The next-payment card also displays an approximate USD requirement based on the
latest stored USD-BRL rate. This estimate never changes the BRL contract or
creates a currency purchase automatically.

---

## Overview page

### Route Comparator — UYU → BRL

Shows which of the two possible routes yields more reais per Uruguayan peso right
now:

- **Direct route:** convert UYU to BRL directly (using the UYU-BRL pair)
- **Indirect route:** convert UYU to USD then USD to BRL (using UYU-USD × USD-BRL)

The system calculates both rates and highlights the best one with the percentage
advantage. If data is missing for any pair, the comparator is not shown until all
three pairs have been seeded.

### Pair Status

Three cards with the current status of each pair: rate, today's signal, and
deviation from the 90-day moving average. Click any card to go to that pair's
full dashboard.

### Capital Deployed by Pair

Table showing, for each pair, the total base currency spent, total received, and
the effective average rate across all recorded purchases.

---

## Per-pair dashboard

Each pair has its own page with the same structure:

### 1. Summary cards (top row)

| Card | What it shows |
|---|---|
| **Pair** | Current rate, moving averages, deviation, momentum, and volatility |
| **Today's Signal** | System recommendation with confidence level |
| **Suggested Allocation** | Amount to buy based on the pair's monthly budget |

This section **auto-refreshes every 5 minutes**. You can also force a refresh
with the **↻ Actualizar** button in the top bar.

When the source is **Open Exchange Rates**, manual refresh follows the quota
policy:

- weekends do not trigger remote API calls,
- Saturday and Sunday are mirrored locally from the latest Friday value so the
  chart stays continuous,
- repeated refreshes are throttled by a cooldown window,
- once the local monthly safety cap is reached, the app stops making OER
  requests until the next month.

### 2. Chart — Last 90 days

Actual rate in purple, MA 30 in yellow, and MA 90 in red. Hover over the chart
to see exact values for each date.

If the selected source does not publish weekend updates, the app can fill
Saturday and Sunday with synthetic rows copied from Friday's last known rate.
These mirrored rows are stored in the database so the 90-day chart remains
continuous without spending weekend API requests.

### 3. Configuration panel

Adjust the pair's parameters without touching code. See the
[Configuration](#configuration) section below.

### 4. Recent decisions

Table with the last 30 days: rate, calculated signal, confidence, and suggested
amount. Useful for seeing how signals evolved over time.

### 5. Capital deployed

Section for recording and reviewing conversions you have actually executed for
this pair:

- **Totals:** sum of base currency spent, sum of quote currency received, weighted
  average rate.
- **Purchases table:** list of all recorded trades with a delete button.
- **Entry form:** enter date, amount spent, amount received, and an optional note.

> Example for USD-BRL: enter how many USD you spent and how many BRL you received.
> The system calculates the effective rate and adds it to the totals.

---

## Signals

The system calculates how much the current rate deviates from its 90-day moving
average (MA90) and generates a signal:

| Signal | Condition | Suggested allocation |
|---|---|---|
| **COMPRA FUERTE** | Deviation > high threshold (default +3%) | 150% of monthly budget |
| **COMPRA MODERADA** | Deviation > moderate threshold (default +1.5%) | 100% of budget |
| **NEUTRAL** | Deviation between –1% and +1.5% | 50% of budget |
| **NO COMPRAR** | Deviation < –1% | 20% of budget |

> **Example:** If the monthly budget for USD-BRL is 1,000 USD and the signal is
> COMPRA FUERTE, the system suggests buying 1,500 USD that day.

### Confidence level

Combines the signal with the trend (last 3 rates):

- **ALTA** → COMPRA FUERTE + upward trend
- **MEDIA** → COMPRA FUERTE with downward trend, or COMPRA MODERADA with neutral/positive trend
- **BAJA** → weak signal or no trend confirmation

---

## Technical indicators

| Indicator | Description |
|---|---|
| **MA 30d** | Simple moving average of the last 30 days |
| **MA 90d** | Simple moving average of the last 90 days (main reference) |
| **Deviation** | `(current_rate − MA90) / MA90 × 100` — as a percentage |
| **Momentum** | "al alza" if the last 3 days are consecutively higher; "a la baja" if lower; "neutral" otherwise |
| **Volatility** | Average absolute daily change over the last 14 days |

---

## Configuration

The **Configuration** panel (right column on each dashboard) lets you adjust the
parameters for that specific pair. Each pair has its own independent configuration.

### Monthly budget

Typical monthly amount in the pair's base currency. The system multiplies this
by the signal factor to calculate the suggested amount.

### Decision thresholds

Deviation percentages that define the signal boundaries:

- **C. Fuerte >** (default 3.0): above this → COMPRA FUERTE
- **C. Mod. >** (default 1.5): above this → COMPRA MODERADA
- **No Comp. <** (default –1.0): below this → NO COMPRAR

The range between "No Comp." and "C. Mod." is the NEUTRAL zone.

### Alerts

Alerts are sent via Telegram using a single project-wide bot. Set
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in your `.env` file to enable them
(see the FAQ for setup instructions).

#### Automatic alerts (per pair)

Configure the conditions in each pair's configuration panel:

- **Alert on COMPRA FUERTE:** checkbox — fires whenever the strong-buy signal is active
- **Alert if deviation >:** fires when deviation vs MA90 exceeds that percentage
- **Alert if rate >:** fires when the current rate exceeds that value

These fire automatically when `fetch_rates` runs without `--no-alerts`.

#### Manual send

Two buttons let you send messages on demand without waiting for a trigger:

- **📤 Enviar** (nav bar, always visible) — sends one message per active pair in
  a single click, from any page. Inline feedback shows how many were sent.
- **Enviar Alerta** (per-pair config panel) — sends a message for that pair only.

#### Message format

Each Telegram message contains:

```
🚀 Dólar / Real — COMPRA FUERTE
━━━━━━━━━━━━━━━
💰 Cotización: 5.8900
📉 Desviación vs MA90: +3.50%
📊 MA30: 5.7200 · MA90: 5.6900
↗️ Tendencia: al alza ↑
🎯 Confianza: 🟢 ALTA
━━━━━━━━━━━━━━━
💵 Sugerido: $1500 (150% del presupuesto)
```

---

## Daily automation

The production container starts one guarded APScheduler thread inside its single
Gunicorn worker. It refreshes all pairs and sends the same Telegram snapshot as
the **📤 Enviar** button at 07:00 and 12:30 UTC, Monday through Friday. A 90-day
safety backfill runs every day at 02:00 UTC.

For local testing, run the scheduler in its own terminal:

```bash
uv run manage.py run_scheduler
```

Do not run the standalone command while the production container is running.
Production scheduling is enabled only after migrations through the private
`RUN_SCHEDULER` runtime flag.

### Open Exchange Rates quota strategy

If you use `EXCHANGE_RATE_SOURCE=openexchangerates`, the app applies a more
conservative policy to avoid exhausting the free plan:

- weekday automatic refresh only,
- no remote fetches on Saturday or Sunday,
- local weekend mirroring for charts,
- a local monthly request counter,
- a configurable target cap, usually `95%` of the monthly quota,
- an optional cooldown between manual checks and refreshes,
- historical OER fetches disabled by default on the free plan.

The relevant optional env vars are:

```env
OER_MONTHLY_REQUEST_QUOTA=1000
OER_TARGET_USAGE_RATIO=0.95
OER_MIN_REQUEST_INTERVAL_MINUTES=240
OER_ALLOW_HISTORICAL=False
```

For paid OER plans, you can enable:

```env
OER_ALLOW_HISTORICAL=True
```

but that should be done only if the quota is large enough for historical calls.

For the initial load or to update the full history:

```bash
uv run manage.py fetch_rates --days 365
```

If `OER_ALLOW_HISTORICAL=False`, Open Exchange Rates runs are automatically
downgraded to latest-only mode to protect quota.

### Command options

```
uv run manage.py fetch_rates [options]

  --days N        Number of days to fetch (default: 90)
  --pair CODE     Specific pair to update (e.g. usd-brl). Default: all active.
  --no-alerts     Skip alert evaluation on this run
```

When finished, the command prints a summary of indicators per pair and shows the
UYU → BRL route comparator in the console.

---

## Admin panel

Access `/admin/` to view and edit records directly. First create a superuser:

```bash
uv run manage.py createsuperuser
```

From the admin you can manage the three pairs, view the rate history filtered by
pair, adjust configurations, and review recorded purchases.

---

## FAQ

**Is the data real-time?**
No. The API provides daily rates. The current day's rate may update multiple
times if you run `fetch_rates` more than once during the day.

**Do I need an API key?**
No. Rate data comes from [AwesomeAPI](https://economia.awesomeapi.com.br), which is
free and requires no registration or API key. Telegram alerts are optional; they
require a bot token from @BotFather and a chat ID.

If you switch to **Open Exchange Rates**, then yes: you must set
`OPENEXCHANGERATES_APP_ID`. On the free plan, the app is designed to conserve
requests and stay under a configurable monthly safety cap.

**How do I check the Open Exchange Rates quota manually?**
Click **⚙ Cuota OER** in the top bar. The panel shows:

- the current OER plan and API status,
- requests used, remaining, and quota,
- days elapsed and remaining in the OER month,
- the app's local tracked usage and local safety cap,
- a suggested remaining daily budget based on the configured quota target.

This check is manual on purpose, so it does not add background traffic every
time you open a page.

**How do I set up Telegram alerts?**
1. Open Telegram and start a chat with [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts — copy the token it gives you.
3. Send any message to your new bot, then open:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   Find `"chat":{"id":...}` — that number is your `TELEGRAM_CHAT_ID`.
4. Set both values in your `.env`:
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
   TELEGRAM_CHAT_ID=987654321
   ```
5. Click **Enviar Alerta** on any pair to confirm delivery.

**What happens if the API doesn't respond?**
The "↻ Actualizar" button shows a spinner while trying to fetch data. If it
fails, existing data is preserved with no error shown to the user. The CLI
command does print the error.

If the OER quota guard blocks a request, the app also keeps the current data and
waits for the next allowed window or the next monthly reset.

**Does the route comparator account for fees?**
No. It calculates gross rates directly from the API rates. Your bank's or
exchange house's fees may change the actual outcome.

**Can I use PostgreSQL instead of SQLite?**
Not as a one-line configuration change. SQLite is the supported database for
the current single-owner deployment. Move to PostgreSQL as a planned migration
when concurrent users, multiple hosts, tenant isolation, reporting, or stricter
recovery targets require it; see the product roadmap.

**Can I add more pairs?**
Yes. See the programming guide — it can be done from the admin panel or with a
data migration, without touching code.
