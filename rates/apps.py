import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class RatesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "rates"

    def ready(self):
        # Avoid starting the scheduler twice when Django's dev reloader is active.
        import os
        if os.environ.get("RUN_MAIN") == "true" or not _is_runserver():
            _start_scheduler()


def _is_runserver():
    import sys
    return "runserver" in sys.argv


def _start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    from rates.cron import fetch_rates_and_send_all_alerts, fetch_rates_daily_backfill

    scheduler = BackgroundScheduler(timezone="UTC")
    # Twice daily: 07:00 and 12:30 — fetch rates and send Telegram snapshot
    scheduler.add_job(
        fetch_rates_and_send_all_alerts,
        CronTrigger(hour=7, minute=0),
        id="fetch_and_alert_morning",
        max_instances=1,
    )
    scheduler.add_job(
        fetch_rates_and_send_all_alerts,
        CronTrigger(hour=12, minute=30),
        id="fetch_and_alert_midday",
        max_instances=1,
    )
    # Daily at 02:00 UTC — 90-day backfill, no alerts (safety net)
    scheduler.add_job(
        fetch_rates_daily_backfill,
        CronTrigger(hour=2, minute=0),
        id="fetch_daily_backfill",
        max_instances=1,
    )
    scheduler.start()
    logger.info("scheduler: started (07:00, 12:30, 02:00 UTC)")
