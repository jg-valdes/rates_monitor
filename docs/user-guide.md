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
| **USD-BRL** | Dollar / Real pair dashboard |
| **UYU-USD** | Uruguayan Peso / Dollar pair dashboard |
| **UYU-BRL** | Uruguayan Peso / Real pair dashboard |

The **↻ Actualizar** button (visible on each dashboard) fetches the latest rate
from the API and refreshes the cards.

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

### 2. Chart — Last 90 days

Actual rate in purple, MA 30 in yellow, and MA 90 in red. Hover over the chart
to see exact values for each date.

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

Alerts are sent via Telegram. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
in your `.env` file to enable them (see the FAQ for setup instructions).

Configure the conditions per pair:

- **Alert if deviation >:** fires when deviation vs MA90 exceeds that percentage
- **Alert if rate >:** fires when the current rate exceeds that value
- **Alert on COMPRA FUERTE:** checkbox — fires whenever the strong-buy signal is active

Each alert message includes pair name, signal, current rate, deviation,
confidence level, and suggested amount — identical to what **Enviar Alerta de
Prueba** sends.

The **Enviar Alerta de Prueba** button sends a real message using current data
so you can verify delivery and see the exact message format without waiting for
a signal condition to trigger.

---

## Daily automation

To keep data up to date without manual intervention, configure a cron job:

```bash
# Update all pairs every hour (weekdays)
0 * * * 1-5 cd /path/to/project && uv run manage.py fetch_rates --days 3
```

The `--days 3` option fetches the last 3 days, ensuring no rate is missed due
to timezone differences.

For the initial load or to update the full history:

```bash
uv run manage.py fetch_rates --days 365
```

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
5. Click **Enviar Alerta de Prueba** on any pair to confirm delivery.

**What happens if the API doesn't respond?**
The "↻ Actualizar" button shows a spinner while trying to fetch data. If it
fails, existing data is preserved with no error shown to the user. The CLI
command does print the error.

**Does the route comparator account for fees?**
No. It calculates gross rates directly from the API rates. Your bank's or
exchange house's fees may change the actual outcome.

**Can I use PostgreSQL instead of SQLite?**
Yes. Change the `DATABASES` variable in `config/settings.py`. There are no
SQLite-specific queries in the code.

**Can I add more pairs?**
Yes. See the programming guide — it can be done from the admin panel or with a
data migration, without touching code.
