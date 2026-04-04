"""
Cron job wrappers registered in settings.CRONJOBS.
Each function is a thin shell that calls the corresponding management command
so django-crontab can reference them by dotted path.
"""

import logging

from django.core.management import call_command

logger = logging.getLogger(__name__)


def fetch_rates_hourly():
    """Run every hour: fetch the last 3 days for all active pairs (with alerts)."""
    logger.info("cron: fetch_rates_hourly start")
    call_command("fetch_rates", days=3)
    logger.info("cron: fetch_rates_hourly done")


def fetch_rates_daily_backfill():
    """Run once a day: 90-day backfill without alerts (safety net for missed days)."""
    logger.info("cron: fetch_rates_daily_backfill start")
    call_command("fetch_rates", days=90, no_alerts=True)
    logger.info("cron: fetch_rates_daily_backfill done")
