# Plan: Telegram Bot Alerts Integration

## Goal

Replace the per-pair webhook URL input with a single, project-wide Telegram bot
configured via environment variables. Add a "Test Alert" button in the UI so the
user can verify delivery without waiting for a real signal.

---

## Current state

- **`PairConfig.alert_webhook_url`** — each pair stores its own webhook URL.
- **`alerts.py` → `_send_webhook()`** — POSTs a JSON payload to that URL.
- **`config_form.html`** — has an `<input type="url">` for the webhook URL.
- **Cron / management command** — calls `check_and_send()` after each fetch,
  which evaluates conditions and calls `_send_webhook()` per triggered alert.

## Target state

- A single Telegram bot token + chat ID, read from env vars, used for all pairs.
- The webhook URL field is removed from the model, form, and views.
- `alerts.py` sends messages via the Telegram Bot API (`sendMessage`).
- A "Test Alert" button on each pair's config panel sends a sample message to
  Telegram and shows success/failure inline via HTMX.

---

## Environment variables

```
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...   # from @BotFather
TELEGRAM_CHAT_ID=987654321             # target chat/group/channel ID
```

Both are optional. When either is missing, alert sending is silently skipped
(same behaviour as the current empty-webhook-URL case).

---

## Implementation steps

### 1. Add env vars to `config/settings.py`

```python
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
```

No new dependencies — the existing `requests` library is sufficient.

### 2. Rewrite `rates/services/alerts.py`

Replace `_send_webhook()` with `_send_telegram()`:

```python
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

def _send_telegram(message: str) -> bool:
    """Send a message via Telegram Bot API. Returns True on success."""
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return False
    resp = requests.post(
        TELEGRAM_API.format(token=token),
        json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
        timeout=5,
    )
    resp.raise_for_status()
    return True
```

Update `check_and_send()`:
- Remove the `config.alert_webhook_url` guard.
- Call `_send_telegram(message)` instead of `_send_webhook(...)`.
- Keep the same trigger conditions (strong buy, deviation, rate thresholds).

Add a public helper for the test button — it sends a **real alert with
current data**, not a placeholder:

```python
def send_test_alert(indicators: dict, decision: dict, config, pair_name: str) -> bool:
    """
    Build and send a real alert message using current pair data.
    Uses the same format as production alerts so the user sees exactly
    what future notifications will look like.  Returns True on success.
    """
    signal_es = SIGNAL_LABELS.get(decision["signal"], decision["signal"])
    msg = (
        f"🔔 *{pair_name}* — Señal: *{signal_es}*\n"
        f"Cotización: `{indicators['current_rate']:.4f}`\n"
        f"Desviación: `{indicators['deviation']:+.2f}%`\n"
        f"Confianza: {decision['confidence']}\n"
        f"Sugerido: `${decision['suggested_amount']:.0f}` "
        f"({decision['allocation_pct']}% del presupuesto)"
    )
    return _send_telegram(msg)
```

### 3. Remove `alert_webhook_url` from `PairConfig`

- Delete the `alert_webhook_url` field from `rates/models.py`.
- Generate a migration (`makemigrations`) to drop the column.
- Remove the field from `rates/admin.py` if it appears in `list_display`.

### 4. Update `config_form.html`

- Remove the "URL Webhook" `<input>` and its label.
- Add a "Test Alert" button that POSTs via HTMX to a new endpoint.
- Show inline feedback (success ✓ or error ✕) after the POST.

Rough template fragment:

```html
<button type="button"
  hx-post="{% url 'rates:test_alert' pair.slug %}"
  hx-target="#alert-feedback"
  hx-swap="innerHTML"
  class="...">
  Enviar Alerta de Prueba
</button>
<span id="alert-feedback"></span>
```

### 5. Add `test_alert` view + URL

**`rates/views.py`:**

The view computes real indicators and decision for the pair, then passes
them to `send_test_alert` — the message the user receives in Telegram is
identical to what a cron-triggered alert would send.

```python
@require_http_methods(["POST"])
def test_alert(request, pair_code):
    pair = get_object_or_404(CurrencyPair, code=pair_code.upper(), active=True)
    config = _get_or_create_config(pair)
    rates_list = list(ExchangeRate.objects.filter(pair=pair).order_by("date"))
    indicators = compute_all(rates_list)
    if not indicators:
        return HttpResponse(
            '<span class="text-amber-400 text-xs">⚠ Sin datos suficientes</span>'
        )
    decision = build_decision(indicators, config)
    try:
        ok = send_test_alert(indicators, decision, config, pair_name=pair.name)
    except Exception:
        logger.warning("test_alert failed for %s", pair.code, exc_info=True)
        ok = False
    if ok:
        return HttpResponse('<span class="text-emerald-400 text-xs">✓ Enviado</span>')
    return HttpResponse(
        '<span class="text-red-400 text-xs">'
        '✕ Error (revisa TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID)</span>'
    )
```

**`rates/urls.py`:**

```python
path("<str:pair_code>/test-alert/", views.test_alert, name="test_alert"),
```

### 6. Update `update_config` view

- Remove handling of `alert_webhook_url` from `request.POST`.

### 7. Update docs and env examples

- **`.env.example`** — add `TELEGRAM_BOT_TOKEN=` and `TELEGRAM_CHAT_ID=`.
- **`README.md`** — add Telegram vars to the env table.
- **`docs/deployment.md`** — add Telegram vars to the env table.
- **`docs/programming-guide.md`** — update alerts section, env table.
- **`docs/user-guide.md`** — update alerts/configuration section:
  explain how to create a bot via @BotFather and obtain the chat ID.
- **`overview.md`** — update the alerts description.

### 8. Verify

- `uv run manage.py makemigrations` — should create migration for dropped field.
- `uv run manage.py migrate`
- `uv run manage.py check --deploy` — should pass cleanly.
- Manual test: set env vars, click "Enviar Alerta de Prueba", confirm Telegram
  message arrives.
- `uv run manage.py fetch_rates --days 3` — confirm cron alert flow still works.

---

## Files changed (expected)

| File | Change |
|---|---|
| `config/settings.py` | Add 2 env vars |
| `rates/models.py` | Remove `alert_webhook_url` field |
| `rates/services/alerts.py` | Replace webhook with Telegram `sendMessage` |
| `rates/views.py` | Remove webhook handling in `update_config`; add `test_alert` view |
| `rates/urls.py` | Add `test-alert/` route |
| `rates/admin.py` | Remove `alert_webhook_url` from admin if present |
| `rates/templates/rates/partials/config_form.html` | Remove webhook input; add test button |
| `rates/migrations/000X_*.py` | Auto-generated: drop `alert_webhook_url` |
| `.env.example` | Add `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| `README.md` | Update env table |
| `docs/deployment.md` | Update env table |
| `docs/programming-guide.md` | Update alerts + env sections |
| `docs/user-guide.md` | Update alerts section with Telegram setup |
| `overview.md` | Update alerts description |

---

## Out of scope

- Receiving messages from Telegram (no webhook listener / bot commands).
- Per-pair chat IDs (all alerts go to one chat).
- Rich media (images, inline keyboards) — plain Markdown text only.
- Message queuing or async sending — `requests.post` with 5 s timeout is fine
  for a personal-use app.
