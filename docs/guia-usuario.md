# Guía de Usuario — Monitor Cambiario

Esta aplicación te ayuda a encontrar el mejor momento y la mejor ruta para convertir Pesos Uruguayos (UYU) a Reales Brasileños (BRL), monitoreando tres pares cambiarios con indicadores técnicos simples.

---

## Instalación y primer uso

### Requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) instalado

### Pasos

```bash
# 1. Acceder al directorio del proyecto
cd rates_monitor

# 2. Instalar dependencias
uv sync

# 3. Crear la base de datos (incluye los tres pares automáticamente)
uv run python manage.py migrate

# 4. Obtener los últimos 90 días de cotizaciones para todos los pares
uv run python manage.py fetch_rates

# 5. Iniciar el servidor
uv run python manage.py runserver
```

Abre el navegador en **http://localhost:8000**.

### Código de acceso (producción)

Si el sitio está en un servidor accesible desde internet, define la variable de entorno `ACCESS_PASSCODE` antes de arrancar:

```bash
export ACCESS_PASSCODE=tu-codigo-secreto
uv run python manage.py runserver
```

Con el código configurado, la primera vez que entres al sitio se mostrará un formulario de acceso. La sesión dura 24 horas.

---

## Navegación

La barra superior muestra cuatro secciones:

| Pestaña | Contenido |
|---|---|
| **Resumen** | Comparador de rutas + estado de los tres pares + capital desplegado |
| **USD-BRL** | Dashboard del par Dólar / Real |
| **UYU-USD** | Dashboard del par Peso Uruguayo / Dólar |
| **UYU-BRL** | Dashboard del par Peso Uruguayo / Real |

El botón **↻ Actualizar** (visible en cada dashboard) obtiene la cotización más reciente de la API y refresca las tarjetas.

---

## Página de Resumen

### Comparador de Rutas — UYU → BRL

Muestra cuál de las dos rutas posibles produce más reales por cada peso uruguayo en este momento:

- **Ruta directa:** cambiar UYU por BRL directamente (usando el par UYU-BRL)
- **Ruta indirecta:** cambiar UYU por USD y luego USD por BRL (usando UYU-USD × USD-BRL)

El sistema calcula ambas tasas y destaca la mejor con el porcentaje de ventaja. Si faltan datos de algún par, el comparador no se muestra hasta que se pueblen los tres.

### Estado de los Pares

Tres tarjetas con el estado actual de cada par: cotización, señal de hoy y desviación respecto a la media de 90 días. Haz clic en cualquier tarjeta para ir al dashboard completo de ese par.

### Capital Desplegado por Par

Tabla que muestra, para cada par, el total de moneda gastada, el total recibida y la tasa media efectiva de todas las compras registradas.

---

## Dashboard por Par

Cada par tiene su propia página con la misma estructura:

### 1. Tarjetas de resumen (fila superior)

| Tarjeta | Qué muestra |
|---|---|
| **Par** | Cotización actual, medias móviles, desviación, tendencia y volatilidad |
| **Señal de Hoy** | Recomendación del sistema con nivel de confianza |
| **Asignación Sugerida** | Monto a comprar según el presupuesto mensual del par |

Esta sección **se actualiza automáticamente cada 5 minutos**. También puedes forzar una actualización con el botón **↻ Actualizar** en la barra superior.

### 2. Gráfico — Últimos 90 días

Cotización real en morado, MA 30 en amarillo y MA 90 en rojo. Pasa el cursor sobre el gráfico para ver los valores exactos de cada fecha.

### 3. Panel de Configuración

