# Guía de Programación — Monitor Cambiario

Convenciones, patrones de diseño y guía para extender el proyecto.

---

## Estructura del proyecto

```
rates_monitor/
├── config/                        # Configuración de Django (settings, urls, wsgi)
├── rates/                         # Única app Django
│   ├── migrations/                # 0001–0005 (schema + data + Purchase)
│   ├── services/                  # Lógica de negocio pura (sin Django)
│   │   ├── fetcher.py             # Obtención de datos de la API por par
│   │   ├── indicators.py          # Cálculo de indicadores técnicos
│   │   ├── decision.py            # Motor de señales y asignación de capital
│   │   ├── cross_pair.py          # Comparador de rutas UYU → BRL
│   │   └── alerts.py              # Notificaciones vía webhook
│   ├── templatetags/
│   │   └── rates_extras.py        # Filtros de template personalizados
│   ├── management/commands/
│   │   └── fetch_rates.py         # Comando CLI para cron (todos los pares)
│   ├── templates/rates/
│   │   ├── login.html             # Formulario de código de acceso (standalone)
│   │   ├── overview.html          # Página de resumen (comparador + capital)
│   │   ├── dashboard.html         # Dashboard por par
│   │   └── partials/              # Fragmentos HTMX
│   │       ├── stats.html         # Tarjetas de indicadores/señal (auto-refresh)
│   │       ├── config_form.html   # Configuración por par
│   │       └── purchases.html     # Capital desplegado (HTMX add/delete)
│   ├── models.py                  # CurrencyPair, ExchangeRate, Purchase, PairConfig
│   ├── views.py                   # Todas las vistas + helpers
│   ├── urls.py                    # Rutas con slugs en minúsculas
│   ├── middleware.py              # PasscodeMiddleware
│   ├── context_processors.py     # Inyecta all_pairs en cada template
│   ├── translations.py            # Mapeo de constantes internas → español
│   └── admin.py
├── templates/
│   └── base.html                  # Layout global (nav con tabs de pares, logout)
└── docs/
```

---

## Principios de diseño

### 1. Separación entre lógica y framework

Toda la lógica de negocio vive en `rates/services/`. Esos módulos son **funciones Python puras**: no importan Django, no hacen queries, no usan `request`. Esto los hace fáciles de testear y reusar desde cualquier contexto (views, comandos de gestión, scripts).

```python
# Correcto — función pura, testeable en aislamiento
def compute_deviation(rate: float, ma90: float) -> float:
    return round((rate - ma90) / ma90 * 100, 4)

# Incorrecto — mezcla lógica con acceso a datos
def compute_deviation_from_db():
    rate = ExchangeRate.objects.last().rate  # acoplamiento innecesario
    ...
```

### 2. Las views son orquestadoras

Las views en `rates/views.py` hacen una sola cosa: obtener datos del ORM, llamar a los servicios, y armar el contexto para el template. No contienen lógica de negocio.

```python
def dashboard(request, pair_code):
    pair       = get_object_or_404(CurrencyPair, code=pair_code.upper(), active=True)
    rates_list = list(ExchangeRate.objects.filter(pair=pair).order_by("date"))
    config     = _get_or_create_config(pair)
    indicators = compute_all(rates_list)          # servicio
    decision   = build_decision(indicators, config) # servicio
    return render(request, "rates/dashboard.html", {...})
```

### 3. Las constantes de dominio son siempre en inglés

Los valores almacenados en la base de datos y usados en comparaciones Python (`STRONG BUY`, `HIGH`, `up`) se mantienen siempre en inglés. Las traducciones al español son solo para display, centralizadas en `rates/translations.py`.

**Por qué:** mezclar el idioma de presentación con el de dominio haría que renombrar una señal requiera una migración de base de datos.

### 4. Los pares cambiarios son entidades gestionadas

No hay ningún código de par en duro en la lógica de negocio. Todas las funciones reciben un objeto `CurrencyPair` o una lista de tasas ya filtradas. Añadir un nuevo par solo requiere insertar una fila en la tabla `CurrencyPair` (y su `PairConfig`) — el resto del sistema lo detecta automáticamente.

---

## Modelos

### `CurrencyPair`

Entidad central. Contiene el código (`USD-BRL`), nombre legible, código de API de AwesomeAPI y estado activo.

**Propiedades calculadas** (sin columnas en BD):
- `slug` → `code.lower()`, usado en URLs
- `base_currency` → parte izquierda del código (`USD` en `USD-BRL`)
- `quote_currency` → parte derecha del código (`BRL` en `USD-BRL`)

