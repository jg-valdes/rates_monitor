# Monitor Cambiario — Visión General del Proyecto

## Objetivo

Herramienta personal para encontrar la mejor ruta para convertir Pesos Uruguayos (UYU)
a Reales Brasileños (BRL), con o sin pasar por Dólares (USD) como paso intermedio.

El sistema monitorea 3 pares cambiarios individualmente (señales técnicas por par) y
calcula en tiempo real cuál ruta produce más BRL por cada peso uruguayo.

**Rutas posibles:**

| Ruta       | Camino          | Pares usados             |
|------------|-----------------|--------------------------|
| Directa    | UYU → BRL       | UYU-BRL                  |
| Indirecta  | UYU → USD → BRL | UYU-USD + USD-BRL        |

**Pares monitoreados:**

| Par     | Significado                        | Rol en la decisión      |
|---------|------------------------------------|-------------------------|
| USD-BRL | Cuántos reales vale 1 dólar        | Ruta indirecta (paso 2) |
| UYU-USD | Cuántos dólares vale 1 peso uru.   | Ruta indirecta (paso 1) |
| UYU-BRL | Cuántos reales vale 1 peso uru.    | Ruta directa            |

**Fuente de datos:** [AwesomeAPI](https://economia.awesomeapi.com.br)
**Idioma de la interfaz:** Español de España / Cuba
**Base de datos:** SQLite

---

## Estado Actual — Implementado

### Stack técnico

- **Backend:** Python 3.14 + Django 6
- **Frontend:** Django Templates + HTMX 2.0 + Tailwind CSS (CDN)
- **Gráficos:** Chart.js 4.4
- **Gestor de paquetes:** uv

### Estructura del proyecto

```
rates_monitor/
├── config/
│   ├── settings.py          # ACCESS_PASSCODE, middleware, context processor
│   ├── urls.py
│   └── wsgi.py
├── rates/
│   ├── models.py            # CurrencyPair, ExchangeRate, PairConfig
│   ├── views.py             # login, logout, overview, dashboard, stats, refresh, config
│   ├── urls.py              # rutas con slugs en minúsculas
│   ├── admin.py             # CurrencyPair, ExchangeRate, PairConfig
│   ├── middleware.py        # PasscodeMiddleware
│   ├── context_processors.py # inyecta all_pairs en cada template
│   ├── translations.py      # etiquetas en español para constantes internas
│   ├── templatetags/
│   │   └── rates_extras.py  # filtros: signal_label, confidence_label, momentum_label
│   ├── services/
│   │   ├── fetcher.py       # fetch_and_store(pair, days)
│   │   ├── indicators.py    # MA, desviación, momentum, volatilidad
│   │   ├── decision.py      # señal, confianza, asignación de capital
│   │   ├── cross_pair.py    # comparador de rutas UYU→BRL
│   │   └── alerts.py        # notificaciones vía webhook
│   ├── management/commands/
│   │   └── fetch_rates.py   # CLI para obtener cotizaciones
│   ├── migrations/
│   │   ├── 0001_initial.py
│   │   ├── 0002_currency_pair_pair_config.py  # schema
│   │   ├── 0003_seed_pairs.py                 # datos iniciales
│   │   └── 0004_finalize_exchange_rate.py     # restricciones + elimina UserConfig
│   └── templates/rates/
│       ├── login.html
│       ├── overview.html
│       ├── dashboard.html
│       └── partials/
│           ├── stats.html
│           └── config_form.html
└── templates/
    └── base.html            # nav con tabs de pares + botón logout
```

### Modelos

**`CurrencyPair`**
- `code` — e.g. `"USD-BRL"` (único)
- `name` — e.g. `"Dólar / Real"`
- `api_code` — código usado en la URL de AwesomeAPI
- `active` — activo/inactivo
- `slug` (property) — `code.lower()`, usado en URLs

**`ExchangeRate`**
- `pair` → FK a `CurrencyPair`
- `date`, `rate`, `high`, `low`, `created_at`
- Restricción única: `(pair, date)`

**`PairConfig`** (OneToOne con CurrencyPair)
- `monthly_budget`, `threshold_strong_buy`, `threshold_moderate_buy`, `threshold_do_not_buy`
- `alert_webhook_url`, `alert_on_strong_buy`, `alert_on_deviation_above`, `alert_on_rate_above`

### URLs

| Método | URL                        | Vista            |
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

### Motor de indicadores (por par)

- **MA 30 / MA 90** — media móvil simple
- **Desviación** — `(cotización - MA90) / MA90 * 100`
- **Momentum** — tendencia de los últimos 3 valores (`up` / `down` / `neutral`)
- **Volatilidad** — cambio absoluto medio de los últimos 14 días

### Motor de decisión (por par)

| Desviación        | Señal           | Asignación |
|-------------------|-----------------|------------|
| > +3%             | STRONG BUY      | 150%       |
| > +1.5%           | MODERATE BUY    | 100%       |
| entre -1% y +1.5% | NEUTRAL         | 50%        |
| < -1%             | DO NOT BUY      | 20%        |

Confianza ajustada por momentum: `STRONG BUY + up = HIGH`, etc.

### Comparador de rutas (cross_pair.py)

```
direct_rate   = cotización UYU-BRL             (BRL por 1 UYU)
indirect_rate = cotización UYU-USD × USD-BRL   (BRL por 1 UYU vía USD)
mejor_ruta    = la que produce más BRL por peso
```

Mostrado en `/overview/` con ventaja porcentual.

### Seguridad

- `ACCESS_PASSCODE` en `.env` activa la protección (vacío = desactivado en dev)
- `PasscodeMiddleware` bloquea todas las rutas excepto `/login/` y `/logout/`
- Comparación con `hmac.compare_digest` (tiempo constante)
- Token firmado con `signing.dumps()` almacenado en cookie `rm_access`
  (`httponly`, `samesite=Lax`, `secure` en producción, caducidad 24 h)

### Alertas

Webhook configurable por par. Se dispara cuando:
- Señal STRONG BUY activa (si habilitado)
- Desviación supera umbral configurado
- Cotización supera umbral configurado

Payload incluye: par, señal, cotización, desviación, confianza, monto sugerido.

### Comando CLI

```bash
# Obtener todos los pares activos (90 días por defecto)
uv run python manage.py fetch_rates

# Par específico, últimos 3 días, sin alertas
uv run python manage.py fetch_rates --pair usd-brl --days 3 --no-alerts
```

Imprime indicadores por par y comparador de rutas al final.

---

## Cómo ejecutar en local

```bash
# Instalar dependencias
uv sync

# Aplicar migraciones (ya incluye los 3 pares y datos migrados)
uv run python manage.py migrate

# Poblar cotizaciones iniciales
uv run python manage.py fetch_rates

# Arrancar servidor
uv run python manage.py runserver
```

Abre `http://localhost:8000` — redirige a `/overview/`.

Para activar el passcode:
```bash
export ACCESS_PASSCODE=tu-secreto
```

---

### Seguimiento de capital (Purchase)

Modelo `Purchase` para registrar conversiones reales ejecutadas por el usuario.

**Campos:** `pair`, `date`, `amount_spent` (moneda base), `amount_received` (moneda cotizada), `note`, `created_at`
**Propiedad calculada:** `effective_rate = amount_received / amount_spent`

Por par se muestran:
- Total gastado / total recibido / tasa media ponderada / número de operaciones
- Tabla de compras individuales con botón de eliminar (HTMX)
- Formulario inline para registrar nuevas compras

En `/overview/`: tabla consolidada de capital desplegado por los tres pares.

Las monedas se derivan automáticamente del código del par (`USD-BRL` → gasta `USD`, recibe `BRL`).

---

## Pendiente / Próximos pasos

- Automatizar `fetch_rates` vía cron (e.g. `--days 3` cada hora)
- Migrar base de datos a PostgreSQL en producción
