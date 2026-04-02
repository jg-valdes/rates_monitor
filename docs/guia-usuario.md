# Guía de Usuario — Monitor USD/BRL

Esta aplicación te ayuda a decidir cuándo comprar dólares (USD) con pesos o reales brasileños (BRL), analizando la cotización histórica con indicadores técnicos simples.

---

## Instalación y primer uso

### Requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) instalado

### Pasos

```bash
# 1. Clonar o descargar el proyecto
cd rates_monitor

# 2. Instalar dependencias
uv sync

# 3. Crear la base de datos
uv run python manage.py migrate

# 4. Obtener los últimos 90 días de cotizaciones
uv run python manage.py fetch_rates

# 5. Iniciar el servidor
uv run python manage.py runserver
```

Abrí el navegador en **http://localhost:8000**.

---

## El dashboard

La pantalla principal tiene tres secciones:

### 1. Tarjetas de resumen (fila superior)

| Tarjeta | Qué muestra |
|---|---|
| **USD / BRL** | Cotización actual, medias móviles, desviación, tendencia y volatilidad |
| **Señal de Hoy** | La recomendación del sistema (ver abajo) con nivel de confianza |
| **Asignación Sugerida** | Monto en USD a comprar según tu presupuesto mensual |

Esta sección **se actualiza sola cada 5 minutos** via HTMX. También podés hacer clic en **↻ Actualizar** en la barra superior para forzar una actualización inmediata (incluye obtener la cotización más reciente de la API).

### 2. Gráfico — Últimos 90 días

Muestra la cotización real en morado, la MA 30 en amarillo y la MA 90 en rojo. Pasá el cursor sobre el gráfico para ver los valores exactos de cada fecha.

### 3. Decisiones recientes

Tabla con los últimos 30 días: cotización, señal calculada, confianza y monto sugerido. Útil para ver cómo evolucionaron las señales con el tiempo.

---

## Señales

El sistema calcula cuánto se desvía la cotización actual de su media de 90 días (MA90) y genera una señal:

| Señal | Condición | Asignación sugerida |
|---|---|---|
| **COMPRA FUERTE** | Desviación > umbral alto (por defecto +3%) | 150% del presupuesto mensual |
| **COMPRA MODERADA** | Desviación > umbral moderado (por defecto +1.5%) | 100% del presupuesto |
| **NEUTRAL** | Desviación entre –1% y +1.5% | 50% del presupuesto |
| **NO COMPRAR** | Desviación < –1% | 20% del presupuesto |

> **Ejemplo:** Si el presupuesto mensual es USD 1.000 y la señal es COMPRA FUERTE, el sistema sugiere comprar USD 1.500 ese día.

### Nivel de confianza

Combina la señal con la tendencia (últimas 3 cotizaciones):

- **ALTA** → COMPRA FUERTE + tendencia al alza
- **MEDIA** → COMPRA FUERTE pero tendencia a la baja, o COMPRA MODERADA en tendencia neutra/positiva
- **BAJA** → señal débil o sin confirmación de tendencia

---

## Indicadores técnicos

| Indicador | Descripción |
|---|---|
| **MA 30d** | Media móvil simple de los últimos 30 días |
| **MA 90d** | Media móvil simple de los últimos 90 días (referencia principal) |
| **Desviación** | `(cotización_actual - MA90) / MA90 × 100` — en porcentaje |
| **Tendencia** | "al alza" si los últimos 3 días son consecutivamente más altos, "a la baja" si más bajos, "neutral" en otro caso |
| **Volatilidad** | Variación diaria absoluta promedio de los últimos 14 días |

---

## Configuración

El panel de **Configuración** (columna derecha) permite ajustar parámetros sin tocar código:

### Presupuesto mensual

Ingresá tu presupuesto mensual típico en USD. El sistema multiplica ese valor según la señal para calcular el monto sugerido.

### Umbrales de decisión

Porcentajes de desviación que delimitan las señales:

- **C. Fuerte >** (por defecto 3.0): por encima de este valor → COMPRA FUERTE
- **C. Mod. >** (por defecto 1.5): por encima de este valor → COMPRA MODERADA
- **No Comp. <** (por defecto –1.0): por debajo de este valor → NO COMPRAR

El rango entre "No Comp." y "C. Mod." es la zona NEUTRAL.

### Alertas

Podés recibir notificaciones cuando se cumplan condiciones:

- **URL Webhook**: cualquier URL que acepte un POST JSON (Telegram bot via n8n, Discord, Slack, etc.)
- **Alerta si desviación >**: se dispara cuando la desviación supera ese porcentaje
- **Alerta si cotización >**: se dispara cuando la cotización supera ese valor
- **Alertar al activarse COMPRA FUERTE**: casilla de verificación

---

## Automatización diaria

Para mantener los datos actualizados sin intervención manual, configurá un cron job:

```bash
# Actualizar cada hora (días hábiles)
0 * * * 1-5 cd /ruta/al/proyecto && uv run python manage.py fetch_rates --days 3
```

La opción `--days 3` obtiene los últimos 3 días, lo que garantiza que no se pierda ninguna cotización por diferencias de zona horaria.

Para la carga inicial o para actualizar el historial:

```bash
uv run python manage.py fetch_rates --days 365
```

### Opciones del comando

```
uv run python manage.py fetch_rates [opciones]

  --days N      Cantidad de días a obtener (por defecto: 90)
  --no-alerts   Omitir verificación de alertas en esta ejecución
```

---

## Panel de administración

Accedé a `/admin/` para ver y editar los registros directamente en la base de datos. Primero creá un superusuario:

```bash
uv run python manage.py createsuperuser
```

---

## Preguntas frecuentes

**¿Los datos son en tiempo real?**
No. La API provee cotizaciones diarias. La cotización del día actual puede actualizarse varias veces durante el día si ejecutás `fetch_rates` más de una vez.

**¿Necesito una API key?**
No. El sistema usa [awesomeapi.com.br](https://economia.awesomeapi.com.br), una API pública y gratuita sin autenticación.

**¿Qué pasa si la API no responde?**
El botón "↻ Actualizar" muestra un spinner mientras intenta obtener datos. Si falla, conserva los datos existentes sin mostrar error al usuario. El comando CLI sí muestra el error.

**¿Puedo usar PostgreSQL en lugar de SQLite?**
Sí. Cambiá la variable `DATABASES` en `config/settings.py`. No hay ninguna consulta específica de SQLite en el código.