### `ExchangeRate`

Un registro por día y par. Restricción única `(pair, date)`. Campos `high` y `low` son opcionales.

### `PairConfig`

Relación `OneToOne` con `CurrencyPair`. Almacena umbrales de decisión, presupuesto mensual y configuración de alertas por par. Se crea automáticamente con defaults si no existe (`_get_or_create_config(pair)`).

### `Purchase`

Registra conversiones reales ejecutadas por el usuario. Campos: `pair`, `date`, `amount_spent` (moneda base), `amount_received` (moneda cotizada), `note`. La tasa efectiva (`effective_rate`) es una propiedad calculada: `amount_received / amount_spent`.

---

## Capa de servicios

### `services/fetcher.py`

```python
def fetch_and_store(pair: CurrencyPair, days: int = 90) -> tuple[int, int]:
```

- Usa `pair.api_code` para construir la URL de AwesomeAPI.
- Usa `update_or_create(pair=pair, date=rate_date, ...)` para ser idempotente.
- Lanza excepciones — el llamador decide qué hacer.

### `services/indicators.py`

Funciones puras que reciben listas de floats y devuelven floats:

```python
def compute_ma(values: list[float], window: int) -> float | None: ...
def compute_deviation(rate: float, ma90: float) -> float: ...
def compute_momentum(values: list[float]) -> str: ...   # "up" | "down" | "neutral"
def compute_volatility(values: list[float], window: int = 14) -> float: ...
def compute_all(rates_list) -> dict | None: ...         # orquestadora
def compute_rolling_ma(values: list[float], window: int) -> list[float | None]: ...
```

`compute_rolling_ma` devuelve `None` en los primeros `window-1` puntos para que Chart.js deje esa parte de la línea vacía.

### `services/decision.py`

```python
def build_decision(indicators: dict, config: PairConfig) -> dict:
    # Devuelve: signal, confidence, suggested_amount, allocation_pct, color
```

Las constantes de señal (`STRONG_BUY`, etc.) nunca deben cambiar — están almacenadas en la BD y comparadas en código.

### `services/cross_pair.py`

Compara las dos rutas posibles para convertir UYU → BRL:

```python
def compute_cross_pair() -> dict | None:
    # direct_rate   = cotización UYU-BRL
    # indirect_rate = cotización UYU-USD × USD-BRL
    # Devuelve None si algún par no tiene datos aún
```

Devuelve `None` con degradación elegante cuando faltan datos de cualquiera de los tres pares.

### `services/alerts.py`

```python
def check_and_send(indicators, decision, config, pair_name: str = "") -> list[str]:
```

- Nunca lanza excepciones: los errores de webhook se logean pero no interrumpen el flujo.
- Incluye `pair_name` como prefijo en todos los mensajes (`[Dólar / Real] Señal COMPRA FUERTE…`).
- El payload del webhook incluye el campo `pair` para que el receptor pueda filtrar por par.

---

## Seguridad — PasscodeMiddleware

`rates/middleware.py` intercepta todas las peticiones. Si `settings.ACCESS_PASSCODE` está definido:

1. Rutas exentas: `/login/`, `/logout/`, `/admin/` — pasan sin verificación.
2. Comprueba la cookie `rm_access` con `django.core.signing.loads(max_age=86400)`.
3. Si la cookie no existe o está expirada → redirige a `/login/?next=<ruta>`.

La comparación del código en `login_view` usa `hmac.compare_digest` (tiempo constante, seguro frente a timing attacks). El token firmado usa la `SECRET_KEY` de Django — no se necesita tabla adicional en BD.

```python
# settings.py
ACCESS_PASSCODE = os.environ.get("ACCESS_PASSCODE", "")
# Vacío → middleware desactivado (comodidad en desarrollo)
```

---

## Templates y HTMX

### Estructura

```
templates/base.html                    ← layout global (tabs de pares, logout)
rates/templates/rates/
  login.html                           ← standalone (no extiende base.html)
  overview.html                        ← extends base.html
  dashboard.html                       ← extends base.html
  partials/
    stats.html                         ← HTMX polling cada 300s
    config_form.html                   ← HTMX POST por par
    purchases.html                     ← HTMX add/delete compras
```

### Patrón de auto-refresh (polling)

El `div#stats-section` en `stats.html` se auto-refresca con `hx-trigger="every 300s"`. Para que el polling continúe después de un `outerHTML` swap, el partial devuelto **debe incluir los mismos atributos HTMX** en su elemento raíz — incluyendo la URL correcta del par:

