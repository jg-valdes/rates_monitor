# Guía de Programación — Monitor USD/BRL

Convenciones, patrones de diseño y guía para extender el proyecto.

---

## Estructura del proyecto

```
rates_monitor/
├── config/                  # Configuración de Django (settings, urls, wsgi)
├── rates/                   # Única app Django
│   ├── migrations/
│   ├── services/            # Lógica de negocio pura (sin Django)
│   │   ├── fetcher.py       # Obtención de datos de la API
│   │   ├── indicators.py    # Cálculo de indicadores técnicos
│   │   ├── decision.py      # Motor de señales y asignación
│   │   └── alerts.py        # Notificaciones via webhook
│   ├── templatetags/
│   │   └── rates_extras.py  # Filtros de template personalizados
│   ├── management/commands/
│   │   └── fetch_rates.py   # Comando de gestión para cron
│   ├── templates/rates/
│   │   ├── dashboard.html
│   │   └── partials/        # Fragmentos HTMX
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   ├── translations.py      # Mapeo de constantes internas → etiquetas en español
│   └── admin.py
├── templates/
│   └── base.html            # Layout base con CDNs
└── docs/
```

---

## Principios de diseño

### 1. Separación entre lógica y framework

Toda la lógica de negocio vive en `rates/services/`. Esos módulos son **funciones Python puras**: no importan Django, no hacen queries, no usan `request`. Esto los hace fáciles de testear y de reusar desde cualquier contexto (views, comandos de gestión, scripts).

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

Las views en `rates/views.py` hacen exactamente una cosa: obtener los datos del ORM, llamar a los servicios, y armar el contexto para el template. No contienen lógica de negocio.

```python
def dashboard(request):
    rates_list = list(ExchangeRate.objects.order_by("date"))  # query
    config = UserConfig.get_solo()                             # query
    indicators = compute_all(rates_list)                       # servicio
    decision = build_decision(indicators, config)              # servicio
    return render(request, "rates/dashboard.html", {...})      # render
```

### 3. Las constantes de dominio son siempre inglés

Los valores almacenados en la base de datos y usados en comparaciones de código (`STRONG BUY`, `HIGH`, `up`) se mantienen siempre en inglés. Las traducciones al español son únicamente para display, centralizadas en `rates/translations.py`.

**Por qué:** mezclar el idioma de presentación con el de dominio haría que renombrar una señal requiera una migración de base de datos.

```python
# rates/translations.py — único lugar donde se traduce
SIGNAL_LABELS = {
    "STRONG BUY": "COMPRA FUERTE",
    ...
}
```

---

## Capa de servicios

### `services/fetcher.py`

**Responsabilidad única:** comunicarse con la API externa y persistir los datos.

- Usa `update_or_create` para ser idempotente (se puede ejecutar N veces sin duplicar registros).
- Lanza excepciones en lugar de tragárselas. El llamador (view o comando) decide qué hacer.
- No hace transformaciones de negocio: solo mapea campos de API → campos de modelo.

### `services/indicators.py`

**Funciones puras** que reciben listas de floats y devuelven floats.

```python
# Todas las funciones tienen esta firma:
def compute_ma(values: list[float], window: int) -> float | None: ...
def compute_deviation(rate: float, ma90: float) -> float: ...
def compute_momentum(values: list[float]) -> str: ...  # "up" | "down" | "neutral"
def compute_volatility(values: list[float], window: int = 14) -> float: ...

# Función orquestadora que llama a todas las anteriores:
def compute_all(rates_list) -> dict | None: ...
```

La función `compute_rolling_ma` devuelve una lista de `float | None` para alimentar Chart.js. Los `None` los primeros N-1 puntos hacen que Chart.js deje esa parte de la línea vacía.

### `services/decision.py`

Transforma indicadores + configuración en una decisión accionable.

```python
# Constantes de señal — nunca cambiar los strings (están en la DB)
STRONG_BUY = "STRONG BUY"
MODERATE_BUY = "MODERATE BUY"
NEUTRAL = "NEUTRAL"
DO_NOT_BUY = "DO NOT BUY"

# Función pública principal
def build_decision(indicators: dict, config) -> dict:
    signal = get_signal(indicators["deviation"], config)
    confidence = get_confidence(signal, indicators["momentum"])
    ...
    return {"signal": signal, "confidence": confidence, ...}
```

### `services/alerts.py`

- **Nunca lanza excepciones**: los errores de webhook se logean pero no interrumpen el flujo. Una alerta fallida no debe impedir que el comando de gestión termine exitosamente.
- El payload del webhook incluye `signal_es` (español) además del código interno, para que el destinatario pueda mostrar el texto localizado.

---

## Modelos

### `ExchangeRate`

Un registro por día de cotización (restricción `unique=True` en `date`). Campos `high` y `low` son opcionales porque la API no siempre los provee.

### `UserConfig` — patrón Singleton

Siempre tiene `pk=1`. Se accede via `UserConfig.get_solo()` que usa `get_or_create(pk=1)`.

```python
def save(self, *args, **kwargs):
    self.pk = 1  # garantiza que solo existe una fila
    super().save(*args, **kwargs)
```

