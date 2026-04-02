You are a senior full-stack engineer specialized in Python, Django, HTMX, and lightweight financial systems.

Your task is to build a simple but robust web application that helps a user optimize USD to BRL conversions using rule-based analysis.

## 🎯 GOAL

Build a minimal web app that:
1. Tracks USD/BRL exchange rate daily
2. Computes dynamic indicators
3. Generates actionable signals (buy / wait)
4. Displays a simple dashboard
5. Sends alerts when conditions are met

The system must be simple, clean, and production-ready (not overengineered).

---

## 🧱 TECH STACK

- git: init a repo
- Package manager: uv
- Backend: Python + Django
- Frontend: Django templates + HTMX
- UI components: Django Cotton (or simple reusable components)
- Database: SQLite initial (next step PostgreSql)
- Task runner: Django management commands or huey (optional, keep simple first)
- Styling: Minimal CSS or Tailwind (optional)

---

## 📊 CORE FEATURES

### 1. Data Ingestion

- Fetch USD/BRL daily from a reliable API (e.g., openexchangerates.org or similar)
- Store:
  - date
  - open (optional)
  - close (required)
  - high (optional)
  - low (optional)

Create model:

ExchangeRate:
- date (DateField, unique)
- rate (FloatField)

---

### 2. Indicators Engine

Implement the following calculations:

#### Moving Average (MA)
- MA_30
- MA_90

#### Deviation (%)
- deviation = (current_rate - MA_90) / MA_90

#### Momentum (simple)
- last 3 days trend:
  - uptrend if 3 consecutive higher closes
  - downtrend if 3 consecutive lower closes

#### Volatility (simple ATR-like)
- average absolute daily change over last 14 days

---

### 3. Decision Engine (CORE LOGIC)

Implement rules:

IF deviation > +3%:
    signal = "STRONG BUY"

ELIF deviation > +1.5%:
    signal = "MODERATE BUY"

ELIF deviation between -1% and +1.5%:
    signal = "NEUTRAL / WAIT"

ELSE:
    signal = "DO NOT BUY"

Enhance with momentum:

IF STRONG BUY AND momentum == "up":
    confidence = "HIGH"

IF STRONG BUY AND momentum == "down":
    confidence = "MEDIUM"

---

### 4. Capital Allocation Logic

Allow user to define:
- monthly_usd_budget

System suggests:

STRONG BUY:
    allocate 150% of monthly budget

MODERATE BUY:
    allocate 100%

NEUTRAL:
    allocate 50%

DO NOT BUY:
    allocate 0–30%

---

### 5. Dashboard (HTMX-driven)

Single page with:

#### Top Section
- Current USD/BRL
- MA_30 / MA_90
- Deviation %
- Signal (big, colored)
- Suggested USD amount

#### Chart Section
- Simple line chart (last 90 days)

#### Decision Card
- "Today’s Action":
  - BUY STRONG / BUY / WAIT / SKIP
  - Confidence level

#### History Table
- Date
- Rate
- Signal
- Suggested action

Use HTMX to:
- refresh data without full reload
- trigger recalculations

---

### 6. Alerts System

User can configure alerts:

- Notify when:
  - deviation > X%
  - rate > value
  - STRONG BUY triggered

Implement:
- email OR webhook to telegram bot, or simple log-based alerts first

---

### 7. Daily Automation

Create a scheduled job to run each hour:

- fetch new rate
- compute indicators
- store decision
- trigger alerts

Use:
- Django management command (cron-friendly) or huey

---

## 🧩 UX REQUIREMENTS

- Clean, minimal UI
- Mobile-friendly
- No login required (single user app)
- Fast load (<1s)

---

## 🧪 BONUS FEATURES (if time allows)

Add a configuration panel where thresholds (3%, 1.5%, etc.) can be edited from the UI without changing code.
- Track:
  - total USD used
  - total BRL obtained
  - average BRL/USD rate

---

## 🧠 DESIGN PRINCIPLES

- Keep logic modular (services layer)
- Avoid overengineering
- Make decision rules easily editable
- Prioritize clarity over complexity

---

## 🚀 OUTPUT EXPECTATION

Generate:
1. Full Django project structure
2. Models
3. Core services (data + indicators + decision engine)
4. Views + templates (HTMX enabled)
5. Example management command
6. Basic styling
7. Monitor async task executions and results if possible

Explain briefly how to run the project locally.

Do NOT skip implementation details.