```html
<div id="stats-section"
     hx-get="{% url 'stats_partial' pair.slug %}"
     hx-trigger="every 300s"
     hx-swap="outerHTML">
```

### URLs parametrizadas por par

Todas las URLs de partial usan `pair.slug` (lowercase). El par siempre está disponible en contexto porque:
- Las views de dashboard lo pasan explícitamente.
- El context processor `active_pairs` inyecta `all_pairs` en todos los templates para el nav.

### CSRF con HTMX

El token se inyecta globalmente en `base.html`:

```html
<meta name="htmx-config" content='{"defaultHeaders":{"X-CSRFToken":"{{ csrf_token }}"}}'>
```

`login.html` es standalone (no extiende `base.html`) y usa `{% csrf_token %}` directamente en el formulario.

### Filtros de template

```html
{% load rates_extras %}
{{ decision.signal|signal_label }}        {# "COMPRA FUERTE" #}
{{ decision.confidence|confidence_label }} {# "ALTA" #}
{{ indicators.momentum|momentum_label }}   {# "al alza ↑" #}
```

---

## Convenciones de código

### Nombres

- **Funciones:** `snake_case`, verbo + sustantivo (`compute_all`, `fetch_and_store`, `build_decision`)
- **Constantes de dominio:** `UPPER_SNAKE_CASE` (`STRONG_BUY`, `DO_NOT_BUY`)
- **Templates:** `snake_case.html`, partials en subdirectorio `partials/`
- **URL slugs:** siempre minúsculas (`usd-brl`, `uyu-brl`)

### Type hints

Todas las funciones de servicios usan type hints con `|` para unions (Python 3.10+):

```python
def compute_ma(values: list[float], window: int) -> float | None: ...
def compute_cross_pair() -> dict | None: ...
```

### Logging

Usar el logger del módulo, nunca `print()`:

```python
logger = logging.getLogger(__name__)
logger.info("Fetching 90 days of USD-BRL")
logger.warning("ALERTA: señal disparada")
logger.error("Error al enviar webhook")
```

---

## Cómo añadir un nuevo par cambiario

1. Insertar en la BD (o crear una migración de datos):
   ```python
   pair = CurrencyPair.objects.create(
       code="EUR-BRL", name="Euro / Real", api_code="EUR-BRL", active=True
   )
   PairConfig.objects.create(pair=pair)
   ```

2. Poblar histórico:
   ```bash
   uv run python manage.py fetch_rates --pair eur-brl --days 90
   ```

3. El par aparece automáticamente en la navegación, en el overview y en el comparador de rutas si se actualiza `cross_pair.py` para incluirlo.

## Cómo añadir una nueva señal

1. Añadir la constante en `services/decision.py`:
   ```python
   EXTREME_BUY = "EXTREME BUY"
   ```
2. Actualizar `SIGNAL_MULTIPLIERS` y `SIGNAL_CSS`.
3. Actualizar `get_signal()` con la nueva condición.
4. Añadir la traducción en `rates/translations.py`.
5. Actualizar los bloques `{% if %}` en los templates.

## Cómo añadir un nuevo indicador

1. Escribir una función pura en `services/indicators.py`.
2. Añadir el resultado al dict de `compute_all()`.
3. Usarlo en `build_decision()` si afecta la señal.
4. Mostrarlo en `partials/stats.html`.

---

## Testing

Los servicios son funciones puras → se testean sin base de datos ni HTTP:

```python
from rates.services.indicators import compute_deviation, compute_momentum
from rates.services.cross_pair import compute_cross_pair

def test_deviation_positiva():
    assert compute_deviation(5.80, 5.50) == pytest.approx(5.45, rel=1e-2)

def test_momentum_al_alza():
    assert compute_momentum([5.0, 5.1, 5.2]) == "up"
```

Para testear views con queries, usar `@pytest.mark.django_db` con fixtures de pytest-django.

---

## Variables de entorno

| Variable | Por defecto | Descripción |
|---|---|---|
| `SECRET_KEY` | *(valor de desarrollo)* | Clave secreta de Django. Cambiar en producción. |
| `DEBUG` | `True` | Poner en `False` para producción. |
| `ALLOWED_HOSTS` | `*` | Lista de hosts separados por coma. |
| `ACCESS_PASSCODE` | *(vacío)* | Código de acceso al sitio. Vacío = sin protección. |

Ejemplo de `.env` para producción:

```env
SECRET_KEY=tu-clave-secreta-larga-y-aleatoria
DEBUG=False
ALLOWED_HOSTS=tudominio.com
ACCESS_PASSCODE=tu-codigo-secreto
```