No usar librerías externas (`django-solo`) para algo que se resuelve con 3 líneas.

---

## Templates y HTMX

### Estructura de templates

```
templates/base.html              ← layout global (CDNs, nav, footer)
rates/templates/rates/
  dashboard.html                 ← página principal (extends base.html)
  partials/
    stats.html                   ← sección de tarjetas (HTMX-refreshable)
    config_form.html             ← formulario de configuración (HTMX POST)
```

### Patrón de auto-refresh (polling)

El div `#stats-section` en `stats.html` se auto-refresca usando el atributo HTMX `hx-trigger="every 300s"`. Para que el polling continúe después de un swap `outerHTML`, el partial devuelto **debe incluir los mismos atributos HTMX** en su elemento raíz.

```html
{# stats.html — el div raíz tiene los atributos de polling #}
<div id="stats-section"
     hx-get="{% url 'stats_partial' %}"
     hx-trigger="every 300s"
     hx-swap="outerHTML">
  ...
</div>
```

### CSRF con HTMX

En lugar de incluir `{% csrf_token %}` en cada formulario HTMX, el token se inyecta globalmente via la meta tag en `base.html`:

```html
<meta name="htmx-config" content='{"defaultHeaders":{"X-CSRFToken":"{{ csrf_token }}"}}'>
```

Esto aplica el header `X-CSRFToken` a **todos** los requests HTMX. Django acepta el token tanto como campo de formulario como header HTTP.

### Filtros de template

Los filtros `signal_label`, `confidence_label` y `momentum_label` en `rates/templatetags/rates_extras.py` traducen constantes internas a español. Cargarlos con `{% load rates_extras %}` al inicio del template.

```html
{% load rates_extras %}
{{ decision.signal|signal_label }}       {# "COMPRA FUERTE" #}
{{ decision.confidence|confidence_label }} {# "ALTA" #}
```

---

## Convenciones de código

### Nombres

- **Funciones:** `snake_case`, verbo + sustantivo (`compute_all`, `fetch_and_store`, `build_decision`)
- **Constantes de dominio:** `UPPER_SNAKE_CASE` (`STRONG_BUY`, `DO_NOT_BUY`)
- **Templates:** `snake_case.html`, partials en subdirectorio `partials/`
- **URLs:** `snake_case` con nombres descriptivos (`stats_partial`, `refresh_data`)

### Type hints

Todas las funciones de servicios usan type hints. Usar `|` para union types (Python 3.10+):

```python
def compute_ma(values: list[float], window: int) -> float | None: ...
```

### Logging

Usar el logger del módulo, nunca `print()`:

```python
logger = logging.getLogger(__name__)
logger.info("Mensaje informativo")
logger.warning("Alerta disparada")
logger.error("Error recuperable")
```

Los niveles de log están configurados en `config/settings.py`. El logger `rates` está en nivel `INFO`; el resto en `WARNING`.

---

## Cómo agregar una nueva señal

1. Agregar la constante en `rates/services/decision.py`:
   ```python
   EXTREME_BUY = "EXTREME BUY"
   ```

2. Actualizar `SIGNAL_MULTIPLIERS` y `SIGNAL_CSS` en el mismo archivo.

3. Actualizar `get_signal()` con la nueva condición.

4. Agregar la traducción en `rates/translations.py`:
   ```python
   SIGNAL_LABELS["EXTREME BUY"] = "COMPRA EXTREMA"
   ```

5. Actualizar los bloques `{% if %}` en los templates para manejar el nuevo valor.

---

## Cómo agregar un nuevo indicador

1. Escribir una función pura en `rates/services/indicators.py` con tipo de retorno explícito.

2. Agregar el resultado al dict que devuelve `compute_all()`.

3. Usar el indicador en `build_decision()` si afecta a la señal.

4. Mostrarlo en `rates/templates/rates/partials/stats.html`.

---

## Testing

Los servicios son funciones puras → se testean sin base de datos ni cliente HTTP.

```python
# tests/test_indicators.py
from rates.services.indicators import compute_deviation, compute_momentum

def test_deviation_positiva():
    assert compute_deviation(5.80, 5.50) == pytest.approx(5.45, rel=1e-2)

def test_momentum_al_alza():
    assert compute_momentum([5.0, 5.1, 5.2]) == "up"

def test_momentum_neutral():
    assert compute_momentum([5.0, 5.2, 5.1]) == "neutral"
```

Para testear views que hacen queries, usar `@pytest.mark.django_db` con fixtures de pytest-django.

---

## Variables de entorno

| Variable | Por defecto | Descripción |
|---|---|---|
| `SECRET_KEY` | *(valor de desarrollo)* | Clave secreta de Django. Cambiar en producción. |
| `DEBUG` | `True` | Poner en `False` para producción. |
| `ALLOWED_HOSTS` | `*` | Lista de hosts separados por coma. |

Ejemplo de `.env` para producción:

```env
SECRET_KEY=tu-clave-secreta-larga-y-aleatoria
DEBUG=False
ALLOWED_HOSTS=tudominio.com,www.tudominio.com
```

Cargar con `python-dotenv` o pasar directamente como variables de entorno del sistema.
