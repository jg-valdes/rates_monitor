import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "dev-only-key-change-this-for-production-xk2p9mq7vc",
)
DEBUG = os.environ.get("DEBUG", "True") == "True"

if DEBUG:
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]

if not DEBUG:

    def _origins(env_var: str) -> list[str]:
        """Parse a comma-separated list of hostnames/origins and ensure each has a scheme."""
        result = []
        for h in os.environ.get(env_var, "").split(","):
            h = h.strip()
            if not h:
                continue
            if not h.startswith(("http://", "https://")):
                h = f"https://{h}"
            result.append(h)
        return result

    CSRF_TRUSTED_ORIGINS = _origins("CSRF_TRUSTED_ORIGINS_EXTRA")

# Set this in .env to enable the passcode gate. Leave empty to disable in dev.
ACCESS_PASSCODE = os.environ.get("ACCESS_PASSCODE", "")

# ── Telegram alerts ───────────────────────────────────────────────────────────
# Both must be set for alerts to be sent. Leave empty to disable.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_crontab",
    "rates",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "rates.middleware.PasscodeMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "rates.context_processors.active_pairs",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

_data_dir = os.environ.get("DATA_DIR", "")
DATA_DIR = Path(_data_dir) if _data_dir else BASE_DIR

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
    }
}

STATIC_ROOT = BASE_DIR / "staticfiles"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Cron jobs (django-crontab) ────────────────────────────────────────────────
# django-crontab resolves the Python executable and manage.py path at install
# time. Pointing to sys.executable ensures the venv Python is used, which is
# correct both in Docker (/app/.venv/bin/python) and in local dev.
import sys as _sys  # noqa: E402

CRONTAB_PYTHON_EXECUTABLE = _sys.executable
CRONTAB_DJANGO_MANAGE_PATH = str(BASE_DIR / "manage.py")
CRONTAB_LOCK_JOBS = True  # prevents concurrent runs of the same job

CRONJOBS = [
    # Every hour — fetch last 3 days for all pairs, evaluate alerts
    ("0 * * * *", "rates.cron.fetch_rates_hourly"),
    # Every day at 02:00 UTC — 90-day backfill, no alerts (safety net)
    ("0 2 * * *", "rates.cron.fetch_rates_daily_backfill"),
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "rates": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