Ajusta los parámetros del par sin tocar código. Ver sección [Configuración](#configuración) más abajo.

### 4. Decisiones Recientes

Tabla con los últimos 30 días: cotización, señal calculada, confianza y monto sugerido. Útil para ver cómo evolucionaron las señales con el tiempo.

### 5. Capital Desplegado

Sección para registrar y consultar las conversiones que has ejecutado realmente en este par:

- **Totales:** suma de moneda gastada, suma de moneda recibida, tasa media ponderada.
- **Tabla de compras:** lista de todas las operaciones registradas con botón de eliminar.
- **Formulario de registro:** introduce fecha, moneda gastada, moneda recibida y una nota opcional.

> Ejemplo para USD-BRL: introduces cuántos USD gastaste y cuántos BRL recibiste. El sistema calcula la tasa efectiva de esa operación y la acumula en los totales.

---

## Señales

El sistema calcula cuánto se desvía la cotización actual de su media de 90 días (MA90) y genera una señal:

| Señal | Condición | Asignación sugerida |
|---|---|---|
| **COMPRA FUERTE** | Desviación > umbral alto (por defecto +3%) | 150% del presupuesto mensual |
| **COMPRA MODERADA** | Desviación > umbral moderado (por defecto +1.5%) | 100% del presupuesto |
| **NEUTRAL** | Desviación entre –1% y +1.5% | 50% del presupuesto |
| **NO COMPRAR** | Desviación < –1% | 20% del presupuesto |

> **Ejemplo:** Si el presupuesto mensual del par USD-BRL es 1.000 USD y la señal es COMPRA FUERTE, el sistema sugiere comprar 1.500 USD ese día.

### Nivel de confianza

Combina la señal con la tendencia (últimas 3 cotizaciones):

- **ALTA** → COMPRA FUERTE + tendencia al alza
- **MEDIA** → COMPRA FUERTE con tendencia a la baja, o COMPRA MODERADA en tendencia neutra/positiva
- **BAJA** → señal débil o sin confirmación de tendencia

---

## Indicadores técnicos

| Indicador | Descripción |
|---|---|
| **MA 30d** | Media móvil simple de los últimos 30 días |
| **MA 90d** | Media móvil simple de los últimos 90 días (referencia principal) |
| **Desviación** | `(cotización_actual − MA90) / MA90 × 100` — en porcentaje |
| **Tendencia** | "al alza" si los últimos 3 días son consecutivamente más altos; "a la baja" si más bajos; "neutral" en cualquier otro caso |
| **Volatilidad** | Variación diaria absoluta promedio de los últimos 14 días |

---

## Configuración

El panel de **Configuración** (columna derecha de cada dashboard) permite ajustar los parámetros de ese par en concreto. Cada par tiene su propia configuración independiente.

### Presupuesto mensual

Importe mensual típico en la moneda base del par. El sistema lo multiplica según la señal para calcular el monto sugerido.

### Umbrales de decisión

Porcentajes de desviación que delimitan las señales:

- **C. Fuerte >** (por defecto 3.0): por encima → COMPRA FUERTE
- **C. Mod. >** (por defecto 1.5): por encima → COMPRA MODERADA
- **No Comp. <** (por defecto –1.0): por debajo → NO COMPRAR

El rango entre "No Comp." y "C. Mod." es la zona NEUTRAL.

### Alertas

Configura notificaciones automáticas por webhook cuando se cumplan condiciones:

- **URL Webhook:** cualquier endpoint que acepte un POST JSON (Telegram vía n8n, Discord, Slack, etc.)
- **Alerta si desviación >:** se dispara cuando la desviación supera ese porcentaje
- **Alerta si cotización >:** se dispara cuando la cotización supera ese valor
- **Alertar al activarse COMPRA FUERTE:** casilla de verificación

El payload enviado incluye el nombre del par, la señal, la cotización, la desviación, la confianza y el monto sugerido.

---

## Automatización diaria

Para mantener los datos actualizados sin intervención manual, configura un cron job:

```bash
# Actualizar todos los pares cada hora (días hábiles)
0 * * * 1-5 cd /ruta/al/proyecto && uv run python manage.py fetch_rates --days 3
```

La opción `--days 3` obtiene los últimos 3 días, garantizando que no se pierda ninguna cotización por diferencias de zona horaria.

Para la carga inicial o para actualizar el historial completo:

```bash
uv run python manage.py fetch_rates --days 365
```

### Opciones del comando

```
uv run python manage.py fetch_rates [opciones]

  --days N        Cantidad de días a obtener (por defecto: 90)
  --pair CÓDIGO   Par específico a actualizar (ej: usd-brl). Por defecto: todos.
  --no-alerts     Omitir verificación de alertas en esta ejecución
```

Al terminar, el comando imprime un resumen de indicadores por par y muestra el comparador de rutas UYU → BRL en consola.

---

## Panel de administración

Accede a `/admin/` para ver y editar registros directamente. Primero crea un superusuario:

```bash
uv run python manage.py createsuperuser
```

Desde el admin puedes gestionar los tres pares, ver el historial de cotizaciones filtrado por par, ajustar configuraciones y revisar las compras registradas.

---

## Preguntas frecuentes

**¿Los datos son en tiempo real?**
No. La API provee cotizaciones diarias. La cotización del día actual puede actualizarse varias veces si ejecutas `fetch_rates` más de una vez durante el día.

**¿Necesito una API key?**
No. El sistema usa [awesomeapi.com.br](https://economia.awesomeapi.com.br), una API pública y gratuita sin autenticación.

**¿Qué pasa si la API no responde?**
El botón "↻ Actualizar" muestra un spinner mientras intenta obtener datos. Si falla, conserva los datos existentes sin mostrar error al usuario. El comando CLI sí muestra el error.

**¿El comparador de rutas tiene en cuenta comisiones?**
No. Calcula tasas brutas directamente desde las cotizaciones de la API. Las comisiones de tu banco o casa de cambio pueden cambiar el resultado real.

**¿Puedo usar PostgreSQL en lugar de SQLite?**
Sí. Cambia la variable `DATABASES` en `config/settings.py`. No hay ninguna consulta específica de SQLite en el código.

**¿Puedo añadir más pares?**
Sí. Consulta la guía de programación — se puede hacer desde el panel de administración o con una migración de datos, sin tocar código.
