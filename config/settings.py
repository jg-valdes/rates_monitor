from pathlib import Path

from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY", default="dev-only-key-change-this-for-production-xk2p9mq7vc")
DEBUG = config("DEBUG", default=True, cast=bool)

if DEBUG:
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="", cast=Csv())

if not DEBUG:

    def _origins(env_var: str) -> list[str]:
        """Parse a comma-separated list of hostnames/origins and ensure each has a scheme."""
        result = []
        for h in config(env_var, default="", cast=Csv()):
            if not h.startswith(("http://", "https://")):
                h = f"https://{h}"
            result.append(h)
        return result

    CSRF_TRUSTED_ORIGINS = _origins("CSRF_TRUSTED_ORIGINS_EXTRA")

# Set this in .env to enable the passcode gate. Leave empty to disable in dev.
ACCESS_PASSCODE = config("ACCESS_PASSCODE", default="")

# ── Exchange rate source ──────────────────────────────────────────────────────
# "awesomeapi" (default, no key needed) or "openexchangerates" (requires key).
EXCHANGE_RATE_SOURCE = config("EXCHANGE_RATE_SOURCE", default="awesomeapi")
# Required when EXCHANGE_RATE_SOURCE = "openexchangerates"
OPENEXCHANGERATES_APP_ID = config("OPENEXCHANGERATES_APP_ID", default="")

# ── Telegram alerts ───────────────────────────────────────────────────────────
# Both must be set for alerts to be sent. Leave empty to disable.
TELEGRAM_BOT_TOKEN = config("TELEGRAM_BOT_TOKEN", default="")
TELEGRAM_CHAT_ID = config("TELEGRAM_CHAT_ID", default="")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
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

_data_dir = config("DATA_DIR", default="")
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
